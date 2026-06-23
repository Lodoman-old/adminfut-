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

# Add guest registration columns to league_devicetoken if missing
python -c "
import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'league_project.settings'
django.setup()
from django.db import connection
with connection.cursor() as c:
    for col in ['es_invitado', 'nombre', 'telefono']:
        c.execute(\"\"\"SELECT 1 FROM information_schema.columns WHERE table_name='league_devicetoken' AND column_name='%s'\"\"\" % col)
        if not c.fetchone():
            if col == 'es_invitado':
                c.execute(\"ALTER TABLE league_devicetoken ADD COLUMN es_invitado boolean NOT NULL DEFAULT false\")
            elif col == 'nombre':
                c.execute(\"ALTER TABLE league_devicetoken ADD COLUMN nombre varchar(100) NOT NULL DEFAULT ''\")
            elif col == 'telefono':
                c.execute(\"ALTER TABLE league_devicetoken ADD COLUMN telefono varchar(20) NOT NULL DEFAULT ''\")
            print('Columna %s agregada a league_devicetoken.' % col)
    # M2M table for categorias
    c.execute(\"\"\"SELECT 1 FROM information_schema.tables WHERE table_name='league_devicetoken_categorias'\"\"\")
    if not c.fetchone():
        c.execute('''CREATE TABLE league_devicetoken_categorias (
            id bigserial NOT NULL PRIMARY KEY,
            devicetoken_id bigint NOT NULL REFERENCES league_devicetoken(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
            categoria_id bigint NOT NULL REFERENCES league_categoria(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
            UNIQUE(devicetoken_id, categoria_id)
        )''')
        print('Tabla league_devicetoken_categorias creada.')
    # categoria_preferida on accounts_usuario
    c.execute(\"\"\"SELECT 1 FROM information_schema.columns WHERE table_name='accounts_usuario' AND column_name='categoria_preferida_id'\"\"\")
    if not c.fetchone():
        c.execute(\"ALTER TABLE accounts_usuario ADD COLUMN categoria_preferida_id bigint NULL REFERENCES league_categoria(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED\")
        print('Columna categoria_preferida_id agregada a accounts_usuario.')
" 2>&1

# If the recordatorio_30min_enviado column doesn't exist, add it directly
python -c "
import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'league_project.settings'
django.setup()
from django.db import connection
with connection.cursor() as c:
    c.execute(\"\"\"SELECT 1 FROM information_schema.columns WHERE table_name='league_partido' AND column_name='recordatorio_30min_enviado'\"\"\")
    if not c.fetchone():
        c.execute(\"ALTER TABLE league_partido ADD COLUMN recordatorio_30min_enviado boolean NOT NULL DEFAULT false\")
        from django.db.migrations.recorder import MigrationRecorder
        MigrationRecorder.Migration.objects.get_or_create(app='league', name='0053_partido_recordatorio_30min_enviado')
        print('Columna recordatorio_30min_enviado agregada directamente y migración marcada como aplicada.')
    else:
        print('Columna recordatorio_30min_enviado ya existe.')
" 2>&1

# If the finance_caja table doesn't exist, create it
python -c "
import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'league_project.settings'
django.setup()
from django.db import connection
with connection.cursor() as c:
    c.execute(\"\"\"SELECT 1 FROM information_schema.tables WHERE table_name='finance_caja'\"\"\")
    if not c.fetchone():
        c.execute('''CREATE TABLE finance_caja (
            id bigserial NOT NULL PRIMARY KEY,
            fecha_apertura timestamptz NOT NULL DEFAULT now(),
            fecha_cierre timestamptz NULL,
            monto_inicial numeric(10,2) NOT NULL DEFAULT 0,
            monto_final_real numeric(10,2) NULL,
            estado varchar(10) NOT NULL DEFAULT 'ABIERTA',
            observaciones text NOT NULL DEFAULT '',
            usuario_id integer NULL REFERENCES accounts_usuario(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
        )''')
        c.execute('CREATE INDEX finance_caja_usuario_id ON finance_caja(usuario_id)')
        # Add caja_id column to ingreso
        c.execute(\"\"\"SELECT 1 FROM information_schema.columns WHERE table_name='finance_ingreso' AND column_name='caja_id'\"\"\")
        if not c.fetchone():
            c.execute('ALTER TABLE finance_ingreso ADD COLUMN caja_id integer NULL REFERENCES finance_caja(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED')
            c.execute('CREATE INDEX finance_ingreso_caja_id ON finance_ingreso(caja_id)')
        from django.db.migrations.recorder import MigrationRecorder
        MigrationRecorder.Migration.objects.get_or_create(app='finance', name='0012_caja_model_and_ingreso_caja_fk')
        print('Tabla finance_caja creada directamente y migración marcada como aplicada.')
    else:
        print('Tabla finance_caja ya existe.')
" 2>&1

exec gunicorn league_project.wsgi --bind 0.0.0.0:$PORT --workers 4 --timeout 120
