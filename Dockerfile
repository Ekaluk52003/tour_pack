# Dockerfile.prod
FROM python:3.12.2-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND noninteractive

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-thai-tlwg \
    build-essential \
    python3-dev \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    netcat-traditional \
    libpq-dev \
    nodejs \
    npm \
    cron \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt .

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

COPY ./package.json ./package-lock.json ./
RUN npm install

COPY webpack.config.js ./
COPY tailwind.config.js ./
COPY postcss.config.js ./

# Copy the static assets explicitly
COPY ./static ./static

RUN npm run build

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
