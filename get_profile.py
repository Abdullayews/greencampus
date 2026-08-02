from flask import session, jsonify
from config import get_db_connection

def get_profile_route():
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