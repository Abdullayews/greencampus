from flask import session, request, jsonify
from config import get_db_connection

def submit_application_route():
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