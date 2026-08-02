from flask import session, jsonify
from config import get_db_connection

def get_notifications_route():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})
    
    user_id = session['user_id']
    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM contents WHERE status = 'Aktiv' AND type = 'announcement'")
            ann_count = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM contents WHERE status = 'Aktiv' AND type = 'survey'")
            surv_count = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM penalties WHERE student_id = %s AND status = 'Ödənilməmiş'", (user_id,))
            pen_count = cursor.fetchone()['count']
            
            return jsonify({
                "success": True,
                "notifications": [
                    {"title": "Aktiv Elanlar", "description": f"{ann_count} ədəd aktiv elanınız var.", "icon": "megaphone", "color": "info", "redirect": "announcements", "redirect_text": "Elanlar"},
                    {"title": "Aktiv Anketlər", "description": f"{surv_count} ədəd ankent iştirakınızı gözləyir.", "icon": "clipboard-check", "color": "warning", "redirect": "announcements", "redirect_text": "Elanlar"},
                    {"title": "Ödənişli Cərimələr", "description": f"{pen_count} ədəd ödənilməmiş cəriməniz var.", "icon": "alert-triangle", "color": "danger", "redirect": "payments", "redirect_text": "Ödənişlər"}
                ]
            })
    except Exception as e:
        return jsonify({"success": False, "message": f"Xəta: {e}"})
    finally:
        conn.close()