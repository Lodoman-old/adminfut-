#!/usr/bin/env bash
set -e

# Apply pending migrations
python manage.py migrate --noinput 2>&1 || echo "migrate failed (non-fatal)"

# If the estado column still doesn't exist, add it directly
python -c "
import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'league_project.settings'
django.setup()
from django.db import connection
with connection.cursor() as c:
    c.execute(\"\"\"SELECT 1 FROM information_schema.columns WHERE table_name='league_jornada' AND column_name='estado'\"\"\")
    if not c.fetchone():
        c.execute(\"ALTER TABLE league_jornada ADD COLUMN estado VARCHAR(10) NOT NULL DEFAULT 'ACTIVA'\")
        c.execute(\"ALTER TABLE league_jornada ADD COLUMN motivo_suspension TEXT NOT NULL DEFAULT ''\")
        c.execute(\"ALTER TABLE league_jornada ADD COLUMN semanas_suspension INTEGER NULL\")
        # Mark migration as applied
        from django.db.migrations.recorder import MigrationRecorder
        MigrationRecorder.Migration.objects.get_or_create(app='league', name='0051_jornada_estado_jornada_motivo_suspension_and_more')
        print('Columnas agregadas directamente y migración marcada como aplicada.')
    else:
        print('Columnas ya existen.')
" 2>&1

exec gunicorn league_project.wsgi --bind 0.0.0.0:$PORT --workers 4 --timeout 120
