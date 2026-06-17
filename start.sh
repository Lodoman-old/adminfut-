#!/usr/bin/env bash
set -e
python manage.py migrate --noinput
exec gunicorn league_project.wsgi --bind 0.0.0.0:$PORT --workers 4 --timeout 120
