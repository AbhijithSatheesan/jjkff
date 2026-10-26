#!/bin/sh
set -e

python manage.py migrate --noinput

python manage.py shell -c "
from core.models import WindForecast, WindActual
from django.core.management import call_command

if not WindForecast.objects.exists() and not WindActual.objects.exists():
    call_command('loaddata', 'wind_history')
"

exec gunicorn gridbricks.wsgi:application \
    --bind "0.0.0.0:${PORT:-8080}"