# DumbBureau

Multi-User-Web-App zur Verwaltung von Ausbildungstätigkeiten (Berichtsheft) mit
automatischer PDF-Generierung. Sicherer Login per **WebAuthn/Passkey** (Resident Keys),
Datenverschlüsselung per **AES-128-GCM** und ein Admin-Panel mit Audit-Log und
Recovery-Funktionen.

## Features

- **WebAuthn-Login** (Passkey / YubiKey) — kein Passwort
- **Aufgaben (Tasks)** mit Monatsübersicht, Quick-Add, „Letzte Woche kopieren“
- **Custom Kategorien** (FiSi-Bereiche) mit Farben
- **User-definierte HTML-Templates** (Jinja2) für die PDF-Erzeugung
- **PDF-Export** nach IHK-Vorgaben (WeasyPrint)
- **Admin-Panel**: Benutzer, Audit-Log, Task-Viewing, Einladungen, Archivierung
- **i18n** Deutsch / Englisch, Dark Theme, Mobile-First
- **Verschlüsselung** (AES-128-GCM) für Task-Beschreibungen und Audit-Details
- **Max ~5 User** (SQLite als Datenbank)

## Stack

- **Backend**: FastAPI, SQLAlchemy 2, webauthn (v3), PyJWT, cryptography, argon2-cffi, Jinja2, WeasyPrint, bleach
- **Frontend**: Vanilla JS (kein Build), Hash-Router-SPA, nginx
- **Deployment**: Docker Compose

## Struktur

```
backend/
  app/            # FastAPI application
    routes/       # auth, tasks, categories, templates, pdf, admin
    crypto.py     # AES-128-GCM + Argon2id
    rate_limit.py # Sliding-Window-Rate-Limiter + Client-IP-Auflösung
    pdf_generator.py
    maintenance.py
  docker-entrypoint.sh  # chown + Drop-Privileges (unprivilegierter User)
  tests/          # Integrationstests (python tests/run_all.py)
frontend/
  index.html      # App-Shell
  pages/login.html
  js/             # api, auth, views, i18n, ...
  css/
docker-compose.yml
```

## Deployment (Docker Compose)

```bash
# 1. Konfiguration vorbereiten
cp .env.example .env
# SECRET_KEY, ADMIN_RECOVERY_SECRET, WEBAUTHN_RP_ID/ORIGIN setzen (siehe unten)

# 2. Bauen und starten
docker compose up -d --build
```

Die App **benötigt einen Reverse Proxy mit HTTPS** (WebAuthn/Passkeys verlangen
einen sicheren Kontext). Dafür wird dein eigener Reverse Proxy (nginx, Nginx
Proxy Manager, Traefik …) verwendet – die App bringt **keinen** eigenen
TLS-Terminator mit.

- **Frontend** wird auf Host-Port `8360` publiziert (`FRONTEND_PORT`).
- **Backend** optional auf `8361` (`BACKEND_PORT`), nur für Debug/API-Zugriff.
- Dein Reverse Proxy terminiert TLS und zeigt seinen Upstream auf
  `http://<docker-host>:8360`.

Daten liegen unter `APPDATA_DIR` (Standard `/appdata/dumbbureau/`):

- `db.sqlite` — Datenbank
- `templates/` — User-Templates
- `exports/` — PDF-Exports
- `logs/` — Logs

## Umgebungsvariablen (`.env`)

| Variable | Beschreibung |
|---|---|
| `FRONTEND_PORT` | Host-Port der Web-App (Standard `8360`), Ziel deines Reverse Proxys |
| `BACKEND_PORT` | Host-Port der API (Standard `8361`), nur für Debug |
| `SECRET_KEY` | JWT-Signatur (mind. 32 Zeichen, `openssl rand -hex 32`) |
| `ENCRYPTION_KEY` | Optional, Schlüssel für AES-128-GCM (Fallback: `SECRET_KEY`) |
| `ADMIN_RECOVERY_SECRET` | Secret für den allerersten (Admin-)User |
| `WEBAUTHN_RP_ID` | Registrierbare Domain (deine Subdomain, kein Schema/Port) |
| `WEBAUTHN_RP_NAME` | Anzeigename der Relying Party |
| `WEBAUTHN_ORIGIN` | Origin (Schema+Host, z. B. `https://dumbbureau.example.com`) |
| `DATABASE_URL` | SQLite-Pfad (Container-intern) |
| `APPDATA_DIR` | Host-Verzeichnis für DB/Templates/Exports/Logs |
| `TRUSTED_PROXY_IPS` | Feste IP deines Reverse Proxys + Docker-Bridge-Bereich `172.16.0.0/12` |
| `CORS_ORIGINS` | Erlaubte Frontend-Origins (kommagetrennt) |
| `RATE_LIMIT_ENABLED` | Rate Limiting an/aus (Standard `true`) |
| `RATE_LIMIT_MAX_REQUESTS` | Max. Requests je Client & Fenster (Standard `30`) |
| `RATE_LIMIT_WINDOW_SECONDS` | Fenstergröße in Sekunden (Standard `60`) |
| `CHALLENGE_TTL_SECONDS` | Gültigkeit der WebAuthn-Challenge (Standard `300`) |
| `ACCESS_TOKEN_TTL_MINUTES` | JWT-Session-Gültigkeit (Standard `60`) |
| `INVITE_TOKEN_TTL_DAYS` | Gültigkeit der Einladungen (Standard `7`) |
| `RECOVERY_TOKEN_TTL_MINUTES` | Gültigkeit der Recovery-Tokens (Standard `30`) |
| `LOG_LEVEL` | Log-Level (Standard `INFO`) |

**Lokal testen:** Die Defaults (`RP_ID=localhost`, Origin `http://localhost:8360`)
passen für `http://localhost:8360` (localhost gilt als sicherer Kontext).

## Erst-Einrichtung

1. Beim ersten Start existiert noch kein User. Auf der Login-Seite wird die
   **Admin-Setup**-Ansicht angezeigt.
2. Benutzername + E-Mail eingeben, `ADMIN_RECOVERY_SECRET` eintragen und den
   Passkey (YubiKey) registrieren → erster User wird **Admin**.
3. Weitere User: Als Admin im Admin-Panel unter **Einladungen** einen Code
   erzeugen und teilen. Der neue User registriert sich damit (wird Nicht-Admin).

## WebAuthn-Hinweise

- WebAuthn erfordert einen **sicheren Kontext** (HTTPS) oder `localhost`.
- `WEBAUTHN_RP_ID` muss exakt der Domain entsprechen, unter der die App
  erreichbar ist (kein Schema/Port); `WEBAUTHN_ORIGIN` ist Schema+Host(+Port).
- Bei Subpath-Deployment (`PUBLIC_URL=/dumbbureau`) den Reverse-Proxy so
  konfigurieren, dass `/dumbbureau/...` auf den Frontend-Container und
  `/dumbbureau/api/...` auf den Backend-Container zeigt.

## Reverse Proxy / HTTPS (Passkeys)

Dein Reverse Proxy terminiert TLS und leitet intern (HTTP) an den
Docker-Host auf `FRONTEND_PORT` (8360) weiter. Damit WebAuthn sauber läuft:

```bash
# .env (Subdomain-Beispiel — deine echte Domain in deiner lokalen .env)
WEBAUTHN_RP_ID=dumbbureau.example.com
WEBAUTHN_ORIGIN=https://dumbbureau.example.com
CORS_ORIGINS=https://dumbbureau.example.com

# Feste IP deines Reverse Proxys (damit die Client-IP korrekt erkannt wird)
TRUSTED_PROXY_IPS=192.168.1.2, 172.16.0.0/12

docker compose up -d --build
```

Dein Reverse Proxy muss `X-Real-IP` (bzw. `X-Forwarded-For`) mit der echten
Client-IP setzen und an den Frontend-Container weitergeben. Das Frontend leitet
beide Header an das Backend weiter, damit das Rate-Limiting pro Client (statt
pro Proxy) greift.

## Logs & Rotation

Die Container-Logs werden über den Docker-JSON-Driver rotiert
(`max-size=10m`, `max-file=3`, in `docker-compose.yml` zentral definiert).
Anzeigen mit `docker compose logs -f backend` bzw. `docker compose logs -f frontend`.

## Backup (extern)

Backups laufen bewusst **außerhalb** der App (z. B. via Unraid). Der
`APPDATA_DIR` liegt im WAL-Modus vor; für ein konsistentes Backup bitte
`db.sqlite` **inklusive** `db.sqlite-wal` und `db.sqlite-shm` sichern (oder die
Container kurz stoppen). Die Daten sind verschlüsselt – zur Wiederherstellung
wird derselbe `ENCRYPTION_KEY`/`SECRET_KEY` benötigt.

## Tests

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python tests/run_all.py
```

Die Tests decken Auth (WebAuthn-Registrierung/Login/Recovery), Task-CRUD,
Kategorien/Templates, PDF-Export (WeasyPrint wird gemockt, da Pango nötig ist),
Admin sowie Security (Rate Limiting, User-Enumeration, Proxy-Konfiguration) ab.
Ein virtueller WebAuthn-Authenticator simuliert einen echten Security-Key.

## Sicherheit

- **WebAuthn**: 2-Schritt-Flow mit Server-Challenge (Replay-sicher)
- **JWT**: 60-min-TTL, `HS256`
- **Rate Limiting**: Sliding-Window-Limiter für Auth-Endpoints, keyed per
  Client-IP (über `TRUSTED_PROXY_IPS` korrekt aufgelöst)
- **Kein User-Enumeration**: `login/options` liefert bei unbekanntem Usernamen
  keine Fehlermeldung, sondern eine usernameless Challenge
- **AES-128-GCM**: Task-Beschreibungen + Audit-Details verschlüsselt at rest,
  Key-Ableitung per Argon2id aus `ENCRYPTION_KEY`/`SECRET_KEY`
- **Template-Sandbox**: Jinja2 `SandboxedEnvironment` (SSTI-Schutz) + HTML-
  Sanitizing (bleach)
- **SSRF-Schutz**: WeasyPrint lädt nur `data:`-URIs (keine externen/file-URLs)
- **Recovery/Invites**: Einmal-Tokens (gehasht gespeichert, kurze TTL)
- **Container-Hardening**: Backend läuft als unprivilegierter User (UID 10001),
  Volume-Ownership wird beim Start korrigiert
