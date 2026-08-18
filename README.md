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
Caddyfile         # Reverse-Proxy / TLS (Profil `caddy`)
docker-compose.yml
```

## Deployment (Docker Compose)

```bash
# 1. Konfiguration vorbereiten
cp .env.example .env
# SECRET_KEY, ADMIN_RECOVERY_SECRET, DUMBBUREAU_HOSTNAME,
# WEBAUTHN_RP_ID/ORIGIN setzen (siehe unten)

# 2. Bauen und starten (mit HTTPS-Reverse-Proxy via Caddy)
docker compose --profile caddy up -d --build
```

WebAuthn/Passkeys benötigen einen **sicheren Kontext** (HTTPS). Deshalb gibt es ein
optionales Caddy-Profil, das TLS übernimmt und die App unter **Port 8360 (HTTPS)**
bereitstellt; Port **8361** leitet auf HTTPS um. Ohne das Profil (`docker compose up -d`)
laufen nur Backend/Frontend **intern** (nicht vom Host erreichbar) – das ist nur für
lokale Tests gedacht, wo `http://localhost` als sicherer Kontext gilt.

Caddy nutzt `tls internal` (selbstsigniertes Zertifikat über eine lokale CA). Damit
Passkeys im LAN ohne Browser-Warnung funktionieren, die Caddy-CA einmalig auf den
Clients installieren (siehe „HTTPS / Caddy (Passkeys)“).

Daten liegen unter `APPDATA_DIR` (Standard `/appdata/dumbbureau/`):

- `db.sqlite` — Datenbank
- `templates/` — User-Templates
- `exports/` — PDF-Exports
- `logs/` — Logs

Die App ist unter `https://<DUMBBUREAU_HOSTNAME>:8360` erreichbar. Backend und
Frontend werden **nicht** direkt auf den Host publiziert – der gesamte externe
Zugriff läuft über Caddy.

## Umgebungsvariablen (`.env`)

| Variable | Beschreibung |
|---|---|
| `DUMBBUREAU_HOSTNAME` | DNS-Name oder LAN-IP der App (kein Schema/Port); muss `WEBAUTHN_RP_ID` entsprechen |
| `SECRET_KEY` | JWT-Signatur (mind. 32 Zeichen, `openssl rand -hex 32`) |
| `ENCRYPTION_KEY` | Optional, Schlüssel für AES-128-GCM (Fallback: `SECRET_KEY`) |
| `ADMIN_RECOVERY_SECRET` | Secret für den allerersten (Admin-)User |
| `WEBAUTHN_RP_ID` | Registrierbare Domain (mit Caddy: `DUMBBUREAU_HOSTNAME`) |
| `WEBAUTHN_RP_NAME` | Anzeigename der Relying Party |
| `WEBAUTHN_ORIGIN` | Origin (mit Caddy: `https://<host>:8360`) |
| `DATABASE_URL` | SQLite-Pfad (Container-intern) |
| `APPDATA_DIR` | Host-Verzeichnis für DB/Templates/Exports/Logs |
| `TRUSTED_PROXY_IPS` | CIDR des Reverse-Proxy (internes Docker-Netz, Standard `172.28.1.0/24`) |
| `CORS_ORIGINS` | Erlaubte Frontend-Origins (kommagetrennt) |
| `RATE_LIMIT_ENABLED` | Rate Limiting an/aus (Standard `true`) |
| `RATE_LIMIT_MAX_REQUESTS` | Max. Requests je Client & Fenster (Standard `30`) |
| `RATE_LIMIT_WINDOW_SECONDS` | Fenstergröße in Sekunden (Standard `60`) |
| `CHALLENGE_TTL_SECONDS` | Gültigkeit der WebAuthn-Challenge (Standard `300`) |
| `ACCESS_TOKEN_TTL_MINUTES` | JWT-Session-Gültigkeit (Standard `60`) |
| `INVITE_TOKEN_TTL_DAYS` | Gültigkeit der Einladungen (Standard `7`) |
| `RECOVERY_TOKEN_TTL_MINUTES` | Gültigkeit der Recovery-Tokens (Standard `30`) |
| `LOG_LEVEL` | Log-Level (Standard `INFO`) |

**Lokal testen (ohne Caddy):** Die Defaults (`RP_ID=localhost`, Origin
`http://localhost:8360`) passen für `http://localhost:8360`. Dafür Frontend/Backend
kurzzeitig auf den Host publizieren oder den Caddy-Stack mit `localhost`-Hostname nutzen.

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
  erreichbar ist (kein Schema/Port); `WEBAUTHN_ORIGIN` ist Schema+Host+Port.
- Bei Subpath-Deployment (`PUBLIC_URL=/dumbbureau`) den Reverse-Proxy so
  konfigurieren, dass `/dumbbureau/...` auf den Frontend-Container und
  `/dumbbureau/api/...` auf den Backend-Container zeigt.

## HTTPS / Caddy (Passkeys im LAN)

WebAuthn funktioniert über eine LAN-IP ohne HTTPS nicht. Das Caddy-Profil löst
das mit `tls internal` (lokale CA, selbstsigniertes Zertifikat):

```bash
# .env
DUMBBUREAU_HOSTNAME=dumbbureau.local   # oder die LAN-IP, z.B. 192.168.188.50
WEBAUTHN_RP_ID=dumbbureau.local        # identisch zu DUMBBUREAU_HOSTNAME
WEBAUTHN_ORIGIN=https://dumbbureau.local:8360
CORS_ORIGINS=https://dumbbureau.local:8360

docker compose --profile caddy up -d --build
```

Caddy-CA einmalig auf den Clients installieren, damit das Zertifikat als
vertrauenswürdig gilt (sonst zeigt der Browser eine Warnung, die man einmalig
bestätigen muss):

```bash
# CA aus dem caddy_data-Volume exportieren:
docker cp dumbbureau_caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
# Auf Windows (Admin):   certutil -addstore -f "Root" caddy-root.crt
# Auf macOS:             sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain caddy-root.crt
# Auf Linux:             sudo cp caddy-root.crt /usr/local/share/ca-certificates/caddy-root.crt && sudo update-ca-certificates
```

Danach ist die App unter `https://<DUMBBUREAU_HOSTNAME>:8360` erreichbar;
`http://<DUMBBUREAU_HOSTNAME>:8361` leitet auf HTTPS um. Backend und Frontend
laufen nur intern (nicht auf den Host gepubliziert).

## Logs & Rotation

Die Container-Logs werden über den Docker-JSON-Driver rotiert
(`max-size=10m`, `max-file=3`, in `docker-compose.yml` zentral definiert).
Anzeigen mit `docker compose logs -f backend` bzw. `docker compose --profile caddy logs -f caddy`.

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
