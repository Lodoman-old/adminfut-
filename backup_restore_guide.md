# Backup & Restore Render Database

## Backup (Render PostgreSQL → local JSON)

1. Get your Render database URL:
   - Render Dashboard > Database > Info > Connections > External Database URL

2. Create `.env.render` in project root:
   ```
   DATABASE_URL=postgres://user:password@host:port/dbname
   ```
   (`.env.render` is gitignored — use `.env.render.example` as template)

3. Run backup:
   ```bash
   python scripts/backup_render.py
   ```
   Saves to `backups/render_backup.json` (and a timestamped copy).

## Restore (local JSON → local SQLite)

```bash
python scripts/restore_render.py [backups/backup_file.json]
```

**WARNING:** Overwrites your local SQLite database.

## Schema changes

Migrations handle schema automatically:
- `python manage.py makemigrations` → commit → push → Render auto-deploys + `migrate`
- The `web: bash start.sh` in Procfile runs `migrate` on every deploy
