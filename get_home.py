from flask import session, jsonify
from config import get_db_connection

def get_home_route():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})
    
    user_id = session['user_id']
    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM rooms WHERE telebe_1_id = %s OR telebe_2_id = %s OR telebe_3_id = %s OR telebe_4_id = %s OR telebe_5_id = %s OR telebe_6_id = %s",
                (user_id, user_id, user_id, user_id, user_id, user_id)
            )
            room = cursor.fetchone()
            
            if not room:
                return jsonify({"success": False, "message": "Sizin otaq tapılmadı"})
            
            room_number = room['id']
            student_ids = []
            positions = {}
            
            for i in range(1, 7):
                col = f"telebe_{i}_id"
                if room.get(col):
                    student_ids.append(room[col])
                    positions[room[col]] = i
            
            if not student_ids:
                return jsonify({"success": False, "message": "Otaqda tələbə yoxdur"})
            
            placeholders = ','.join(['%s'] * len(student_ids))
            cursor.execute(f"SELECT id, ad_soyad FROM students WHERE id IN ({placeholders}) ORDER BY ad_soyad ASC", tuple(student_ids))
            students = cursor.fetchall()
            
            roommates = []
            for student in students:
                sid = student['id']
                pos = positions[sid]
                items = [
                    {"item_name": "Yataq", "status": room.get(f"yataq_{pos}_status", 'Bilinmir')},
                    {"item_name": "Oturacaq", "status": room.get(f"oturacaq_{pos}_status", 'Bilinmir')},
                    {"item_name": "Şkaf", "status": room.get(f"skaf_{pos}_status", 'Bilinmir')}
                ]
                items.sort(key=lambda x: x['item_name'])
                roommates.append({
                    "id": sid,
                    "ad_soyad": student['ad_soyad'],
                    "items": items
                })
            
            return jsonify({"success": True, "room_number": room_number, "roommates": roommates})
    except Exception as e:
        return jsonify({"success": False, "message": f"Xəta: {e}"})
    finally:
        conn.close()