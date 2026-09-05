import os

import pymysql
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB

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

# ---------------------------------------------------------------------------
# Connection Pool (DBUtils)
# Hər request yeni TCP+SSL bağlantısı açmaq (TiDB-ə ~200-400ms) əvəzinə
# bağlantılar pool-dan götürülüb təkrar istifadə olunur.
# Vacib: pool bağlantısında close() onu REAL bağlamır, pool-a QAYTARIR —
# ona görə app.py-dəki with_db decorator-u heç bir dəyişiklik tələb etmir.
# ---------------------------------------------------------------------------
POOL = PooledDB(
    creator=pymysql,
    maxconnections=int(os.getenv("DB_POOL_MAX", 10)),
    mincached=2,
    maxcached=int(os.getenv("DB_POOL_CACHED", 5)),
    blocking=True,   # pool doludursa gözlə (xəta yox)
    ping=1,          # hər götürmədə bağlantı sağlamlığını yoxla
    **DB_CONFIG
)


def get_db_connection():
    """Pool-dan bağlantı alır. Xəta tutulmur — with_db tutacaq."""
    return POOL.connection()
