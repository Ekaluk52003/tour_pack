# Backup Management Guide

This guide outlines the process for setting up and managing database backups for Django projects, covering both system cron and Django-crontab methods.

## 1. Database Backup Setup

### 1.1 Install Required Packages

`pip install django-dbbackup django-crontab`

### 1.2 Configure Django Settings

Add the following to your Django settings:

```python
INSTALLED_APPS = [
# ...
'dbbackup',
'django_crontab',
]
DBBACKUP_STORAGE = 'django.core.files.storage.FileSystemStorage'
DBBACKUP_STORAGE_OPTIONS = {'location': '/path/to/your/backups/'}
```

### 1.3 Create Backup Directory

Ensure the backup directory exists and has appropriate permissions:
Or just create the directory in the project folder /backups

```bash
mkdir -p /path/to/your/backups/
chmod 755 /path/to/your/backups/
```

## 2. Manual Backup and Restore

### 2.1 Create a Backup

To create a manual backup, run:

```bash
docker-compose run --rm web python manage.py dbbackup
```
You might need to install postgres client on your system to make backup command work

### 2.2 Restore from Backup

To restore from the latest backup:

```bash
docker-compose run --rm web python manage.py dbrestore
```

## 3. Automated Backups with Django-crontab

### Configure Cron Jobs

In your Django settings, add the cron job:
This schedules a backup at every hour. This basically run Django management command dbbackup. You can create your own management command to backup your database. dbbackup --clean is default command from Django-dbbackup.

```python


CRONJOBS = [

     ('0 * * * *', 'django.core.management.call_command', ['dbbackup', '--clean'])

    # ('*/2 * * * *', 'django.core.management.call_command', ['cleanup_backups']),
]
```


### Add Cron Jobs to System

Run the following command to add the cron jobs to your system:

```bash
docker-compose run --rm web python manage.py crontab add
```


### Manage Cron Jobs

- To show current cron jobs:
  ```bash
  docker-compose run --rm web python manage.py crontab show
  ```

- To remove all cron jobs:
  ```bash
  docker-compose run --rm web python manage.py crontab remove
  ```

### Start Cron Service with Docker Compose

To ensure that your cron jobs run in the Docker environment, you need to start the cron service in your Docker container. Add the following to your `docker-compose.yml` file:

```yaml
services:
  web:
    // ... existing web service configuration ...
    command: sh -c "python manage.py crontab add && service cron start"
```
you can add above command to entrypoint.sh so that you don't need to run it manually inside the container using bash.

This command does the following:
1. Adds the cron jobs to the system
2. Starts the cron service

Make sure your Dockerfile installs the cron package and PostgreSQL client:

```dockerfile
RUN apt-get update && apt-get install -y cron postgresql-client
```

The PostgreSQL client is necessary for the database backup process to work correctly.

Now, when you start your Docker containers with `docker-compose up`, the cron service will be running and your scheduled backups will occur as configured.

## 4. Backup Retention and Maintenance

### 4.1 Configure Backup Retention

To keep only a certain number of backups, add this to your settings:

```python
DBBACKUP_CLEANUP_KEEP = 10  # Keep last 10 backups
```

### Backup and clean old backups. This will create a new backup and delete the oldest backup if the number of backups exceeds the specified limit.

```bash
docker-compose exec web python manage.py dbbackup --clean
```

## Remark

When run already start docker service with cmd : service cron start and docker-compose exec web python manage.py crontab add
Django will pick up the cron job and run it. You don't need to start the cron service again.

# Library

- django-dbbackup
https://django-dbbackup.readthedocs.io/en/stable/index.html
- django-crontab
https://pypi.org/project/django-crontab/


