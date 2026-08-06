import os
import re
import secrets
from datetime import datetime

import requests
from flask import Flask, session, request, jsonify, redirect, render_template
from flasgger import Swagger

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

Swagger(app)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@app.route('/', methods=['GET'])
def index():
    """
    Tələbə portalı ana səhifəsi
    ---
    tags:
      - Səhifələr
    responses:
      200:
        description: HTML səhifə
    """
    user_name = session.get('user_name', '')
    user_ixtisas = session.get('ixtisas', '')
    user_kurs = session.get('kurs', '')
    user_otaq = session.get('otaq_nomresi', '')
    is_logged_in = 'user_id' in session

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
    """
    Tələbə girişi
    ---
    tags:
      - Auth
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            email:
              type: string
              example: "test@example.com"
            sifre:
              type: string
              example: "12345"
    responses:
      200:
        description: Giriş nəticəsi
        schema:
          type: object
          properties:
            success:
              type: boolean
            user:
              type: object
            message:
              type: string
    """
    data = request.get_json() or {}
    email = data.get('email', '')
    sifre = data.get('sifre', '')

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

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
                    session['user_id'] = user['id']
                    session['user_name'] = user['ad_soyad']
                    session['ixtisas'] = user['ixtisas']
                    session['kurs'] = user['kurs']
                    session['otaq_nomresi'] = user.get('otaq_nomresi') or 'Yoxdur'

                    user.pop('sifre', None)
                    return jsonify({"success": True, "user": user})
                else:
                    return jsonify({"success": False, "message": "Şifrə yanlışdır!"})
            else:
                return jsonify({"success": False, "message": f"Bu email databasedə yoxdur: {email}"})
    except Exception as e:
        return jsonify({"success": False, "message": f"DB Xətası: {e}"})
    finally:
        conn.close()


@app.route('/logout', methods=['GET'])
def logout():
    """
    Tələbə çıxışı
    ---
    tags:
      - Auth
    responses:
      302:
        description: Ana səhifəyə yönləndirir
    """
    session.clear()
    return redirect('/')


# ---------------------------------------------------------------------------
# Data (GET)
# ---------------------------------------------------------------------------

@app.route('/get_home', methods=['GET'])
def get_home():
    """
    Tələbənin otaq və otaq yoldaşları məlumatı
    ---
    tags:
      - Dashboard
    responses:
      200:
        description: Otaq məlumatları
        schema:
          type: object
          properties:
            success:
              type: boolean
            room_number:
              type: string
            roommates:
              type: array
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    user_id = session['user_id']
    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM rooms WHERE telebe_1_id = %s OR telebe_2_id = %s OR telebe_3_id = %s OR telebe_4_id = %s OR telebe_5_id = %s OR telebe_6_id = %s",
                (user_id, user_id, user_id, user_id, user_id, user_id)
            )
            room = cursor.fetchone()

            if not room:
                return jsonify({"success": False, "message": "Sizin otaq tapılmadı"})

            room_number = room['id']
            student_ids = []
            positions = {}

            for i in range(1, 7):
                col = f"telebe_{i}_id"
                if room.get(col):
                    student_ids.append(room[col])
                    positions[room[col]] = i

            if not student_ids:
                return jsonify({"success": False, "message": "Otaqda tələbə yoxdur"})

            placeholders = ','.join(['%s'] * len(student_ids))
            cursor.execute(f"SELECT id, ad_soyad FROM students WHERE id IN ({placeholders}) ORDER BY ad_soyad ASC", tuple(student_ids))
            students = cursor.fetchall()

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

            return jsonify({"success": True, "room_number": room_number, "roommates": roommates})
    except Exception as e:
        return jsonify({"success": False, "message": f"Xəta: {e}"})
    finally:
        conn.close()


@app.route('/get_applications', methods=['GET'])
def get_applications():
    """
    Tələbənin ərizə siyahısı
    ---
    tags:
      - Ərizələr
    responses:
      200:
        description: Ərizə siyahısı
        schema:
          type: object
          properties:
            success:
              type: boolean
            applications:
              type: array
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT id, basliq, muraciet, priority, status,
                       DATE_FORMAT(created_at, '%d.%m.%Y') as tarix
                FROM applications
                WHERE student_id = %s
                ORDER BY created_at DESC
            """
            cursor.execute(sql, (session['user_id'],))
            applications = cursor.fetchall()
            return jsonify({"success": True, "applications": applications})
    except Exception as e:
        return jsonify({"success": False, "message": f"Xəta: {e}"})
    finally:
        conn.close()


@app.route('/get_canteen', methods=['GET'])
def get_canteen():
    """
    Bugünkü yeməkxana menyusu
    ---
    tags:
      - Yeməkxana
    responses:
      200:
        description: Menyu məlumatları
        schema:
          type: object
          properties:
            success:
              type: boolean
            day:
              type: string
            dorm:
              type: string
            uni:
              type: string
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    days_az = {
        1: 'Bazar ertəsi', 2: 'Çərşənbə axşamı', 3: 'Çərşənbə',
        4: 'Cümə axşamı', 5: 'Cümə', 6: 'Şənbə', 7: 'Bazar'
    }
    today_num = datetime.now().isoweekday()
    today_name = days_az.get(today_num, 'Bazar')

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT location, meal_name FROM canteen_menu WHERE day_of_week = %s", (today_num,))
            meals = cursor.fetchall()

            dorm_meal = 'Restoran bağlıdır'
            uni_meal = 'Restoran bağlıdır'

            for meal in meals:
                if meal['location'] == 'Yataqxana':
                    dorm_meal = meal['meal_name']
                if meal['location'] == 'Universitet':
                    uni_meal = meal['meal_name']

            return jsonify({
                "success": True,
                "day": today_name,
                "dorm": dorm_meal,
                "uni": uni_meal
            })
    except Exception as e:
        return jsonify({"success": False, "message": f"Xəta: {e}"})
    finally:
        conn.close()


@app.route('/get_contents', methods=['GET'])
def get_contents():
    """
    Aktiv elan və sorğu siyahısı
    ---
    tags:
      - Məzmun
    responses:
      200:
        description: Elan/sorğu siyahısı
        schema:
          type: object
          properties:
            success:
              type: boolean
            contents:
              type: array
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, type, title, description, priority, status
                FROM contents
                WHERE status = 'Aktiv'
                ORDER BY created_at DESC
            """)
            contents = cursor.fetchall()
            return jsonify({"success": True, "contents": contents})
    except Exception as e:
        return jsonify({"success": False, "message": f"Məlumatlar gətirilə bilmədi: {e}"})
    finally:
        conn.close()


@app.route('/get_laundry', methods=['GET'])
def get_laundry():
    """
    Tələbənin camaşırxana statusu
    ---
    tags:
      - Camaşırxana
    responses:
      200:
        description: Maşın statusları
        schema:
          type: object
          properties:
            success:
              type: boolean
            data:
              type: object
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM laundry WHERE student_id = %s", (session['user_id'],))
            data = cursor.fetchone()

            if not data:
                data = {
                    "machine_1_status": "Yoxdur",
                    "machine_2_status": "Yoxdur",
                    "machine_3_status": "Yoxdur"
                }

            return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": f"Xəta: {e}"})
    finally:
        conn.close()


@app.route('/get_notifications', methods=['GET'])
def get_notifications():
    """
    Bildirişlər (elan, sorğu, cərimə sayı)
    ---
    tags:
      - Bildirişlər
    responses:
      200:
        description: Bildiriş siyahısı
        schema:
          type: object
          properties:
            success:
              type: boolean
            notifications:
              type: array
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    user_id = session['user_id']
    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM contents WHERE status = 'Aktiv' AND type = 'announcement'")
            ann_count = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM contents WHERE status = 'Aktiv' AND type = 'survey'")
            surv_count = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM penalties WHERE student_id = %s AND status = 'Ödənilməmiş'", (user_id,))
            pen_count = cursor.fetchone()['count']

            return jsonify({
                "success": True,
                "notifications": [
                    {"title": "Aktiv Elanlar", "description": f"{ann_count} ədəd aktiv elanınız var.", "icon": "megaphone", "color": "info", "redirect": "announcements", "redirect_text": "Elanlar"},
                    {"title": "Aktiv Anketlər", "description": f"{surv_count} ədəd ankent iştirakınızı gözləyir.", "icon": "clipboard-check", "color": "warning", "redirect": "announcements", "redirect_text": "Elanlar"},
                    {"title": "Ödənişli Cərimələr", "description": f"{pen_count} ədəd ödənilməmiş cəriməniz var.", "icon": "alert-triangle", "color": "danger", "redirect": "payments", "redirect_text": "Ödənişlər"}
                ]
            })
    except Exception as e:
        return jsonify({"success": False, "message": f"Xəta: {e}"})
    finally:
        conn.close()


@app.route('/get_penalties', methods=['GET'])
def get_penalties():
    """
    Tələbənin cərimə siyahısı
    ---
    tags:
      - Cərimələr
    responses:
      200:
        description: Cərimə siyahısı
        schema:
          type: object
          properties:
            success:
              type: boolean
            penalties:
              type: array
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, amount, reason, status
                FROM penalties
                WHERE student_id = %s
                ORDER BY created_at DESC
            """, (session['user_id'],))
            penalties = cursor.fetchall()
            return jsonify({"success": True, "penalties": penalties})
    except Exception as e:
        return jsonify({"success": False, "message": f"Cərimələr gətirilə bilmədi: {e}"})
    finally:
        conn.close()


@app.route('/get_profile', methods=['GET'])
def get_profile():
    """
    Tələbə profil məlumatları
    ---
    tags:
      - Profil
    responses:
      200:
        description: Profil məlumatları
        schema:
          type: object
          properties:
            success:
              type: boolean
            data:
              type: object
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT s.ad_soyad, s.email, s.ixtisas, s.kurs, s.api_key, s.ev_deyisme_isteyi,
                       p.yuxu_rejimi, p.temizlik, p.sosial_munasibet, p.hayat_terzi
                FROM students s
                LEFT JOIN students_profiles p ON s.id = p.student_id
                WHERE s.id = %s
            """
            cursor.execute(sql, (session['user_id'],))
            data = cursor.fetchone()
            return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        conn.close()


@app.route('/get_roommates', methods=['GET'])
def get_roommates():
    """
    Otaq yoldaşı axtarışı (ev dəyişmək istəyən tələbələr)
    ---
    tags:
      - Otaq Yoldaşları
    responses:
      200:
        description: Tələbə siyahısı
        schema:
          type: object
          properties:
            success:
              type: boolean
            roommates:
              type: array
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT s.id, s.ad_soyad, s.ixtisas,
                       p.yuxu_rejimi, p.temizlik, p.sosial_munasibet, p.hayat_terzi
                FROM students s
                LEFT JOIN students_profiles p ON s.id = p.student_id
                WHERE s.ev_deyisme_isteyi = 1 AND s.id != %s
            """, (session['user_id'],))
            roommates = cursor.fetchall()
            return jsonify({"success": True, "roommates": roommates})
    except Exception as e:
        return jsonify({"success": False, "message": f"Siyahı gətirilə bilmədi: {e}"})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Mutations (POST)
# ---------------------------------------------------------------------------

@app.route('/submit_application', methods=['POST'])
def submit_application():
    """
    Yeni ərizə göndər
    ---
    tags:
      - Ərizələr
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            basliq:
              type: string
            muraciet:
              type: string
            priority:
              type: string
              example: "Orta"
    responses:
      200:
        description: Nəticə
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    user_id = session['user_id']
    data = request.get_json() or {}

    basliq = (data.get('basliq') or '').strip()
    muraciet = (data.get('muraciet') or '').strip()
    priority = data.get('priority', 'Orta')

    if not basliq or not muraciet:
        return jsonify({"success": False, "message": "Başlıq və müraciət boş ola bilməz!"})

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM rooms WHERE telebe_1_id = %s OR telebe_2_id = %s OR telebe_3_id = %s OR telebe_4_id = %s OR telebe_5_id = %s OR telebe_6_id = %s",
                (user_id, user_id, user_id, user_id, user_id, user_id)
            )
            room = cursor.fetchone()
            room_number = room['id'] if room else 'Bilinmir'

            full_basliq = f"Otaq {room_number} - {basliq}"

            cursor.execute(
                "INSERT INTO applications (student_id, basliq, muraciet, priority) VALUES (%s, %s, %s, %s)",
                (user_id, full_basliq, muraciet, priority)
            )
            conn.commit()
            return jsonify({"success": True, "message": "Müraciət uğurla göndərildi!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Xəta: {e}"})
    finally:
        conn.close()


@app.route('/update_application', methods=['POST'])
def update_application():
    """
    Ərizəni yenilə
    ---
    tags:
      - Ərizələr
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            id:
              type: integer
            basliq:
              type: string
            muraciet:
              type: string
            priority:
              type: string
    responses:
      200:
        description: Nəticə
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    user_id = session['user_id']
    data = request.get_json() or {}

    app_id = data.get('id', 0)
    basliq = (data.get('basliq') or '').strip()
    muraciet = (data.get('muraciet') or '').strip()
    priority = data.get('priority', 'Orta')

    if not basliq or not muraciet:
        return jsonify({"success": False, "message": "Başlıq və müraciət boş ola bilməz!"})

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE applications SET basliq = %s, muraciet = %s, priority = %s WHERE id = %s AND student_id = %s",
                (basliq, muraciet, priority, app_id, user_id)
            )
            conn.commit()
            return jsonify({"success": True, "message": "Müraciət yeniləndi!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Xəta: {e}"})
    finally:
        conn.close()


@app.route('/delete_application', methods=['POST'])
def delete_application():
    """
    Ərizəni sil
    ---
    tags:
      - Ərizələr
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            id:
              type: integer
    responses:
      200:
        description: Nəticə
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    user_id = session['user_id']
    data = request.get_json() or {}
    app_id = data.get('id', 0)

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM applications WHERE id = %s AND student_id = %s", (app_id, user_id))
            conn.commit()
            return jsonify({"success": True, "message": "Müraciət silindi!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Xəta: {e}"})
    finally:
        conn.close()


@app.route('/update_profile', methods=['POST'])
def update_profile():
    """
    Profili yenilə
    ---
    tags:
      - Profil
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            email:
              type: string
            ixtisas:
              type: string
            kurs:
              type: string
            api_key:
              type: string
            ev_deyisme_isteyi:
              type: integer
            yuxu_rejimi:
              type: string
            temizlik:
              type: string
            sosial_munasibet:
              type: string
            hayat_terzi:
              type: string
    responses:
      200:
        description: Nəticə
        schema:
          type: object
          properties:
            success:
              type: boolean
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    data = request.get_json() or {}
    user_id = session['user_id']

    email = (data.get('email') or '').strip()
    ixtisas = (data.get('ixtisas') or '').strip()
    kurs = (data.get('kurs') or '1').strip()
    api_key = (data.get('api_key') or '').strip()
    ev_deyisme = 1 if data.get('ev_deyisme_isteyi') else 0

    yuxu = (data.get('yuxu_rejimi') or '').strip()
    temizlik = (data.get('temizlik') or '').strip()
    sosial = (data.get('sosial_munasibet') or '').strip()
    hayat = (data.get('hayat_terzi') or '').strip()

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE students SET email = %s, ixtisas = %s, kurs = %s, api_key = %s, ev_deyisme_isteyi = %s WHERE id = %s",
                (email, ixtisas, kurs, api_key, ev_deyisme, user_id)
            )

            cursor.execute("""
                INSERT INTO students_profiles (student_id, yuxu_rejimi, temizlik, sosial_munasibet, hayat_terzi)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                yuxu_rejimi = VALUES(yuxu_rejimi),
                temizlik = VALUES(temizlik),
                sosial_munasibet = VALUES(sosial_munasibet),
                hayat_terzi = VALUES(hayat_terzi)
            """, (user_id, yuxu, temizlik, sosial, hayat))

            conn.commit()
            return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": f"Xəta: {e}"})
    finally:
        conn.close()


@app.route('/update_api_key', methods=['POST'])
def update_api_key():
    """
    Yeni API açarı yarat
    ---
    tags:
      - Profil
    responses:
      200:
        description: Yeni API açarı
        schema:
          type: object
          properties:
            success:
              type: boolean
            api_key:
              type: string
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        new_key = secrets.token_hex(16)
        with conn.cursor() as cursor:
            cursor.execute("UPDATE students SET api_key = %s WHERE id = %s", (new_key, session['user_id']))
            conn.commit()
            return jsonify({"success": True, "api_key": new_key})
    except Exception as e:
        return jsonify({"success": False, "message": f"Xəta: {e}"})
    finally:
        conn.close()


@app.route('/ai_handler', methods=['POST'])
def ai_handler():
    """
    AI köməkçi (chat və ya otaq yoldaşı uyğunluğu)
    ---
    tags:
      - AI
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            type:
              type: string
              example: "chat"
            message:
              type: string
            history:
              type: array
            target_id:
              type: integer
    responses:
      200:
        description: AI cavabı
        schema:
          type: object
          properties:
            success:
              type: boolean
            reply:
              type: string
            score:
              type: integer
    """
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur. Zəhmət olmasa daxil olun."})

    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT api_key, ad_soyad FROM students WHERE id = %s", (session['user_id'],))
            user_data = cursor.fetchone()
    finally:
        conn.close()

    api_key = user_data.get('api_key', '') if user_data else ''
    istifadeci_adi = user_data.get('ad_soyad', 'Tələbə') if user_data else 'Tələbə'

    if not api_key:
        return jsonify({"success": False, "message": "API açarı tapılmadı! Zəhmət olmasa Profil bölməsindən şəxsi Gemini API açarınızı daxil edin."})

    data = request.get_json() or {}
    if not data or 'type' not in data:
        return jsonify({"success": False, "message": "Yanlış sorğu formatı."})

    model = "gemini-3.1-flash-lite"
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
            return jsonify({"success": False, "message": "Boş mesaj göndərilə bilməz."})
        contents.append({"role": "user", "parts": [{"text": current_msg}]})
        temperature = 0.7
        max_tokens = 250

    elif req_type == 'match':
        system_prompt = "Sən bir uyğunluq hesablama aparatısan. İstifadəçiyə yalnız 0 ilə 100 arasında tam rəqəm qaytarırsan."
        target_id = data.get('target_id', 0)

        conn = get_db_connection()
        if isinstance(conn, tuple):
            return conn
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT s.id, s.ad_soyad, p.yuxu_rejimi, p.temizlik, p.sosial_munasibet, p.hayat_terzi
                    FROM students s
                    LEFT JOIN students_profiles p ON s.id = p.student_id
                    WHERE s.id IN (%s, %s)
                """, (session['user_id'], target_id))
                users = cursor.fetchall()
        finally:
            conn.close()

        if len(users) < 2:
            return jsonify({"success": False, "message": "Tələbə məlumatları tapılmadı."})

        me = users[0]
        target = users[1]
        match_prompt = f"Tələbə 1 ({me['ad_soyad']}): Yuxu: {me['yuxu_rejimi']}, Təmizlik: {me['temizlik']}, Sosial: {me['sosial_munasibet']}, Həyat: {me['hayat_terzi']}.\n"
        match_prompt += f"Tələbə 2 ({target['ad_soyad']}): Yuxu: {target['yuxu_rejimi']}, Təmizlik: {target['temizlik']}, Sosial: {target['sosial_munasibet']}, Həyat: {target['hayat_terzi']}.\n"
        match_prompt += "Bu iki tələbənin otaq yoldaşı olaraq neçə faiz (0-100) uyğun olduğunu hesabla. Yalnız rəqəmi qaytar."

        contents.append({"role": "user", "parts": [{"text": match_prompt}]})
        temperature = 0.2
        max_tokens = 10
    else:
        return jsonify({"success": False, "message": "Yanlış sorğu növü."})

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
        return jsonify({"success": False, "message": "AI serverinə qoşulmaq mümkün olmadı."})

    if result.get('error'):
        return jsonify({"success": False, "message": f"AI Xətası: {result['error'].get('message', 'API açarı yanlış ola bilər!')}"})

    candidates = result.get('candidates', [])
    if not candidates or not candidates[0].get('content', {}).get('parts', [{}])[0].get('text'):
        return jsonify({"success": False, "message": "AI boş cavab qaytardı."})

    ai_text = candidates[0]['content']['parts'][0]['text']

    if req_type == 'match':
        numbers = re.findall(r'\d+', ai_text)
        score = int(numbers[0]) if numbers else 0
        score = max(0, min(100, score))
        return jsonify({"success": True, "score": score})
    else:
        return jsonify({"success": True, "reply": ai_text.strip()})


if __name__ == '__main__':
    app.run(debug=False)
