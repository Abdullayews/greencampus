import os
import re
import secrets
from datetime import datetime
from functools import wraps

import requests
from flask import Flask, session, request, jsonify, redirect, render_template
from pymysql.err import IntegrityError

from config import get_db_connection

app = Flask(__name__)

# --- Session secret key ---
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
        except IntegrityError as e:
            conn.rollback()
            return fail(f"Məlumat uyğunsuzluğu: {e}", 400)
        except Exception as e:
            conn.rollback()
            return fail(f"Əməliyyat xətası: {e}", 500)
        finally:
            conn.close()
    return decorated


def clean_val(val):
    """Boş string və ya undefined dəyərləri None etmək (ENUM xətalarının qarşısını almaq üçün)"""
    if val is None:
        return None
    val = str(val).strip()
    return val if val else None


def get_room_number_for_student(cur, user_id):
    """Tələbənin otaq nömrəsini tapır."""
    cur.execute(
        "SELECT id FROM rooms WHERE telebe_1_id = %s OR telebe_2_id = %s OR telebe_3_id = %s OR telebe_4_id = %s OR telebe_5_id = %s OR telebe_6_id = %s",
        (user_id, user_id, user_id, user_id, user_id, user_id)
    )
    room = cur.fetchone()
    return room['id'] if room else 'Bilinmir'


def get_ev_status(cur, user_id):
    """Tələbənin ev statusu: 'Ev seçilib' / 'Ev seçilməyib' / 'Rədd edilib'."""
    cur.execute("SELECT ev FROM students WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        return None
    return row.get('ev') or 'Ev seçilməyib'


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@app.route('/', methods=['GET'])
def index():
    """Tələbə portalı ana səhifəsi."""
    user_name = session.get('user_name', '')
    user_ixtisas = session.get('ixtisas', '')
    user_kurs = session.get('kurs', '')
    user_otaq = session.get('otaq_nomresi', '')
    is_logged_in = 'student_id' in session

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

@app.route('/login', methods=['POST'])
def login():
    """Tələbə girişi."""
    data = request.get_json() or {}
    email = data.get('email', '')
    sifre = data.get('sifre', '')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT s.id, s.ad_soyad, s.sifre, s.ixtisas, s.kurs, r.id as otaq_nomresi
                FROM students s
                LEFT JOIN rooms r ON s.id = r.telebe_1_id OR s.id = r.telebe_2_id
                    OR s.id = r.telebe_3_id OR s.id = r.telebe_4_id
                    OR s.id = r.telebe_5_id OR s.id = r.telebe_6_id
                WHERE s.email = %s
            """
            cursor.execute(sql, (email,))
            user = cursor.fetchone()

            if user:
                if user['sifre'] == sifre:
                    session['student_id'] = user['id']
                    session['user_name'] = user['ad_soyad']
                    session['ixtisas'] = user['ixtisas']
                    session['kurs'] = user['kurs']
                    session['otaq_nomresi'] = user.get('otaq_nomresi') or 'Yoxdur'

                    user.pop('sifre', None)
                    return ok(data=user, message="Giriş uğurludur!")
                else:
                    return fail("Şifrə yanlışdır!")
            else:
                return fail(f"Bu email databasedə yoxdur: {email}")
    except Exception as e:
        return fail(f"DB Xətası: {e}", 500)
    finally:
        conn.close()


@app.route('/logout', methods=['GET'])
def logout():
    """Tələbə çıxışı — yalnız tələbə session key-ləri silinir (admin panelə təsir etmir)."""
    session.pop('student_id', None)
    session.pop('user_name', None)
    session.pop('ixtisas', None)
    session.pop('kurs', None)
    session.pop('otaq_nomresi', None)
    return redirect('/')


# ---------------------------------------------------------------------------
# Data (GET)
# ---------------------------------------------------------------------------

@app.route('/get_home', methods=['GET'])
@login_required
@with_db
def get_home(cur):
    """
    Mənim evim.
    Əvvəlcə students.ev statusu yoxlanılır:
      - 'Rədd edilib'   → yalnız mesaj (frontend ortada bir sətr göstərir)
      - 'Ev seçilməyib' → yalnız status (məzmun sonradan əlavə olunacaq)
      - 'Ev seçilib'    → otaq və otaq yoldaşları (əvvəlki məntiq)
    """
    user_id = session['student_id']

    # 1) Ev statusunun yoxlanması
    ev_status = get_ev_status(cur, user_id)
    if ev_status is None:
        return fail("Tələbə tapılmadı")

    if ev_status == 'Rədd edilib':
        return ok(ev_status=ev_status, message="Siz yataqxanada yaşamırsınız")

    if ev_status != 'Ev seçilib':
        # 'Ev seçilməyib' — bu hal üçün davranış sonradan müəyyənləşəcək
        return ok(ev_status=ev_status)

    # 2) 'Ev seçilib' — otaq və otaq yoldaşları
    cur.execute(
        "SELECT * FROM rooms WHERE telebe_1_id = %s OR telebe_2_id = %s OR telebe_3_id = %s OR telebe_4_id = %s OR telebe_5_id = %s OR telebe_6_id = %s",
        (user_id, user_id, user_id, user_id, user_id, user_id)
    )
    room = cur.fetchone()

    if not room:
        return fail("Sizin otaq tapılmadı")

    room_number = room['id']
    student_ids = []
    positions = {}

    for i in range(1, 7):
        col = f"telebe_{i}_id"
        if room.get(col):
            student_ids.append(room[col])
            positions[room[col]] = i

    if not student_ids:
        return fail("Otaqda tələbə yoxdur")

    placeholders = ','.join(['%s'] * len(student_ids))
    cur.execute(
        f"SELECT id, ad_soyad FROM students WHERE id IN ({placeholders}) ORDER BY ad_soyad ASC",
        tuple(student_ids)
    )
    students = cur.fetchall()

    roommates = []
    for student in students:
        sid = student['id']
        pos = positions[sid]
        items = [
            {"item_name": "Yataq", "status": room.get(f"yataq_{pos}_status", 'Bilinmir')},
            {"item_name": "Oturacaq", "status": room.get(f"oturacaq_{pos}_status", 'Bilinmir')},
            {"item_name": "Şkaf", "status": room.get(f"skaf_{pos}_status", 'Bilinmir')}
        ]
        items.sort(key=lambda x: x['item_name'])
        roommates.append({
            "id": sid,
            "ad_soyad": student['ad_soyad'],
            "items": items
        })

    return ok(ev_status=ev_status, room_number=room_number, roommates=roommates)


@app.route('/get_applications', methods=['GET'])
@login_required
@with_db
def get_applications(cur):
    """Tələbənin ərizə siyahısı."""
    sql = """
        SELECT id, basliq, muraciet, priority, status,
               DATE_FORMAT(created_at, '%%d.%%m.%%Y') as tarix
        FROM applications
        WHERE student_id = %s
        ORDER BY created_at DESC
    """
    cur.execute(sql, (session['student_id'],))
    applications = cur.fetchall()
    return ok(applications=applications)


@app.route('/get_canteen', methods=['GET'])
@login_required
@with_db
def get_canteen(cur):
    """Bugünkü yeməkxana menyusu."""
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
    """Aktiv elan və sorğu siyahısı."""
    cur.execute("""
        SELECT id, type, title, description, priority, status
        FROM contents
        WHERE status = 'Aktiv'
        ORDER BY created_at DESC
    """)
    contents = cur.fetchall()
    return ok(contents=contents)


@app.route('/get_laundry', methods=['GET'])
@login_required
@with_db
def get_laundry(cur):
    """Tələbənin camaşırxana statusu."""
    cur.execute("SELECT * FROM laundry WHERE student_id = %s", (session['student_id'],))
    data = cur.fetchone()

    if not data:
        data = {
            "machine_1_status": "Yoxdur",
            "machine_2_status": "Yoxdur",
            "machine_3_status": "Yoxdur"
        }

    return ok(data=data)


@app.route('/get_notifications', methods=['GET'])
@login_required
@with_db
def get_notifications(cur):
    """Bildirişlər (elan, sorğu, cərimə sayı)."""
    user_id = session['student_id']

    cur.execute("SELECT COUNT(*) as count FROM contents WHERE status = 'Aktiv' AND type = 'announcement'")
    ann_count = cur.fetchone()['count']

    cur.execute("SELECT COUNT(*) as count FROM contents WHERE status = 'Aktiv' AND type = 'survey'")
    surv_count = cur.fetchone()['count']

    cur.execute("SELECT COUNT(*) as count FROM penalties WHERE student_id = %s AND status = 'Ödənilməmiş'", (user_id,))
    pen_count = cur.fetchone()['count']

    return ok(notifications=[
        {"title": "Aktiv Elanlar", "description": f"{ann_count} ədəd aktiv elanınız var.", "icon": "megaphone", "color": "info", "redirect": "announcements", "redirect_text": "Elanlar"},
        {"title": "Aktiv Anketlər", "description": f"{surv_count} ədəd ankent iştirakınızı gözləyir.", "icon": "clipboard-check", "color": "warning", "redirect": "announcements", "redirect_text": "Elanlar"},
        {"title": "Ödənişli Cərimələr", "description": f"{pen_count} ədəd ödənilməmiş cəriməniz var.", "icon": "alert-triangle", "color": "danger", "redirect": "payments", "redirect_text": "Ödənişlər"}
    ])


@app.route('/get_penalties', methods=['GET'])
@login_required
@with_db
def get_penalties(cur):
    """Tələbənin cərimə siyahısı."""
    cur.execute("""
        SELECT id, amount, reason, status
        FROM penalties
        WHERE student_id = %s
        ORDER BY created_at DESC
    """, (session['student_id'],))
    penalties = cur.fetchall()
    return ok(penalties=penalties)


@app.route('/get_profile', methods=['GET'])
@login_required
@with_db
def get_profile(cur):
    """Tələbə profil məlumatları."""
    sql = """
        SELECT s.id, s.ad_soyad, s.email, s.ixtisas, s.kurs, s.api_key, s.ev_deyisme_isteyi,
               p.yuxu_rejimi, p.temizlik, p.sosial_munasibet, p.hayat_terzi
        FROM students s
        LEFT JOIN students_profiles p ON s.id = p.student_id
        WHERE s.id = %s
    """
    cur.execute(sql, (session['student_id'],))
    data = cur.fetchone()
    return ok(data=data)


@app.route('/get_roommates', methods=['GET'])
@login_required
@with_db
def get_roommates(cur):
    """Otaq yoldaşı axtarışı (ev dəyişmək istəyən tələbələr)."""
    cur.execute("""
        SELECT s.id, s.ad_soyad, s.ixtisas,
               p.yuxu_rejimi, p.temizlik, p.sosial_munasibet, p.hayat_terzi
        FROM students s
        LEFT JOIN students_profiles p ON s.id = p.student_id
        WHERE s.ev_deyisme_isteyi = 1 AND s.id != %s
    """, (session['student_id'],))
    roommates = cur.fetchall()
    return ok(roommates=roommates)


# ---------------------------------------------------------------------------
# Mutations (POST)
# ---------------------------------------------------------------------------

@app.route('/submit_application', methods=['POST'])
@login_required
@with_db
def submit_application(cur):
    """Yeni ərizə göndər."""
    user_id = session['student_id']
    data = request.get_json() or {}

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
    """Ərizəni yenilə."""
    user_id = session['student_id']
    data = request.get_json() or {}

    app_id = data.get('id', 0)
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
    """Ərizəni sil."""
    user_id = session['student_id']
    data = request.get_json() or {}
    app_id = data.get('id', 0)

    cur.execute("DELETE FROM applications WHERE id = %s AND student_id = %s", (app_id, user_id))
    return ok(message="Müraciət silindi!")


@app.route('/update_profile', methods=['POST'])
@login_required
@with_db
def update_profile(cur):
    """Profili yenilə."""
    data = request.get_json() or {}
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

    return ok(message="Profil yeniləndi!")


@app.route('/update_api_key', methods=['POST'])
@login_required
@with_db
def update_api_key(cur):
    """Yeni API açarı yarat."""
    new_key = secrets.token_hex(16)
    cur.execute("UPDATE students SET api_key = %s WHERE id = %s", (new_key, session['student_id']))
    return ok(api_key=new_key, message="API açarı yeniləndi!")


@app.route('/ai_handler', methods=['POST'])
@login_required
def ai_handler():
    """AI köməkçi (chat və ya otaq yoldaşı uyğunluğu)."""
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

    data = request.get_json() or {}
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
        target_id = data.get('target_id', 0)

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
