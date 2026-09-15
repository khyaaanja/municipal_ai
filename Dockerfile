FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=municipal_ai.settings

WORKDIR /app

# System dependencies for mysqlclient and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    default-libmysqlclient-dev \
    build-essential \
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p logs staticfiles media

# Collect static files — needs SECRET_KEY set; use a dummy one only at build time
RUN SECRET_KEY="build-only-not-used-in-runtime" python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "municipal_ai.wsgi:application", "--config", "gunicorn.conf.py"]
