from flask import session, jsonify
from datetime import datetime
from config import get_db_connection

def get_canteen_route():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur"})
    
    days_az = {
        1: 'Bazar ertəsi', 2: 'Çərşənbə axşamı', 3: 'Çərşənbə',
        4: 'Cümə axşamı', 5: 'Cümə', 6: 'Şənbə', 7: 'Bazar'
    }
    today_num = datetime.now().isoweekday()
    today_name = days_az.get(today_num, 'Bazar')
    
    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT location, meal_name FROM canteen_menu WHERE day_of_week = %s", (today_num,))
            meals = cursor.fetchall()
            
            dorm_meal = 'Restoran bağlıdır'
            uni_meal = 'Restoran bağlıdır'
            
            for meal in meals:
                if meal['location'] == 'Yataqxana':
                    dorm_meal = meal['meal_name']
                if meal['location'] == 'Universitet':
                    uni_meal = meal['meal_name']
            
            return jsonify({
                "success": True,
                "day": today_name,
                "dorm": dorm_meal,
                "uni": uni_meal
            })
    except Exception as e:
        return jsonify({"success": False, "message": f"Xəta: {e}"})
    finally:
        conn.close()