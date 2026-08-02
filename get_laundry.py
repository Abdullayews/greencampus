from flask import session, jsonify
from config import get_db_connection

def get_laundry_route():
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