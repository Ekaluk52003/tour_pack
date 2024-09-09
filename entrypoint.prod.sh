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

   # Start Gunicorn
   echo "Starting Gunicorn..."
   exec gunicorn tour.wsgi:application --bind 0.0.0.0:8000