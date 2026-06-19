#!/usr/bin/env python
"""
Restore a Render backup JSON to the local SQLite database.

Usage:
    python scripts/restore_render.py [backup_file]

If no backup_file is given, uses backups/render_backup.json (the latest).
"""
import os, sys, subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = BASE_DIR / "backups"

if len(sys.argv) > 1:
    backup_file = Path(sys.argv[1])
else:
    backup_file = BACKUP_DIR / "render_backup.json"

if not backup_file.exists():
    print(f"Backup file not found: {backup_file}")
    print("Run scripts/backup_render.py first.")
    sys.exit(1)

print(f"Restoring from: {backup_file}")
print("WARNING: This will overwrite your LOCAL database (SQLite)!")
confirm = input("Continue? (y/N): ")
if confirm.lower() != "y":
    print("Cancelled.")
    sys.exit(0)

cmd = [
    sys.executable, "manage.py", "loaddata",
    str(backup_file),
]
result = subprocess.run(cmd, cwd=BASE_DIR)
if result.returncode == 0:
    print("Restore complete!")
else:
    print("Restore failed!")
    sys.exit(1)
