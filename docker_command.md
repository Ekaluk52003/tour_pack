# Docker Commands for Django Project

## Basic Docker Compose Commands

### Start the services
```bash
docker-compose up -d
```

### Bash into the web container to see the file system
```bash
docker-compose exec web bash
```

### Stop the services
```bash
docker-compose stop
```

### Stop and remove containers, networks
```bash
docker-compose down
```

### Rebuild the images
```bash
docker-compose build
```

### View running containers
```bash
docker-compose ps
```

### View logs
```bash
docker-compose logs
```

### View logs for a specific service
```bash
docker-compose logs web
```

## Django Management Commands

### Run migrations
```bash
docker-compose exec web python manage.py migrate
```

### Make migrations
```bash
docker-compose exec web python manage.py makemigrations
```

### Create a superuser
```bash
docker-compose exec web python manage.py createsuperuser
```

### Collect static files
```bash
docker-compose exec web python manage.py collectstatic
```

### Run Django shell
```bash
docker-compose exec web python manage.py shell
```

## Database Commands

### Access PostgreSQL shell
```bash
docker-compose exec db psql -U ${POSTGRES_USER} -d ${POSTGRES_DB}
```

## Utility Commands

### Remove all stopped containers
```bash
docker container prune
```

### Remove unused images
```bash
docker image prune
```

### View Docker disk usage
```bash
docker system df
```

## Troubleshooting Commands

### Rebuild and force recreate containers
```bash
docker-compose up -d --build --force-recreate
```

### View container logs in real-time
```bash
docker-compose logs -f
```

### Inspect a container
```bash
docker inspect <container_name_or_id>
```

### Execute a command in a running container
```bash
docker-compose exec <service_name> <command>
```

Example:
```bash
docker-compose exec web ls -l
```

### Run a one-off command in a new container
```bash
docker-compose run --rm <service_name> <command>
```

Example:
```bash
docker-compose run --rm web python manage.py check
```

sudo docker-compose -f docker-compose.prod.yml up -d --build web