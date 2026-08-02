from flask import session, request, jsonify
from config import get_db_connection

def delete_application_route():
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