from flask import session, jsonify
from config import get_db_connection

def get_applications_route():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})
    
    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn
    
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT id, basliq, muraciet, priority, status, 
                       DATE_FORMAT(created_at, '%%d.%%m.%%Y') as tarix 
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