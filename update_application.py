from flask import session, request, jsonify
from config import get_db_connection

def update_application_route():
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