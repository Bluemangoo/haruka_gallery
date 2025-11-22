import sqlite3
from pathlib import Path

from .config import gallery_config

if not gallery_config.data_dir.exists():
    gallery_config.data_dir.mkdir(parents=True, exist_ok=True)
db = sqlite3.connect(gallery_config.data_dir / "images.db")
DB_VERSION = 2

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

migration_map = {
    0: "init.sql",
    1: "migrate_1_2.sql",
}

while current_version < DB_VERSION:
    migration_file = migration_map.get(current_version)
    if migration_file is not None:
        with open(str(Path(__file__).resolve().parent / "sql" / migration_file), "r", encoding="utf-8") as f:
            migration_sql = f.read()
            db.executescript(migration_sql)
            db.commit()
            row = db.execute("SELECT version FROM meta LIMIT 1").fetchone()
            current_version = row[0]
            continue
    raise RuntimeError(f"Unrecognized database version: {current_version}")
