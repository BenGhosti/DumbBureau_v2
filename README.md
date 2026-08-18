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
    pdf_generator.py
    maintenance.py
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
# SECRET_KEY, ADMIN_RECOVERY_SECRET, WEBAUTHN_RP_ID/ORIGIN, TRUSTED_PROXY_IPS
# setzen (siehe unten) - .env bleibt lokal, wird nicht committet.

# 2. Bauen und starten
docker compose up -d --build
```

Daten liegen unter `APPDATA_DIR` (Standard `/appdata/dumbbureau/`):

- `db.sqlite` (+ `db.sqlite-wal`, `db.sqlite-shm` im laufenden Betrieb) — Datenbank
- `templates/` — User-Templates
- `exports/` — PDF-Exports
- `logs/` — Logs

Frontend (Web-App): Port `8360`, Backend (API): Port `8361`.
Beide Ports sind über `FRONTEND_PORT` / `BACKEND_PORT` in der `.env` änderbar.

### Netzwerk-Architektur

Dieses Repo enthält bewusst **keinen** eigenen Reverse-Proxy/TLS-Container.
Für den produktiven Betrieb läuft davor ein separater, extern verwalteter
nginx-Reverse-Proxy (eigene IP, z. B. via macvlan) auf demselben Host, der
TLS terminiert und via Cloudflare o. Ä. angebunden sein kann:

```
Internet -> Cloudflare -> dein nginx (TLS, eigene IP) -> :8360 (frontend) -> :8361 (backend, intern)
```

`frontend` und `backend` sprechen intern nur reines HTTP — das ist normal
und erwartet, TLS endet bei deinem externen Proxy. `BACKEND_PORT` (8361)
ist auf dem Host gemappt, damit du/dein Proxy im Bedarfsfall direkt
draufkommen, ist aber nirgends im Stack selbst beworben oder verlinkt —
normaler Traffic läuft immer über `frontend`.

## Umgebungsvariablen (`.env`)

| Variable | Beschreibung |
|---|---|
| `FRONTEND_PORT` | Host-Port der Web-App (Standard `8360`) |
| `BACKEND_PORT` | Host-Port der API, nur für direkten/Debug-Zugriff (Standard `8361`) |
| `SECRET_KEY` | JWT-Signatur (mind. 32 Zeichen, `openssl rand -hex 32`) |
| `ENCRYPTION_KEY` | Optional, Schlüssel für AES-128-GCM (Fallback: `SECRET_KEY`) |
| `ADMIN_RECOVERY_SECRET` | Secret für den allerersten (Admin-)User |
| `WEBAUTHN_RP_ID` | Registrierbare Domain — bei Subdomain-Deployment deine echte Subdomain, z. B. `dumbbureau.example.com` |
| `WEBAUTHN_RP_NAME` | Anzeigename der Relying Party |
| `WEBAUTHN_ORIGIN` | Origin — bei Subdomain-Deployment `https://dumbbureau.example.com` |
| `DATABASE_URL` | SQLite-Pfad (Container-intern) |
| `APPDATA_DIR` | Host-Verzeichnis für DB/Templates/Exports/Logs |
| `TRUSTED_PROXY_IPS` | Feste IP deines externen nginx-Reverse-Proxys (kein Default — leer = es wird niemandem vertraut) |
| `CORS_ORIGINS` | Erlaubte Frontend-Origins (kommagetrennt, deine echte Domain) |
| `CHALLENGE_TTL_SECONDS` | Gültigkeit der WebAuthn-Challenge (Standard `300`) |
| `ACCESS_TOKEN_TTL_MINUTES` | JWT-Session-Gültigkeit (Standard `60`) |
| `INVITE_TOKEN_TTL_DAYS` | Gültigkeit der Einladungen (Standard `7`) |
| `RECOVERY_TOKEN_TTL_MINUTES` | Gültigkeit der Recovery-Tokens (Standard `30`) |
| `LOG_LEVEL` | Log-Level (Standard `INFO`) |

**Lokal testen:** Die Defaults (Port `8360`, `RP_ID=localhost`, Origin
`http://localhost:8360`) passen direkt für `http://localhost:8360`.

**Produktiv unter eigener Subdomain:** `WEBAUTHN_RP_ID`/`WEBAUTHN_ORIGIN`/
`CORS_ORIGINS` auf die echte `https://`-Subdomain setzen, `TRUSTED_PROXY_IPS`
auf die feste IP deines externen nginx. Diese Werte gehören **nur** in deine
lokale `.env`, niemals in `.env.example` oder ins Repo.

## Backup

SQLite läuft im **WAL-Modus** (siehe `database.py`). Für ein konsistentes
Backup reichen nicht `db.sqlite` allein — solange die App läuft, können
committete Änderungen noch in `db.sqlite-wal` stehen. Entweder:

- Backend kurz stoppen und `db.sqlite`, `db.sqlite-wal`, `db.sqlite-shm`
  zusammen kopieren, oder
- ein Filesystem-/Volume-Snapshot des `APPDATA_DIR` (z. B. über Unraid),
  der alle drei Dateien atomar mit erfasst.

Ein reines `cp` bei laufendem Betrieb kann einen inkonsistenten Zwischenstand
erwischen.

## Erst-Einrichtung

1. Beim ersten Start existiert noch kein User. Auf der Login-Seite wird die
   **Admin-Setup**-Ansicht angezeigt.
2. Benutzername + E-Mail eingeben, `ADMIN_RECOVERY_SECRET` eintragen und den
   Passkey (YubiKey) registrieren → erster User wird **Admin**.
3. Weitere User: Als Admin im Admin-Panel unter **Einladungen** einen Code
   erzeugen und teilen. Der neue User registriert sich damit (wird Nicht-Admin).

## WebAuthn-Hinweise

- WebAuthn erfordert einen **sicheren Kontext** (HTTPS) oder `localhost`.
  Eine reine LAN-IP über HTTP (`http://192.168.x.x:8360`) wird von allen
  gängigen Browsern **nicht** als sicherer Kontext akzeptiert — Passkeys
  funktionieren dann nicht. Deshalb terminiert TLS extern an deinem eigenen
  nginx unter einer echten Subdomain.
- `WEBAUTHN_RP_ID` muss exakt der Domain entsprechen, unter der die App
  erreichbar ist (kein Schema/Port).
- Bei Subpath-Deployment (`PUBLIC_URL=/dumbbureau`) den Reverse-Proxy so
  konfigurieren, dass `/dumbbureau/...` auf den Frontend-Container und
  `/dumbbureau/api/...` auf den Backend-Container zeigt.

## Tests

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tests/run_all.py
```

Die Tests decken Auth (WebAuthn-Registrierung/Login/Recovery), Task-CRUD,
Kategorien/Templates, PDF-Export (WeasyPrint wird gemockt, da Pango nötig ist)
und Admin ab. Ein virtueller WebAuthn-Authenticator simuliert einen echten
Security-Key.

## Sicherheit

- **WebAuthn**: 2-Schritt-Flow mit Server-Challenge (Replay-sicher)
- **JWT**: 60-min-TTL, `HS256`
- **AES-128-GCM**: Task-Beschreibungen + Audit-Details verschlüsselt at rest,
  Key-Ableitung per Argon2id aus `ENCRYPTION_KEY`/`SECRET_KEY`
- **Template-Sandbox**: Jinja2 `SandboxedEnvironment` (SSTI-Schutz) + HTML-
  Sanitizing (bleach)
- **SSRF-Schutz**: WeasyPrint lädt nur `data:`-URIs (keine externen/file-URLs)
- **Recovery/Invites**: Einmal-Tokens (gehasht gespeichert, kurze TTL)
- **Rate-Limiting**: Alle Auth-Endpunkte (Register/Login/Recovery) sind pro
  Client-IP gedrosselt (30 Versuche / 5 Minuten) — schützt primär vor
  Ressourcen-Erschöpfung, nicht vor Credential-Guessing (WebAuthn hat kein
  erratbares Geheimnis)
- **Keine User-Enumeration**: Login mit unbekanntem Benutzernamen liefert
  dieselbe generische Antwort wie ein bekannter — kein Rückschluss auf
  existierende Accounts möglich
- **Non-root Container**: Der Backend-Prozess läuft als dedizierter
  unprivilegierter User, nicht als root
