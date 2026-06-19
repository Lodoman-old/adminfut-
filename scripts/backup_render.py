#!/usr/bin/env python
"""
Backup data from Render PostgreSQL to a local JSON file.

Usage:
    1. Get your Render DATABASE_URL from Render Dashboard > Database > Connections
    2. Create .env.render in the project root with:
         DATABASE_URL=postgres://user:password@host:port/dbname
    3. Run: python scripts/backup_render.py
"""
import os, sys, subprocess, json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env.render"
BACKUP_DIR = BASE_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

if not ENV_FILE.exists():
    print("No .env.render found. Create one with:")
    print("    DATABASE_URL=postgres://user:password@host:port/dbname")
    sys.exit(1)

# Read env file (simple key=value)
with open(ENV_FILE) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

if not os.environ.get("DATABASE_URL"):
    print("DATABASE_URL not found in .env.render")
    sys.exit(1)

print("Connecting to Render PostgreSQL and dumping data...")

# Exclude: django sessions, migrations history, admin logs (they're transient)
EXCLUDE = [
    "sessions", "admin", "contenttypes", "auth.Permission",
]

EXCLUDE_ARGS = []
for app in EXCLUDE:
    EXCLUDE_ARGS.extend(["-e", app])

cmd = [
    sys.executable, "manage.py", "dumpdata",
    "--natural-foreign", "--natural-primary",
    "--indent", "2",
    "--output", str(BACKUP_DIR / "render_backup.json"),
] + EXCLUDE_ARGS

result = subprocess.run(cmd, cwd=BASE_DIR)
if result.returncode == 0:
    print(f"Backup saved to: {BACKUP_DIR / 'render_backup.json'}")
    # Also save a timestamped copy
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    ts_path = BACKUP_DIR / f"render_backup_{ts}.json"
    import shutil
    shutil.copy(BACKUP_DIR / "render_backup.json", ts_path)
    print(f"Timestamped copy: {ts_path}")
else:
    print("Backup failed!")
    sys.exit(1)
