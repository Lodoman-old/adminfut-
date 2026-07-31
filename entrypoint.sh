#!/usr/bin/env bash
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Running seed (roles, admin, conceptos)..."
python manage.py seed

echo "Creating superuser if needed..."
python manage.py shell -c "
from accounts.models import Usuario
if not Usuario.objects.filter(is_superuser=True).exists():
    Usuario.objects.create_superuser('admin', 'admin@admin.com', 'admin123')
    print('Superuser created: admin / admin123')
else:
    print('Superuser already exists.')
" 2>/dev/null || true

echo "Starting server..."
exec gunicorn league_project.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers ${GUNICORN_WORKERS:-4} \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --access-logfile - \
    --error-logfile -
