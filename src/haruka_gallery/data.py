import sqlite3
from pathlib import Path

from .config import gallery_config

if not gallery_config.data_dir.exists():
    gallery_config.data_dir.mkdir(parents=True, exist_ok=True)
db = sqlite3.connect(gallery_config.data_dir / "images.db")
DB_VERSION = 1

try:
    cursor = db.execute("SELECT version FROM meta LIMIT 1")
    row = cursor.fetchone()
    if row is None:
        current_version = 0
    else:
        current_version = row[0]
except:
    current_version = 0
if current_version > DB_VERSION:
    from nonebot.log import logger

    logger.warning("Database version is newer than application supports. Please update the application.")

if current_version == 0:
    with open(str(Path(__file__).resolve().parent / "sql" / "init.sql"), "r", encoding="utf-8") as f:
        init_sql = f.read()
        db.executescript(init_sql)
        current_version = 1
