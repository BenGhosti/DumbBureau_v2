FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System dependencies for weasyprint (Pango/Cairo/GdkPixbuf) + curl for
# healthcheck + gosu to drop privileges after fixing volume ownership.
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

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Dedicated non-root user the app actually runs as. The container still
# *starts* as root (see entrypoint) purely to chown the bind-mounted
# APPDATA_DIR volume, whose ownership on the host is unknown at build time -
# then it drops to this user before executing uvicorn. Without that step,
# a bind mount created by `docker compose up` typically ends up root:root
# on the host, and the app user could never write its own database.
RUN groupadd -r dumbbureau && useradd -r -g dumbbureau -d /app dumbbureau

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
