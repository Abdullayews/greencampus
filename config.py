import pymysql
from pymysql.cursors import DictCursor
from pymysql.err import OperationalError
from flask import jsonify

DB_CONFIG = {
    "host": "sql102.infinityfree.com",
    "database": "if0_42430459_students",
    "user": "if0_42430459",
    "password": "HhYFx4Ser2RXZA",
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}

def get_db_connection():
    try:
        return pymysql.connect(**DB_CONFIG)
    except OperationalError as e:
        return jsonify({"success": False, "message": f"DB Bağlantı xətası: {e}"}), 500