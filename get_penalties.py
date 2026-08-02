from flask import session, jsonify
from config import get_db_connection

def get_penalties_route():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})
    
    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, amount, reason, status 
                FROM penalties 
                WHERE student_id = %s 
                ORDER BY created_at DESC
            """, (session['user_id'],))
            penalties = cursor.fetchall()
            return jsonify({"success": True, "penalties": penalties})
    except Exception as e:
        return jsonify({"success": False, "message": f"Cərimələr gətirilə bilmədi: {e}"})
    finally:
        conn.close()