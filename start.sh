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

# If the DeviceToken table doesn't exist, create it directly
python -c "
import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'league_project.settings'
django.setup()
from django.db import connection
with connection.cursor() as c:
    c.execute(\"\"\"SELECT 1 FROM information_schema.tables WHERE table_name='league_devicetoken'\"\"\")
    if not c.fetchone():
        c.execute('''CREATE TABLE league_devicetoken (
            id bigserial NOT NULL PRIMARY KEY,
            token varchar(500) NOT NULL UNIQUE,
            plataforma varchar(10) NOT NULL DEFAULT 'android',
            activo boolean NOT NULL DEFAULT true,
            creado timestamptz NOT NULL DEFAULT now(),
            actualizado timestamptz NOT NULL DEFAULT now(),
            usuario_id integer NULL REFERENCES accounts_usuario(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )''')
        # Create index
        c.execute('CREATE INDEX league_devicetoken_usuario_id ON league_devicetoken(usuario_id)')
        # Mark migration as applied
        from django.db.migrations.recorder import MigrationRecorder
        MigrationRecorder.Migration.objects.get_or_create(app='league', name='0052_devicetoken')
        print('Tabla league_devicetoken creada directamente y migración marcada como aplicada.')
    else:
        print('Tabla league_devicetoken ya existe.')
" 2>&1

exec gunicorn league_project.wsgi --bind 0.0.0.0:$PORT --workers 4 --timeout 120
