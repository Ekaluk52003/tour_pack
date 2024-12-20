#!/bin/sh

if [ "$DATABASE" = "postgres" ]
then
    echo "Waiting for postgres..."

    while ! nc -z $SQL_HOST $SQL_PORT; do
      sleep 1
    done

    echo "PostgreSQL started"
fi

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate

# Start cron service
echo "Starting cron service..."
service cron start

# Add crontab jobs
echo "Adding crontab jobs..."
python manage.py crontab add

# Start Gunicorn
echo "Starting Gunicorn..."
exec gunicorn ${DJANGO_PROJECT_NAME}.wsgi:application --bind 0.0.0.0:8000