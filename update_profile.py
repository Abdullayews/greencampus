from flask import session, request, jsonify
from config import get_db_connection

def update_profile_route():
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