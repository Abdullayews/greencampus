import os
import pymysql
from pymysql.cursors import DictCursor
from pymysql.err import OperationalError

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 4000)),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
}

if os.getenv("DB_SSL", "true").lower() in ("true", "1", "yes"):
    DB_CONFIG["ssl"] = {"ssl": True}


def get_db_connection():
    """DB bağlantısı yaradır. Xəta olduqda exception atır (with_db tutacaq)."""
    return pymysql.connect(**DB_CONFIG)
