#!/bin/sh
set -eu

mkdir -p /app/data /app/media /app/staticfiles

python manage.py check --deploy --fail-level WARNING
python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn foxcons_oidc_bridge.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout "${GUNICORN_TIMEOUT:-60}" \
  --access-logfile - \
  --error-logfile -
