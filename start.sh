#!/usr/bin/env bash
# Startup for the deployed container. Runs from the repo root.
set -e
cd backend

# SQLite lives on the container's disk. On a free tier this disk is ephemeral (resets on redeploy/restart),
# which is fine for a demo. For persistent data, attach a disk or migrate to Postgres (see DEPLOY.md).
python manage.py init-db

# Optionally create an admin from environment variables (set ADMIN_EMAIL + ADMIN_PASSWORD + ADMIN_PIN in the host).
if [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
  python manage.py create-admin --email "$ADMIN_EMAIL" --name "${ADMIN_NAME:-Admin}" --password "$ADMIN_PASSWORD" --pin "${ADMIN_PIN:-246813}" || true
fi

# One worker keeps memory low for the free tier; raise --workers / --timeout on a bigger instance.
exec gunicorn --bind "0.0.0.0:${PORT:-8000}" --workers 1 --threads 4 --timeout 180 "app:create_app()"
