from flask import session, jsonify
from config import get_db_connection

def get_contents_route():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})
    
    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, type, title, description, priority, status 
                FROM contents 
                WHERE status = 'Aktiv' 
                ORDER BY created_at DESC
            """)
            contents = cursor.fetchall()
            return jsonify({"success": True, "contents": contents})
    except Exception as e:
        return jsonify({"success": False, "message": f"Məlumatlar gətirilə bilmədi: {e}"})
    finally:
        conn.close()