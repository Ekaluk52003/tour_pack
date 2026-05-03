# Docker Setup Guide

## Overview

This project uses Docker Compose with two environments:
- **Development**: Hot-reload for both Django and Webpack
- **Production**: Static build, served via Caddy

---

## Development

### 1. Start all services

```bash
docker compose up
```

This starts:
- `web` - Django development server
- `webpack` - Webpack watch mode (auto-rebuilds CSS/JS)
- `db` - PostgreSQL

### 2. Access the application

- Django: http://localhost:8000 (or your `DJANGO_PORT`)
- Webpack dev server: http://localhost:8080

### 3. Common commands

```bash
# Run in background
docker compose up -d

# View logs
docker compose logs -f

# View specific service logs
docker compose logs webpack -f
docker compose logs web -f

# Stop all services
docker compose down

# Stop and remove volumes
docker compose down -v
```

### 4. Running Django management commands

```bash
# Create migrations
docker compose exec web python manage.py makemigrations

# Apply migrations
docker compose exec web python manage.py migrate

# Create superuser
docker compose exec web python manage.py createsuperuser

# Shell
docker compose exec web python manage.py shell
```

### 5. Building CSS (one-time)

If you need to build CSS without running watch mode:

```bash
docker compose run --rm webpack npm run build
```

This updates `static/dist/styles.css` locally.

---

## Production Deployment

### Workflow

1. **Local**: Build CSS and commit
   ```bash
   npm run build
   git add static/dist/
   git commit -m "Update CSS"
   git push
   ```

2. **VPS**: Pull and deploy
   ```bash
   git pull
   docker compose -f docker-compose.prod.yml up -d
   ```

### Production commands

```bash
# Build and start
docker compose -f docker-compose.prod.yml up -d

# View logs
docker compose -f docker-compose.prod.yml logs -f

# Stop
docker compose -f docker-compose.prod.yml down

# Rebuild after code changes
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Services Explained

| Service | Development | Production | Purpose |
|---------|-------------|------------|---------|
| `web` | ✓ | ✓ | Django application |
| `webpack` | ✓ | ✗ | Builds CSS/JS (watch mode) |
| `db` | ✓ | ✓ | PostgreSQL database |
| `caddy` | ✗ | ✓ | Web server & reverse proxy |

---

## Tailwind CSS & Webpack

### How it works

1. Edit templates with Tailwind classes (e.g., `bg-amber-50`, `text-cyan-600`)
2. Webpack watch detects changes via `tailwind.config.js` `content` paths
3. PostCSS processes Tailwind and outputs to `static/dist/styles.css`
4. Django serves the file from `static/dist/`

### Important: Before committing

Always run this before `git commit` to update `static/dist/`:

```bash
docker compose run --rm webpack npm run build
```

Or if you have Node.js locally:

```bash
npm run build
```

Then commit:
```bash
git add static/dist/
git commit -m "..."
```

---

## Troubleshooting

### CSS not updating

1. Check webpack is running:
   ```bash
   docker compose ps
   ```

2. Check webpack logs:
   ```bash
   docker compose logs webpack -f
   ```

3. Hard refresh browser (Ctrl+Shift+R or Cmd+Shift+R)

4. Rebuild manually:
   ```bash
   docker compose run --rm webpack npm run build
   ```

### Port already in use

```bash
# Find what's using port 8000
lsof -i :8000

# Or change DJANGO_PORT in .env
```

### Database connection issues

```bash
# Reset database
docker compose down -v
docker compose up -d db
docker compose exec web python manage.py migrate
```

### Static files not found in production

Ensure `static/dist/` is committed to git:
```bash
git ls-files static/dist/
```

If empty, build and commit:
```bash
npm run build
git add static/dist/
git commit -m "Add built static files"
```

---

## Environment Variables

Create `.env` file:

```env
# Django
DJANGO_PORT=8000
DATABASE_URL=postgres://user:pass@db:5432/dbname

# Database (for db service)
POSTGRES_DB=dbname
POSTGRES_USER=user
POSTGRES_PASSWORD=pass

# Production
DOMAIN=yourdomain.com
```

---

## File Structure

```
.
├── docker-compose.yml          # Development
├── docker-compose.prod.yml     # Production
├── Dockerfile                  # Development web
├── Dockerfile.prod             # Production web
├── Dockerfile.webpack          # Webpack builder
├── tailwind.config.js          # Tailwind config (content paths)
├── webpack.config.js           # Webpack config
├── postcss.config.js           # PostCSS config
├── static/
│   ├── css/styles.css          # Tailwind input
│   └── dist/                   # Built output (committed)
│       ├── styles.css
│       └── bundle.js
└── templates/                    # HTML templates
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Start dev | `docker compose up` |
| Start background | `docker compose up -d` |
| Stop dev | `docker compose down` |
| Build CSS | `docker compose run --rm webpack npm run build` |
| View logs | `docker compose logs -f` |
| Deploy prod | `docker compose -f docker-compose.prod.yml up -d` |
| Rebuild prod | `docker compose -f docker-compose.prod.yml up -d --build` |
