FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_UID=10001 \
    APP_GID=10001

# System dependencies for weasyprint (Pango/Cairo/GdkPixbuf) + curl for the
# healthcheck + gosu to drop privileges in the entrypoint.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-dejavu-core \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged user that runs the app. The entrypoint chowns the mounted
# appdata volume to this UID/GID, then drops root via gosu.
RUN groupadd --system --gid "$APP_GID" app \
    && useradd --system --uid "$APP_UID" --gid "$APP_GID" \
        --home /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
