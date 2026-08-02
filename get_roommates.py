from flask import session, jsonify
from config import get_db_connection

def get_roommates_route():
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