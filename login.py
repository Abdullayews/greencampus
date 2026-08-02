from flask import session, request, jsonify
from config import get_db_connection

def login_route():
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