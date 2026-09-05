import os
import re
import time
import secrets
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps

import requests
from flask import Flask, session, request, jsonify, redirect, render_template
from pymysql.err import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from config import get_db_connection

app = Flask(__name__)

# --- Secret key — dəyişməz olmalıdır, yoxsa bütün sessiyalar ölür ---
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    _key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'secret_key.txt')
    if os.path.exists(_key_path):
        with open(_key_path, 'r') as f:
            _secret_key = f.read().strip()
    if not _secret_key:
        _secret_key = secrets.token_hex(32)
        with open(_key_path, 'w') as f:
            f.write(_secret_key)
app.secret_key = _secret_key

# --- Sessiya avtomatik bitmir (daimi sessiya, ~10 il) ---
app.permanent_session_lifetime = timedelta(days=3650)

# --- Cookie konfiqurasiyası + logging ---
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True
log = logging.getLogger('student')
logging.basicConfig(level=logging.INFO)


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'DENY')
    resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    return resp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ok(data=None, message=None, **extra):
    resp = {"success": True}
    if data is not None:
        resp["data"] = data
    if message:
        resp["message"] = message
    resp.update(extra)
    return jsonify(resp)


def fail(message, status=400):
    return jsonify({"success": False, "message": message}), status


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('student_id'):
            return fail("Giriş tələb olunur!", 403)
        return f(*args, **kwargs)
    return decorated


class BizError(Exception):
    """İş məntiqi xətası — rollback edilir və istifadəçiyə mesajla qaytarılır."""


def with_db(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            conn = get_db_connection()
        except Exception as e:
            return fail(f"DB Bağlantı xətası: {e}", 500)
        try:
            with conn.cursor() as cur:
                result = f(cur, *args, **kwargs)
            conn.commit()
            return result
        except BizError as e:
            conn.rollback()
            return fail(str(e), 400)
        except IntegrityError as e:
            conn.rollback()
            if 'Duplicate entry' in str(e) and 'email' in str(e):
                return fail("Bu email artıq istifadə olunur!", 400)
            return fail(f"Məlumat uyğunsuzluğu: {e}", 400)
        except Exception as e:
            conn.rollback()
            log.exception("Əməliyyat xətası")
            return fail(f"Əməliyyat xətası: {e}", 500)
        finally:
            conn.close()
    return decorated


def clean_val(val):
    if val is None:
        return None
    val = str(val).strip()
    return val if val else None


def as_int(val, default=None):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def get_room_number_for_student(cur, user_id):
    cur.execute("SELECT room_id FROM room_slots WHERE student_id = %s", (user_id,))
    room = cur.fetchone()
    return room['room_id'] if room else 'Bilinmir'


def get_ev_status(cur, user_id):
    cur.execute("SELECT ev FROM students WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        return None
    return row.get('ev') or 'Ev seçilməyib'


def get_cins(cur, user_id):
    cur.execute("SELECT cins FROM students WHERE id = %s", (user_id,))
    row = cur.fetchone()
    return row.get('cins') if row else None


def get_my_group_id(cur, user_id):
    cur.execute("SELECT group_id FROM students WHERE id = %s", (user_id,))
    row = cur.fetchone()
    return row.get('group_id') if row else None


def get_live_group_seq(cur, target_gid, my_cins=None):
    cur.execute("""
        SELECT s.group_id, MIN(s.cins) AS cins
        FROM students s
        WHERE s.group_id IS NOT NULL
        GROUP BY s.group_id ORDER BY s.group_id ASC
    """)
    rows = cur.fetchall()
    ordered = [r['group_id'] for r in rows if my_cins is None or r['cins'] == my_cins]
    if target_gid in ordered:
        return ordered.index(target_gid) + 1
    return target_gid


def dissolve_group_if_empty(cur, group_id):
    if group_id is None:
        return
    cur.execute("SELECT COUNT(*) AS c FROM students WHERE group_id = %s", (group_id,))
    if cur.fetchone()['c'] == 0:
        cur.execute("DELETE FROM student_groups WHERE id = %s", (group_id,))


def remove_from_room(cur, student_id):
    """Tələbəni evdən çıxarır. Bina cinsi SABİTDIR (101-120 Kişi, 121-140 Qadın)."""
    cur.execute("SELECT room_id FROM room_slots WHERE student_id = %s", (student_id,))
    row = cur.fetchone()
    if not row:
        return

    gid = get_my_group_id(cur, student_id)
    cur.execute("UPDATE room_slots SET student_id = NULL WHERE student_id = %s", (student_id,))
    cur.execute("UPDATE students SET ev = 'Ev seçilməyib', group_id = NULL WHERE id = %s", (student_id,))
    if gid:
        dissolve_group_if_empty(cur, gid)


def _cleanup_dead_requests(cur):
    """ÖLÜ TƏLB TƏMİZLƏYİCİ — Gözləmədə olan, amma artıq mənasını itirmiş
    tələbləri avtomatik bağlayır:
      - invite: hədəfin artıq evi varsa (başqa yerdə yerləşibsə)
      - kick/leave: hədəf artıq həmin evdə yaşamırsa (köçübsə/silinibsə)
    Beləliklə, "əbədi gözləmədə" qalan xətalı tələblər yox olur.
    """
    try:
        cur.execute("""
            UPDATE home_requests hr
            JOIN students s ON s.id = hr.target_id
            LEFT JOIN room_slots rs ON rs.student_id = hr.target_id
            SET hr.status = 'Rədd edildi'
            WHERE hr.status = 'Gözləmədə'
              AND (
                (hr.type = 'invite' AND s.ev != 'Ev seçilməyib')
                OR (hr.type IN ('kick', 'leave')
                    AND (rs.room_id IS NULL OR rs.room_id != hr.room_id))
              )
        """)
    except Exception as e:
        log.warning("Ölü tələb təmizlənmədi: %s", e)


def _apply_request(cur, req):
    if req['type'] in ('kick', 'leave'):
        remove_from_room(cur, req['target_id'])


def _check_request_resolution(cur, request_id):
    cur.execute("SELECT * FROM home_requests WHERE id = %s", (request_id,))
    req = cur.fetchone()
    if not req or req['status'] != 'Gözləmədə':
        return

    cur.execute("""
        SELECT rs.student_id FROM room_slots rs
        WHERE rs.room_id = %s AND rs.student_id IS NOT NULL AND rs.student_id != %s
    """, (req['room_id'], req['target_id']))
    eligible = [r['student_id'] for r in cur.fetchall()]

    if not eligible:
        cur.execute("UPDATE home_requests SET status = 'Təsdiqləndi' WHERE id = %s", (request_id,))
        _apply_request(cur, req)
        return

    cur.execute("SELECT voter_id, vote FROM home_request_votes WHERE request_id = %s", (request_id,))
    votes = {v['voter_id']: v['vote'] for v in cur.fetchall()}

    if any(votes.get(eid) == 'Rədd' for eid in eligible):
        cur.execute("UPDATE home_requests SET status = 'Rədd edildi' WHERE id = %s", (request_id,))
        return

    if all(eid in votes for eid in eligible):
        cur.execute("UPDATE home_requests SET status = 'Təsdiqləndi' WHERE id = %s", (request_id,))
        _apply_request(cur, req)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@app.route('/', methods=['GET'])
def index():
    is_logged_in = 'student_id' in session
    user_name = session.get('user_name', '')
    user_ixtisas = session.get('ixtisas', '')
    user_kurs = session.get('kurs', '')
    user_otaq = session.get('otaq_nomresi', '')

    if is_logged_in:
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT ad_soyad, ixtisas, kurs FROM students WHERE id = %s",
                        (session['student_id'],)
                    )
                    row = cur.fetchone()
                    if row:
                        user_name = row['ad_soyad'] or ''
                        user_ixtisas = row['ixtisas'] or ''
                        user_kurs = str(row['kurs'] or '')
                        session['user_name'] = user_name
                        session['ixtisas'] = user_ixtisas
                        session['kurs'] = user_kurs
                    cur.execute(
                        "SELECT room_id FROM room_slots WHERE student_id = %s",
                        (session['student_id'],)
                    )
                    slot = cur.fetchone()
                    user_otaq = str(slot['room_id']) if slot else 'Yoxdur'
                    session['otaq_nomresi'] = user_otaq
            finally:
                conn.close()
        except Exception:
            log.exception("Index sessiya yeniləmə xətası")

    name_first = ''
    user_initials = 'T'
    name_short = 'Tələbə'

    if user_name:
        name_parts = user_name.split(' ')
        name_first = name_parts[0]
        user_initials = name_first[0].upper() if name_first else 'T'
        name_short = name_first
        if len(name_parts) > 1 and name_parts[1]:
            name_short += ' ' + name_parts[1][0].upper() + '.'

    return render_template(
        'index.html',
        user_name=user_name,
        user_ixtisas=user_ixtisas,
        user_kurs=user_kurs,
        user_otaq=user_otaq,
        is_logged_in=is_logged_in,
        name_first=name_first,
        user_initials=user_initials,
        name_short=name_short,
        current_year=datetime.now().year,
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_LOGIN_ATTEMPTS = defaultdict(list)
_LOGIN_WINDOW = 300
_LOGIN_MAX = 10


def _client_ip():
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.remote_addr or 'unknown'


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()
    sifre = data.get('sifre') or ''

    ip = _client_ip()
    now = time.time()
    if len(_LOGIN_ATTEMPTS) > 10000:
        _LOGIN_ATTEMPTS.clear()
    attempts = [t for t in _LOGIN_ATTEMPTS[ip] if now - t < _LOGIN_WINDOW]
    _LOGIN_ATTEMPTS[ip] = attempts
    if len(attempts) >= _LOGIN_MAX:
        return fail("Çoxlu uğursuz cəhd! 5 dəqiqə sonra yenidən cəhd edin.", 429)

    if not email or not sifre:
        return fail("Email və ya şifrə yanlışdır!")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT s.id, s.ad_soyad, s.sifre, s.ixtisas, s.kurs, rs.room_id as otaq_nomresi
                FROM students s
                LEFT JOIN room_slots rs ON rs.student_id = s.id
                WHERE s.email = %s
            """
            cursor.execute(sql, (email,))
            user = cursor.fetchone()
            if not user:
                cursor.execute("""
                    SELECT s.id, s.ad_soyad, s.sifre, s.ixtisas, s.kurs, rs.room_id as otaq_nomresi
                    FROM students s
                    LEFT JOIN room_slots rs ON rs.student_id = s.id
                    WHERE LOWER(s.email) = %s
                """, (email.lower(),))
                user = cursor.fetchone()

            valid = False
            if user:
                stored = user['sifre'] or ''
                if stored.startswith(('pbkdf2:', 'scrypt:')):
                    valid = check_password_hash(stored, sifre)
                elif stored == sifre:
                    valid = True
                    cursor.execute(
                        "UPDATE students SET sifre = %s WHERE id = %s",
                        (generate_password_hash(sifre), user['id'])
                    )
                    conn.commit()

            if not valid:
                _LOGIN_ATTEMPTS[ip].append(time.time())
                return fail("Email və ya şifrə yanlışdır!")

            _LOGIN_ATTEMPTS.pop(ip, None)

            session.permanent = True
            session['student_id'] = user['id']
            session['user_name'] = user['ad_soyad']
            session['ixtisas'] = user['ixtisas']
            session['kurs'] = user['kurs']
            session['otaq_nomresi'] = user.get('otaq_nomresi') or 'Yoxdur'

            user.pop('sifre', None)
            return ok(data=user, message="Giriş uğurludur!")
    except Exception as e:
        log.exception("Login xətası")
        return fail(f"DB Xətası: {e}", 500)
    finally:
        conn.close()


@app.route('/logout', methods=['GET'])
def logout():
    session.clear()
    return redirect('/')


# ---------------------------------------------------------------------------
# Data (GET)
# ---------------------------------------------------------------------------

@app.route('/get_home', methods=['GET'])
@login_required
@with_db
def get_home(cur):
    user_id = session['student_id']

    ev_status = get_ev_status(cur, user_id)
    if ev_status is None:
        return fail("Tələbə tapılmadı")

    if ev_status == 'Rədd edilib':
        return ok(ev_status=ev_status, message="Siz yataqxanada yaşamırsınız")

    if ev_status != 'Ev seçilib':
        my_group_id = get_my_group_id(cur, user_id)
        my_group = None
        if my_group_id:
            cur.execute(
                "SELECT id, ad_soyad, ixtisas, kurs FROM students WHERE group_id = %s ORDER BY ad_soyad ASC",
                (my_group_id,)
            )
            my_seq = get_live_group_seq(cur, my_group_id, get_cins(cur, user_id))
            my_group = {"id": my_seq, "real_id": my_group_id, "members": cur.fetchall()}

        cur.execute(
            "SELECT DISTINCT ixtisas FROM students WHERE ixtisas IS NOT NULL AND ixtisas != '' ORDER BY ixtisas ASC"
        )
        ixtisaslar = [r['ixtisas'] for r in cur.fetchall()]

        return ok(ev_status=ev_status, my_id=user_id, my_group=my_group, ixtisaslar=ixtisaslar)

    gid = get_my_group_id(cur, user_id)
    if gid:
        cur.execute("UPDATE students SET group_id = NULL WHERE id = %s", (user_id,))
        dissolve_group_if_empty(cur, gid)

    cur.execute("SELECT room_id FROM room_slots WHERE student_id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        return fail("Sizin otaq tapılmadı")
    room_number = row['room_id']

    cur.execute("""
        SELECT rs.slot, rs.student_id, rs.yataq_status, rs.skaf_status, rs.oturacaq_status,
               s.ad_soyad
        FROM room_slots rs
        JOIN students s ON s.id = rs.student_id
        WHERE rs.room_id = %s
        ORDER BY rs.slot ASC
    """, (room_number,))
    slots = cur.fetchall()

    if not slots:
        return fail("Otaqda tələbə yoxdur")

    roommates = []
    for slot in slots:
        items = [
            {"item_name": "Yataq", "status": slot.get('yataq_status') or 'Bilinmir'},
            {"item_name": "Oturacaq", "status": slot.get('oturacaq_status') or 'Bilinmir'},
            {"item_name": "Şkaf", "status": slot.get('skaf_status') or 'Bilinmir'}
        ]
        items.sort(key=lambda x: x['item_name'])
        roommates.append({
            "id": slot['student_id'],
            "ad_soyad": slot['ad_soyad'],
            "items": items
        })

    return ok(ev_status=ev_status, my_id=user_id, room_number=room_number, roommates=roommates)


@app.route('/get_applications', methods=['GET'])
@login_required
@with_db
def get_applications(cur):
    user_id = session['student_id']

    cur.execute(
        "UPDATE applications SET notlar = 'Müraciətiniz təsdiqləndi.' "
        "WHERE student_id = %s AND status = 'Təsdiqləndi' AND notlar IS NULL",
        (user_id,)
    )

    sql = """
        SELECT id, basliq, muraciet, priority, status, notlar,
               DATE_FORMAT(created_at, '%%d.%%m.%%Y') as tarix
        FROM applications
        WHERE student_id = %s
        ORDER BY created_at DESC
    """
    cur.execute(sql, (user_id,))
    return ok(applications=cur.fetchall())


@app.route('/get_canteen', methods=['GET'])
@login_required
@with_db
def get_canteen(cur):
    days_az = {
        1: 'Bazar ertəsi', 2: 'Çərşənbə axşamı', 3: 'Çərşənbə',
        4: 'Cümə axşamı', 5: 'Cümə', 6: 'Şənbə', 7: 'Bazar'
    }
    today_num = datetime.now().isoweekday()
    today_name = days_az.get(today_num, 'Bazar')

    cur.execute("SELECT location, meal_name FROM canteen_menu WHERE day_of_week = %s", (today_num,))
    meals = cur.fetchall()

    dorm_meal = 'Restoran bağlıdır'
    uni_meal = 'Restoran bağlıdır'
    for meal in meals:
        if meal['location'] == 'Yataqxana':
            dorm_meal = meal['meal_name']
        if meal['location'] == 'Universitet':
            uni_meal = meal['meal_name']

    return ok(day=today_name, dorm=dorm_meal, uni=uni_meal)


@app.route('/get_contents', methods=['GET'])
@login_required
@with_db
def get_contents(cur):
    cur.execute("""
        SELECT id, type, title, description, priority, status
        FROM contents
        WHERE status = 'Aktiv'
        ORDER BY created_at DESC
    """)
    return ok(contents=cur.fetchall())


@app.route('/get_laundry', methods=['GET'])
@login_required
@with_db
def get_laundry(cur):
    cur.execute("SELECT * FROM laundry WHERE student_id = %s", (session['student_id'],))
    data = cur.fetchone()

    if not data:
        data = {
            "machine_1_status": "Yoxdur",
            "machine_2_status": "Yoxdur",
            "machine_3_status": "Yoxdur"
        }

    return ok(data=data)


_NOTIF_CACHE = {}
_NOTIF_TTL = 20


@app.route('/get_notifications', methods=['GET'])
@login_required
@with_db
def get_notifications(cur):
    """Bildirişlər + badge sayı — 30 saniyəlik polling üçün yüngül cavab."""
    user_id = session['student_id']

    now = time.time()
    hit = _NOTIF_CACHE.get(user_id)
    if hit and now - hit[0] < _NOTIF_TTL:
        return jsonify(hit[1])

    cur.execute("SELECT COUNT(*) as count FROM contents WHERE status = 'Aktiv' AND type = 'announcement'")
    ann_count = cur.fetchone()['count']
    cur.execute("SELECT COUNT(*) as count FROM contents WHERE status = 'Aktiv' AND type = 'survey'")
    surv_count = cur.fetchone()['count']
    cur.execute("SELECT COUNT(*) as count FROM penalties WHERE student_id = %s AND status = 'Ödənilməmiş'", (user_id,))
    pen_count = cur.fetchone()['count']

    req_count = 0
    cur.execute("SELECT room_id FROM room_slots WHERE student_id = %s", (user_id,))
    rrow = cur.fetchone()
    my_room = rrow['room_id'] if rrow else None
    if my_room:
        cur.execute("""
            SELECT COUNT(*) AS c FROM home_requests hr
            WHERE hr.room_id = %s AND hr.status = 'Gözləmədə'
              AND hr.type IN ('kick', 'leave') AND hr.target_id != %s
              AND NOT EXISTS (SELECT 1 FROM home_request_votes v WHERE v.request_id = hr.id AND v.voter_id = %s)
        """, (my_room, user_id, user_id))
        req_count += cur.fetchone()['c']
    cur.execute("""
        SELECT COUNT(*) AS c FROM home_requests
        WHERE target_id = %s AND type = 'invite' AND status = 'Gözləmədə'
    """, (user_id,))
    req_count += cur.fetchone()['c']

    notifications = []
    if ann_count > 0:
        notifications.append({"title": "Aktiv Elanlar", "description": f"{ann_count} ədəd aktiv elanınız var.", "icon": "megaphone", "color": "info", "redirect": "announcements", "redirect_text": "Elanlar"})
    if surv_count > 0:
        notifications.append({"title": "Aktiv Anketlər", "description": f"{surv_count} ədəd anket iştirakınızı gözləyir.", "icon": "clipboard-check", "color": "warning", "redirect": "announcements", "redirect_text": "Elanlar"})
    if pen_count > 0:
        notifications.append({"title": "Ödənişli Cərimələr", "description": f"{pen_count} ədəd ödənilməmiş cəriməniz var.", "icon": "alert-triangle", "color": "danger", "redirect": "payments", "redirect_text": "Ödənişlər"})
    if req_count > 0:
        notifications.append({"title": "Tələblər", "description": f"{req_count} sayda tələb var.", "icon": "inbox", "color": "info", "redirect": "myhome", "redirect_text": "Mənim evim"})

    payload = {
        "success": True,
        "notifications": notifications,
        "total": len(notifications),
        "req_count": req_count
    }
    if len(_NOTIF_CACHE) > 5000:
        _NOTIF_CACHE.clear()
    _NOTIF_CACHE[user_id] = (now, payload)
    return jsonify(payload)


@app.route('/get_penalties', methods=['GET'])
@login_required
@with_db
def get_penalties(cur):
    cur.execute("""
        SELECT id, amount, reason, status
        FROM penalties
        WHERE student_id = %s
        ORDER BY created_at DESC
    """, (session['student_id'],))
    return ok(penalties=cur.fetchall())


@app.route('/get_profile', methods=['GET'])
@login_required
@with_db
def get_profile(cur):
    sql = """
        SELECT s.id, s.ad_soyad, s.email, s.ixtisas, s.kurs, s.api_key, s.ev_deyisme_isteyi,
               p.yuxu_rejimi, p.temizlik, p.sosial_munasibet, p.hayat_terzi
        FROM students s
        LEFT JOIN students_profiles p ON s.id = p.student_id
        WHERE s.id = %s
    """
    cur.execute(sql, (session['student_id'],))
    return ok(data=cur.fetchone())


@app.route('/get_roommates', methods=['GET'])
@login_required
@with_db
def get_roommates(cur):
    cur.execute("""
        SELECT s.id, s.ad_soyad, s.ixtisas, s.ev,
               p.yuxu_rejimi, p.temizlik, p.sosial_munasibet, p.hayat_terzi
        FROM students s
        LEFT JOIN students_profiles p ON s.id = p.student_id
        WHERE s.ev_deyisme_isteyi = 1 AND s.id != %s AND s.cins = %s
    """, (session['student_id'], get_cins(cur, session['student_id'])))
    return ok(roommates=cur.fetchall())


# ---------------------------------------------------------------------------
# Ev seçmə planı (GET)
# ---------------------------------------------------------------------------

@app.route('/get_available_rooms', methods=['GET'])
@login_required
@with_db
def get_available_rooms(cur):
    cur.execute("""
        INSERT IGNORE INTO room_slots (room_id, slot)
        SELECT r.id, s.slot
        FROM rooms r
        JOIN (SELECT 1 AS slot UNION SELECT 2 UNION SELECT 3
              UNION SELECT 4 UNION SELECT 5 UNION SELECT 6) s ON s.slot <= r.capacity
        LEFT JOIN room_slots rs ON rs.room_id = r.id AND rs.slot = s.slot
        WHERE rs.room_id IS NULL
    """)

    my_cins = get_cins(cur, session['student_id'])

    cur.execute("""
        SELECT r.id AS room_id,
               COALESCE(SUM(rs.student_id IS NULL), 0) AS free_count,
               COALESCE(GROUP_CONCAT(CASE WHEN rs.student_id IS NOT NULL THEN s.ad_soyad END
                                      ORDER BY rs.slot SEPARATOR ', '), '') AS occupants_str
        FROM rooms r
        LEFT JOIN room_slots rs ON rs.room_id = r.id
        LEFT JOIN students s ON s.id = rs.student_id
        WHERE (r.cins IS NULL OR r.cins = %s)
        GROUP BY r.id
        HAVING COALESCE(SUM(rs.student_id IS NULL), 0) > 0
        ORDER BY r.id ASC
    """, (my_cins,))
    rooms = cur.fetchall()

    result = [{
        "id": r['room_id'],
        "free_count": r['free_count'],
        "occupants": [x for x in (r['occupants_str'] or '').split(', ') if x]
    } for r in rooms]

    return ok(rooms=result)


@app.route('/search_students', methods=['GET'])
@login_required
@with_db
def search_students(cur):
    user_id = session['student_id']
    q = (request.args.get('q') or '').strip()
    ixtisas = clean_val(request.args.get('ixtisas'))
    kurs = clean_val(request.args.get('kurs'))

    sql = """
        SELECT s.id, s.ad_soyad, s.ixtisas, s.kurs
        FROM students s
        WHERE s.id != %s AND s.ev = 'Ev seçilməyib' AND s.group_id IS NULL AND s.cins = %s
    """
    params = [user_id, get_cins(cur, user_id)]

    if q:
        sql += " AND s.ad_soyad LIKE %s"
        params.append(f"%{q}%")
    if ixtisas:
        sql += " AND s.ixtisas = %s"
        params.append(ixtisas)
    if kurs:
        sql += " AND s.kurs = %s"
        params.append(kurs)

    sql += " ORDER BY s.ad_soyad ASC LIMIT 30"
    cur.execute(sql, tuple(params))
    return ok(students=cur.fetchall())


@app.route('/get_groups', methods=['GET'])
@login_required
@with_db
def get_groups(cur):
    my_cins = get_cins(cur, session['student_id'])
    q = (request.args.get('q') or '').strip()

    cur.execute("""
        DELETE FROM student_groups
        WHERE id NOT IN (
            SELECT gid FROM (SELECT DISTINCT s.group_id AS gid FROM students s WHERE s.group_id IS NOT NULL) x
        )
    """)

    cur.execute("""
        SELECT s.group_id, s.id AS student_id, s.ad_soyad, s.ixtisas, s.kurs, s.cins
        FROM students s
        WHERE s.group_id IS NOT NULL
        ORDER BY s.group_id ASC, s.ad_soyad ASC
    """)
    rows = cur.fetchall()

    groups = {}
    group_cins = {}
    for row in rows:
        gid = row['group_id']
        if gid not in groups:
            groups[gid] = []
            group_cins[gid] = row['cins']
        groups[gid].append({
            "id": row['student_id'], "ad_soyad": row['ad_soyad'],
            "ixtisas": row['ixtisas'], "kurs": row['kurs']
        })

    base = [gid for gid in sorted(groups.keys()) if group_cins[gid] == my_cins]
    numbered = list(enumerate(base, start=1))

    if q:
        if q.isdigit():
            seq = int(q)
            numbered = [(s, g) for s, g in numbered if s == seq]
        else:
            ql = q.lower()
            numbered = [(s, g) for s, g in numbered
                        if any(ql in m['ad_soyad'].lower() for m in groups[g])]

    result = [{"id": s, "real_id": g, "members": groups[g]} for s, g in numbered]
    return ok(groups=result)


@app.route('/get_requests', methods=['GET'])
@login_required
@with_db
def get_requests(cur):
    """Mənim gördüyüm tələblər. Əvvəlcə ölü tələb təmizləyicisi işə düşür."""
    user_id = session['student_id']

    _cleanup_dead_requests(cur)

    cur.execute("SELECT room_id FROM room_slots WHERE student_id = %s", (user_id,))
    row = cur.fetchone()
    my_room = row['room_id'] if row else None

    sql = """
        SELECT hr.id, hr.type, hr.room_id, hr.target_id, hr.requester_id,
               t.ad_soyad AS target_name, r.ad_soyad AS requester_name,
               (SELECT v.vote FROM home_request_votes v WHERE v.request_id = hr.id AND v.voter_id = %s) AS my_vote
        FROM home_requests hr
        JOIN students t ON t.id = hr.target_id
        JOIN students r ON r.id = hr.requester_id
        WHERE hr.status = 'Gözləmədə'
    """
    params = [user_id]
    if my_room:
        sql += " AND (hr.room_id = %s OR hr.target_id = %s)"
        params.extend([my_room, user_id])
    else:
        sql += " AND hr.target_id = %s"
        params.append(user_id)
    sql += " ORDER BY hr.created_at ASC"
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()

    result = []
    for row in rows:
        am_target = (row['target_id'] == user_id)
        can_vote = False
        waiting = []

        if row['type'] in ('kick', 'leave') and my_room == row['room_id'] and not am_target and not row['my_vote']:
            can_vote = True

        if row['type'] in ('kick', 'leave'):
            cur.execute("""
                SELECT s.id, s.ad_soyad FROM room_slots rs
                JOIN students s ON s.id = rs.student_id
                WHERE rs.room_id = %s AND rs.student_id IS NOT NULL AND rs.student_id != %s
            """, (row['room_id'], row['target_id']))
            eligible = cur.fetchall()
            cur.execute("SELECT voter_id FROM home_request_votes WHERE request_id = %s", (row['id'],))
            voted = {v['voter_id'] for v in cur.fetchall()}
            waiting = [e['ad_soyad'] for e in eligible if e['id'] not in voted]

        result.append({
            "id": row['id'], "type": row['type'], "room_id": row['room_id'],
            "target_id": row['target_id'],
            "requester_name": row['requester_name'], "target_name": row['target_name'],
            "am_target": am_target, "my_vote": row['my_vote'], "can_vote": can_vote,
            "waiting": waiting
        })

    return ok(requests=result)


# ---------------------------------------------------------------------------
# Mutations (POST)
# ---------------------------------------------------------------------------

@app.route('/submit_application', methods=['POST'])
@login_required
@with_db
def submit_application(cur):
    user_id = session['student_id']
    data = request.get_json(silent=True) or {}

    basliq = (data.get('basliq') or '').strip()
    muraciet = (data.get('muraciet') or '').strip()
    priority = clean_val(data.get('priority')) or 'Orta'

    if not basliq or not muraciet:
        return fail("Başlıq və müraciət boş ola bilməz!")

    room_number = get_room_number_for_student(cur, user_id)
    full_basliq = f"Otaq {room_number} - {basliq}"

    cur.execute(
        "INSERT INTO applications (student_id, basliq, muraciet, priority) VALUES (%s, %s, %s, %s)",
        (user_id, full_basliq, muraciet, priority)
    )
    return ok(message="Müraciət uğurla göndərildi!")


@app.route('/update_application', methods=['POST'])
@login_required
@with_db
def update_application(cur):
    user_id = session['student_id']
    data = request.get_json(silent=True) or {}

    app_id = as_int(data.get('id'), 0)
    basliq = (data.get('basliq') or '').strip()
    muraciet = (data.get('muraciet') or '').strip()
    priority = clean_val(data.get('priority')) or 'Orta'

    if not basliq or not muraciet:
        return fail("Başlıq və müraciət boş ola bilməz!")

    room_number = get_room_number_for_student(cur, user_id)
    full_basliq = f"Otaq {room_number} - {basliq}"

    cur.execute(
        "UPDATE applications SET basliq = %s, muraciet = %s, priority = %s WHERE id = %s AND student_id = %s",
        (full_basliq, muraciet, priority, app_id, user_id)
    )
    return ok(message="Müraciət yeniləndi!")


@app.route('/delete_application', methods=['POST'])
@login_required
@with_db
def delete_application(cur):
    user_id = session['student_id']
    data = request.get_json(silent=True) or {}
    app_id = as_int(data.get('id'), 0)

    cur.execute("DELETE FROM applications WHERE id = %s AND student_id = %s", (app_id, user_id))
    return ok(message="Müraciət silindi!")


@app.route('/update_profile', methods=['POST'])
@login_required
@with_db
def update_profile(cur):
    data = request.get_json(silent=True) or {}
    user_id = session['student_id']

    email = clean_val(data.get('email'))
    ixtisas = clean_val(data.get('ixtisas'))
    kurs = clean_val(data.get('kurs')) or '1'
    api_key = clean_val(data.get('api_key'))
    ev_deyisme = 1 if data.get('ev_deyisme_isteyi') else 0

    yuxu = clean_val(data.get('yuxu_rejimi'))
    temizlik = clean_val(data.get('temizlik'))
    sosial = clean_val(data.get('sosial_munasibet'))
    hayat = clean_val(data.get('hayat_terzi'))

    if email:
        cur.execute(
            "SELECT id FROM students WHERE email = %s AND id != %s",
            (email, user_id)
        )
        if cur.fetchone():
            return fail("Bu email başqa tələbə tərəfindən istifadə olunur!")

    cur.execute(
        "UPDATE students SET email = %s, ixtisas = %s, kurs = %s, api_key = %s, ev_deyisme_isteyi = %s WHERE id = %s",
        (email, ixtisas, kurs, api_key, ev_deyisme, user_id)
    )

    cur.execute("""
        INSERT INTO students_profiles (student_id, yuxu_rejimi, temizlik, sosial_munasibet, hayat_terzi)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        yuxu_rejimi = VALUES(yuxu_rejimi),
        temizlik = VALUES(temizlik),
        sosial_munasibet = VALUES(sosial_munasibet),
        hayat_terzi = VALUES(hayat_terzi)
    """, (user_id, yuxu, temizlik, sosial, hayat))

    session['ixtisas'] = ixtisas or ''
    session['kurs'] = kurs or ''

    return ok(message="Profil yeniləndi!")


# ---------------------------------------------------------------------------
# Qruplar (POST)
# ---------------------------------------------------------------------------

@app.route('/create_group', methods=['POST'])
@login_required
@with_db
def create_group(cur):
    user_id = session['student_id']

    if get_ev_status(cur, user_id) != 'Ev seçilməyib':
        return fail("Yalnız ev seçməmiş tələbələr qrup yarada bilər!")
    if get_my_group_id(cur, user_id) is not None:
        return fail("Siz artıq bir qrupdasınız!")

    cur.execute("INSERT INTO student_groups (created_at) VALUES (NOW())")
    group_id = cur.lastrowid
    cur.execute("UPDATE students SET group_id = %s WHERE id = %s", (group_id, user_id))

    seq = get_live_group_seq(cur, group_id, get_cins(cur, user_id))
    return ok(group_id=seq, message=f"Qrup #{seq} yaradıldı!")


@app.route('/join_group', methods=['POST'])
@login_required
@with_db
def join_group(cur):
    user_id = session['student_id']
    data = request.get_json(silent=True) or {}
    seq = as_int(data.get('group_id'), 0)

    if get_ev_status(cur, user_id) != 'Ev seçilməyib':
        return fail("Yalnız ev seçməmiş tələbələr qrupa qoşula bilər!")
    if get_my_group_id(cur, user_id) is not None:
        return fail("Siz artıq bir qrupdasınız! Əvvəlcə qrupdan çıxın.")

    my_cins = get_cins(cur, user_id)

    cur.execute("""
        SELECT s.group_id, MIN(s.cins) AS cins
        FROM students s WHERE s.group_id IS NOT NULL
        GROUP BY s.group_id ORDER BY s.group_id ASC
    """)
    rows = cur.fetchall()
    visible = [r['group_id'] for r in rows if r['cins'] == my_cins]

    if not (isinstance(seq, int) and 1 <= seq <= len(visible)):
        return fail("Belə bir qrup yoxdur!")
    group_id = visible[seq - 1]

    cur.execute("SELECT COUNT(*) AS c FROM students WHERE group_id = %s", (group_id,))
    count = cur.fetchone()['c']
    if count >= 6:
        return fail("Qrup doludur (maksimum 6 üzv)!")

    cur.execute("UPDATE students SET group_id = %s WHERE id = %s", (group_id, user_id))
    return ok(message="Qrupa qoşuldunuz!")


@app.route('/leave_group', methods=['POST'])
@login_required
@with_db
def leave_group(cur):
    user_id = session['student_id']
    gid = get_my_group_id(cur, user_id)
    if gid is None:
        return fail("Siz heç bir qrupda deyilsiniz!")

    cur.execute("UPDATE students SET group_id = NULL WHERE id = %s", (user_id,))
    dissolve_group_if_empty(cur, gid)
    return ok(message="Qrupdan çıxdınız!")


@app.route('/add_group_member', methods=['POST'])
@login_required
@with_db
def add_group_member(cur):
    user_id = session['student_id']
    data = request.get_json(silent=True) or {}
    student_id = as_int(data.get('student_id'), 0)

    gid = get_my_group_id(cur, user_id)
    if gid is None:
        return fail("Əvvəlcə qrup yaradın və ya bir qrupa qoşulun!")

    cur.execute("SELECT COUNT(*) AS c FROM students WHERE group_id = %s", (gid,))
    if cur.fetchone()['c'] >= 6:
        return fail("Qrup doludur (maksimum 6 üzv)!")

    my_cins = get_cins(cur, user_id)
    cur.execute("SELECT ev, group_id, cins FROM students WHERE id = %s", (student_id,))
    target = cur.fetchone()
    if not target:
        return fail("Tələbə tapılmadı!")
    if target['cins'] != my_cins:
        return fail("Yalnız eyni cinsdən tələbələr əlavə oluna bilər!")
    if target['ev'] != 'Ev seçilməyib':
        return fail("Bu tələbənin artıq evi var!")
    if target['group_id'] is not None:
        return fail("Bu tələbə artıq başqa qrupdadır!")

    cur.execute("UPDATE students SET group_id = %s WHERE id = %s", (gid, student_id))
    return ok(message="Üzv qrupa əlavə olundu!")


# ---------------------------------------------------------------------------
# Ev seçmə (POST)
# ---------------------------------------------------------------------------

@app.route('/select_home', methods=['POST'])
@login_required
@with_db
def select_home(cur):
    user_id = session['student_id']
    data = request.get_json(silent=True) or {}
    room_id = as_int(data.get('room_id'), 0)

    if get_ev_status(cur, user_id) != 'Ev seçilməyib':
        return fail("Sizin artıq eviniz seçilib!")

    my_cins = get_cins(cur, user_id)

    gid = get_my_group_id(cur, user_id)
    member_ids = [user_id]
    if gid is not None:
        cur.execute("SELECT COUNT(*) AS c FROM students WHERE group_id = %s AND cins != %s", (gid, my_cins))
        if cur.fetchone()['c'] > 0:
            return fail("Qrupunuzda qarşı cinsdən üzv var!")
        cur.execute(
            "SELECT id FROM students WHERE group_id = %s AND ev = 'Ev seçilməyib' ORDER BY id ASC",
            (gid,)
        )
        member_ids = [row['id'] for row in cur.fetchall()]
        if user_id not in member_ids:
            member_ids.append(user_id)

    cur.execute("SELECT id, cins FROM rooms WHERE id = %s", (room_id,))
    room = cur.fetchone()
    if not room:
        return fail("Ev tapılmadı!")
    if room['cins'] is not None and room['cins'] != my_cins:
        return fail("Bu ev qarşı cinsə aiddir!")

    cur.execute("""
        INSERT IGNORE INTO room_slots (room_id, slot)
        SELECT %s, s.slot FROM (SELECT 1 AS slot UNION SELECT 2 UNION SELECT 3
                                UNION SELECT 4 UNION SELECT 5 UNION SELECT 6) s
    """, (room_id,))

    cur.execute(
        "SELECT slot FROM room_slots WHERE room_id = %s AND student_id IS NULL ORDER BY slot ASC",
        (room_id,)
    )
    free_slots = [r['slot'] for r in cur.fetchall()]

    if len(free_slots) < len(member_ids):
        return fail(
            f"Bu evdə yalnız {len(free_slots)} boş yer var, "
            f"yerləşəcək şəxs sayı isə {len(member_ids)}-dir!"
        )

    assigned = 0
    for student_id, slot in zip(member_ids, free_slots):
        cur.execute(
            "UPDATE room_slots SET student_id = %s WHERE room_id = %s AND slot = %s AND student_id IS NULL",
            (student_id, room_id, slot)
        )
        assigned += cur.rowcount
    if assigned != len(member_ids):
        raise BizError("Bu əsnədə ev doldu — siyahını yeniləyib təkrar seçin!")

    placeholders = ','.join(['%s'] * len(member_ids))
    cur.execute(
        f"UPDATE students SET ev = 'Ev seçilib', group_id = NULL WHERE id IN ({placeholders})",
        tuple(member_ids)
    )

    if room['cins'] is None:
        cur.execute("UPDATE rooms SET cins = %s WHERE id = %s", (my_cins, room_id))

    cur.execute(
        f"UPDATE home_requests SET status = 'Rədd edildi' WHERE target_id IN ({placeholders}) "
        "AND type = 'invite' AND status = 'Gözləmədə'",
        tuple(member_ids)
    )

    if gid is not None:
        cur.execute("UPDATE students SET group_id = NULL WHERE group_id = %s", (gid,))
        cur.execute("DELETE FROM student_groups WHERE id = %s", (gid,))

    return ok(message=f"Ev {room_id} seçildi! Qrupunuzla birlikdə yerləşdirildiniz.")


# ---------------------------------------------------------------------------
# Tələblər (POST)
# ---------------------------------------------------------------------------

@app.route('/invite_roommate', methods=['POST'])
@login_required
@with_db
def invite_roommate(cur):
    user_id = session['student_id']
    data = request.get_json(silent=True) or {}
    target_id = as_int(data.get('student_id'), 0)

    if get_ev_status(cur, user_id) != 'Ev seçilib':
        return fail("Dəvət etmək üçün əvvəlcə evdə yaşamalısınız!")

    cur.execute("SELECT room_id FROM room_slots WHERE student_id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        return fail("Sizin eviniz tapılmadı!")
    room_id = row['room_id']

    my_cins = get_cins(cur, user_id)
    cur.execute("SELECT ev, cins FROM students WHERE id = %s", (target_id,))
    target = cur.fetchone()
    if not target:
        return fail("Tələbə tapılmadı!")
    if target_id == user_id:
        return fail("Özünüzü dəvət edə bilməzsiniz!")
    if target['cins'] != my_cins:
        return fail("Yalnız eyni cinsdən tələbələri dəvət edə bilərsiniz!")
    if target['ev'] != 'Ev seçilməyib':
        return fail("Bu tələbənin artıq evi var!")

    cur.execute("SELECT capacity FROM rooms WHERE id = %s", (room_id,))
    capacity = cur.fetchone()['capacity']
    cur.execute(
        "SELECT COUNT(*) AS c FROM room_slots WHERE room_id = %s AND student_id IS NOT NULL",
        (room_id,)
    )
    if cur.fetchone()['c'] >= capacity:
        return fail("Evdə boş yer yoxdur!")

    cur.execute(
        "SELECT COUNT(*) AS c FROM home_requests WHERE target_id = %s AND type = 'invite' AND status = 'Gözləmədə'",
        (target_id,)
    )
    if cur.fetchone()['c'] > 0:
        return fail("Bu tələbəyə artıq aktiv dəvət var!")

    cur.execute(
        "INSERT INTO home_requests (type, room_id, target_id, requester_id) VALUES ('invite', %s, %s, %s)",
        (room_id, target_id, user_id)
    )
    return ok(message="Dəvət göndərildi — cavabı 'Tələblər' bölməsində görünəcək.")


@app.route('/respond_invite', methods=['POST'])
@login_required
@with_db
def respond_invite(cur):
    user_id = session['student_id']
    data = request.get_json(silent=True) or {}
    req_id = as_int(data.get('request_id'), 0)
    accept = bool(data.get('accept', False))

    cur.execute(
        "SELECT * FROM home_requests WHERE id = %s AND target_id = %s AND type = 'invite' AND status = 'Gözləmədə'",
        (req_id, user_id)
    )
    req = cur.fetchone()
    if not req:
        return fail("Dəvət tapılmadı!")

    if not accept:
        cur.execute("UPDATE home_requests SET status = 'Rədd edildi' WHERE id = %s", (req_id,))
        return ok(message="Dəvət rədd edildi.")

    my_cins = get_cins(cur, user_id)
    cur.execute("SELECT cins FROM rooms WHERE id = %s", (req['room_id'],))
    room = cur.fetchone()
    if room['cins'] is not None and room['cins'] != my_cins:
        cur.execute("UPDATE home_requests SET status = 'Rədd edildi' WHERE id = %s", (req_id,))
        return fail("Bu ev artıq qarşı cinsə aiddir!")

    if get_ev_status(cur, user_id) != 'Ev seçilməyib':
        cur.execute("UPDATE home_requests SET status = 'Rədd edildi' WHERE id = %s", (req_id,))
        return fail("Sizin artıq eviniz var!")

    cur.execute("""
        INSERT IGNORE INTO room_slots (room_id, slot)
        SELECT %s, s.slot FROM (SELECT 1 AS slot UNION SELECT 2 UNION SELECT 3
                                UNION SELECT 4 UNION SELECT 5 UNION SELECT 6) s
    """, (req['room_id'],))

    cur.execute(
        "SELECT slot FROM room_slots WHERE room_id = %s AND student_id IS NULL ORDER BY slot ASC LIMIT 1",
        (req['room_id'],)
    )
    slot_row = cur.fetchone()
    if not slot_row:
        cur.execute("UPDATE home_requests SET status = 'Rədd edildi' WHERE id = %s", (req_id,))
        return fail("Evdə boş yer yoxdur!")

    cur.execute(
        "UPDATE room_slots SET student_id = %s WHERE room_id = %s AND slot = %s AND student_id IS NULL",
        (user_id, req['room_id'], slot_row['slot'])
    )
    if cur.rowcount == 0:
        raise BizError("Bu əsnədə ev doldu — dəvət ləğv olundu, yenidən ev seçin!")
    if room['cins'] is None:
        cur.execute("UPDATE rooms SET cins = %s WHERE id = %s", (my_cins, req['room_id']))

    gid = get_my_group_id(cur, user_id)
    cur.execute("UPDATE students SET ev = 'Ev seçilib', group_id = NULL WHERE id = %s", (user_id,))
    if gid:
        dissolve_group_if_empty(cur, gid)

    cur.execute("UPDATE home_requests SET status = 'Təsdiqləndi' WHERE id = %s", (req_id,))
    cur.execute(
        "UPDATE home_requests SET status = 'Rədd edildi' WHERE target_id = %s AND type = 'invite' AND status = 'Gözləmədə' AND id != %s",
        (user_id, req_id)
    )
    return ok(message=f"Ev {req['room_id']} dəvəti qəbul edildi!")


@app.route('/request_kick', methods=['POST'])
@login_required
@with_db
def request_kick(cur):
    user_id = session['student_id']
    data = request.get_json(silent=True) or {}
    target_id = as_int(data.get('student_id'), 0)

    if target_id == user_id:
        return fail("Özünüzü qova bilməzsiniz — 'Evdən çıx' düyməsini istifadə edin.")

    my_room = get_room_number_for_student(cur, user_id)
    target_room = get_room_number_for_student(cur, target_id)
    if my_room == 'Bilinmir' or my_room != target_room:
        return fail("Bu tələbə sizin evinizdə yaşamır!")

    cur.execute(
        "SELECT COUNT(*) AS c FROM home_requests WHERE room_id = %s AND target_id = %s AND type IN ('kick', 'leave') AND status = 'Gözləmədə'",
        (my_room, target_id)
    )
    if cur.fetchone()['c'] > 0:
        return fail("Bu tələbə üçün aktiv tələb artıq var!")

    cur.execute(
        "INSERT INTO home_requests (type, room_id, target_id, requester_id) VALUES ('kick', %s, %s, %s)",
        (my_room, target_id, user_id)
    )
    req_id = cur.lastrowid

    cur.execute(
        "INSERT INTO home_request_votes (request_id, voter_id, vote) VALUES (%s, %s, 'Təsdiq')",
        (req_id, user_id)
    )
    _check_request_resolution(cur, req_id)
    return ok(message="Qovma tələbi göndərildi — ev yoldaşlarının təsdiqi gözlənilir.")


@app.route('/request_leave', methods=['POST'])
@login_required
@with_db
def request_leave(cur):
    user_id = session['student_id']

    cur.execute("SELECT room_id FROM room_slots WHERE student_id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        return fail("Siz evdə yaşamırsınız!")
    room_id = row['room_id']

    cur.execute(
        "SELECT COUNT(*) AS c FROM room_slots WHERE room_id = %s AND student_id IS NOT NULL",
        (room_id,)
    )
    if cur.fetchone()['c'] == 1:
        remove_from_room(cur, user_id)
        return ok(message="Evdən çıxdınız.")

    cur.execute(
        "SELECT COUNT(*) AS c FROM home_requests WHERE room_id = %s AND target_id = %s AND type = 'leave' AND status = 'Gözləmədə'",
        (room_id, user_id)
    )
    if cur.fetchone()['c'] > 0:
        return fail("Çıxma tələbiniz onsuzda gözləmədədir!")

    cur.execute(
        "INSERT INTO home_requests (type, room_id, target_id, requester_id) VALUES ('leave', %s, %s, %s)",
        (room_id, user_id, user_id)
    )
    req_id = cur.lastrowid

    cur.execute(
        "INSERT INTO home_request_votes (request_id, voter_id, vote) VALUES (%s, %s, 'Təsdiq')",
        (req_id, user_id)
    )
    _check_request_resolution(cur, req_id)
    return ok(message="Çıxma tələbi göndərildi — ev yoldaşlarının təsdiyi gözlənilir.")


@app.route('/vote_request', methods=['POST'])
@login_required
@with_db
def vote_request(cur):
    user_id = session['student_id']
    data = request.get_json(silent=True) or {}
    req_id = as_int(data.get('request_id'), 0)
    vote = 'Təsdiq' if data.get('vote') == 'Təsdiq' else 'Rədd'

    cur.execute("SELECT * FROM home_requests WHERE id = %s AND status = 'Gözləmədə'", (req_id,))
    req = cur.fetchone()
    if not req:
        return fail("Tələb tapılmadı!")
    if req['type'] == 'invite':
        return fail("Dəvət üçün səsvermə yoxdur!")
    if req['target_id'] == user_id:
        return fail("Bu tələb sizin haqqınızdadır!")

    cur.execute(
        "SELECT COUNT(*) AS c FROM room_slots WHERE room_id = %s AND student_id = %s",
        (req['room_id'], user_id)
    )
    if cur.fetchone()['c'] == 0:
        return fail("Siz bu evdə yaşamırsınız!")

    cur.execute(
        "SELECT COUNT(*) AS c FROM home_request_votes WHERE request_id = %s AND voter_id = %s",
        (req_id, user_id)
    )
    if cur.fetchone()['c'] > 0:
        return fail("Siz artıq səs vermisiniz!")

    cur.execute(
        "INSERT INTO home_request_votes (request_id, voter_id, vote) VALUES (%s, %s, %s)",
        (req_id, user_id, vote)
    )

    if vote == 'Rədd':
        cur.execute("UPDATE home_requests SET status = 'Rədd edildi' WHERE id = %s", (req_id,))
        return ok(message="Tələb rədd edildi.")

    _check_request_resolution(cur, req_id)
    return ok(message="Səsiniz qeydə alındı.")


# ---------------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------------

@app.route('/ai_handler', methods=['POST'])
@login_required
def ai_handler():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT api_key, ad_soyad FROM students WHERE id = %s", (session['student_id'],))
            user_data = cursor.fetchone()
    finally:
        conn.close()

    api_key = user_data.get('api_key', '') if user_data else ''
    istifadeci_adi = user_data.get('ad_soyad', 'Tələbə') if user_data else 'Tələbə'

    if not api_key:
        return fail("API açarı tapılmadı! Zəhmət olmasa Profil bölməsindən şəxsi Gemini API açarınızı daxil edin.")

    data = request.get_json(silent=True) or {}
    if not data or 'type' not in data:
        return fail("Yanlış sorğu formatı.")

    model = "gemini-flash-lite-latest"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    contents = []
    system_prompt = ""
    req_type = data['type']

    if req_type == 'chat':
        system_prompt = f"Sən 'Yaşıl Kampus' adlı Qarabağ Universitetinin yataqxanasının rəqəmsal AI köməkçisən. Adın 'Kampus AI'-dır. İstifadəçinin adı: {istifadeci_adi}. Əgər söhbət artıq başlayıbsa, təkrar Salam vermə, birbaşa cavab ver."

        history = data.get('history', [])
        for msg in history:
            role = 'user' if msg.get('role') == 'user' else 'model'
            contents.append({"role": role, "parts": [{"text": msg.get('text', '')}]})

        current_msg = (data.get('message') or '').strip()
        if not current_msg:
            return fail("Boş mesaj göndərilə bilməz.")
        contents.append({"role": "user", "parts": [{"text": current_msg}]})
        temperature = 0.7
        max_tokens = 250

    elif req_type == 'match':
        system_prompt = "Sən bir uyğunluq hesablama aparatısan. İstifadəçiyə yalnız 0 ilə 100 arasında tam rəqəm qaytarırsan."
        target_id = as_int(data.get('target_id'), 0)

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT s.id, s.ad_soyad, p.yuxu_rejimi, p.temizlik, p.sosial_munasibet, p.hayat_terzi
                    FROM students s
                    LEFT JOIN students_profiles p ON s.id = p.student_id
                    WHERE s.id IN (%s, %s)
                """, (session['student_id'], target_id))
                users = cursor.fetchall()
        finally:
            conn.close()

        if len(users) < 2:
            return fail("Tələbə məlumatları tapılmadı.")

        try:
            me = next(u for u in users if u['id'] == session['student_id'])
            target = next(u for u in users if u['id'] == target_id)
        except StopIteration:
            return fail("Tələbə məlumatları tapılmadı.")

        match_prompt = f"Tələbə 1 ({me['ad_soyad']}): Yuxu: {me['yuxu_rejimi']}, Təmizlik: {me['temizlik']}, Sosial: {me['sosial_munasibet']}, Həyat: {me['hayat_terzi']}.\n"
        match_prompt += f"Tələbə 2 ({target['ad_soyad']}): Yuxu: {target['yuxu_rejimi']}, Təmizlik: {target['temizlik']}, Sosial: {target['sosial_munasibet']}, Həyat: {target['hayat_terzi']}.\n"
        match_prompt += "Bu iki tələbənin otaq yoldaşı olaraq neçə faiz (0-100) uyğun olduğunu hesabla. Yalnız rəqəmi qaytar."

        contents.append({"role": "user", "parts": [{"text": match_prompt}]})
        temperature = 0.2
        max_tokens = 10
    else:
        return fail("Yanlış sorğu növü.")

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "topP": 0.9
        }
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        result = response.json()
    except Exception:
        return fail("AI serverinə qoşulmaq mümkün olmadı.")

    if result.get('error'):
        return fail(f"AI Xətası: {result['error'].get('message', 'API açarı yanlış ola bilər!')}")

    candidates = result.get('candidates', [])
    if not candidates or not candidates[0].get('content', {}).get('parts', [{}])[0].get('text'):
        return fail("AI boş cavab qaytardı.")

    ai_text = candidates[0]['content']['parts'][0]['text']

    if req_type == 'match':
        numbers = re.findall(r'\d+', ai_text)
        score = int(numbers[0]) if numbers else 0
        score = max(0, min(100, score))
        return ok(score=score)
    else:
        return ok(reply=ai_text.strip())


if __name__ == '__main__':
    app.run(debug=False)
