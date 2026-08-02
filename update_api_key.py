import secrets
from flask import session, jsonify
from config import get_db_connection

def update_api_key_route():
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