# DumbBureau – Feature-Liste & Umsetzungsdetails

Stand: Phase 1–12 + AES-Encryption + Review abgeschlossen.
Backend: FastAPI + SQLAlchemy 2 + SQLite · Frontend: Vanilla JS SPA (nginx) · Deployment: Docker Compose

---

## 1. Authentifizierung (WebAuthn / Passkeys)

| Feature | Umsetzung |
|---|---|
| Passwortloses Login | WebAuthn mit **Resident Keys** (Discoverable Credentials), `AuthenticatorSelectionCriteria(resident_key=REQUIRED, authenticator_attachment=CROSS_PLATFORM, user_verification=REQUIRED)` |
| Sicherer 2-Schritt-Flow | Server generiert Challenge (`secrets.token_bytes(32)`), speichert sie in Tabelle `auth_challenges` (TTL 300 s, Einmal-Verwendung) → Client signiert → Server verifiziert. Kein One-Shot-Flow |
| Registrierung | `POST /api/auth/register/options` + `POST /api/auth/register/verify`; Attestation „none“ (Self-Attestation) |
| Login | `POST /api/auth/login/options` + `POST /api/auth/login/verify`; `allow_credentials` je Username (resident keys erlauben zusätzlich usernameless) |
| Replay-Schutz | Challenge nur einmal verwendbar (`used_at`), Sign-Counter-Check (`new_sign_count > stored`) |
| UV-Erzwingung | `require_user_verification=True` bei Register & Login (PIN/Biometrie am Key) |
| Erster User = Admin | Wenn keine aktiven User existieren: Registrierung nur mit `ADMIN_RECOVERY_SECRET` (constant-time compare) → `is_admin=True` |
| User 2+ via Einladung | Admin erzeugt Einmal-Invite-Token (Tabellen `invite_tokens`, nur SHA-256-Hash gespeichert, TTL 7 Tage) → Registrierung nur mit gültigem Token |
| Passkey-Recovery | Admin (JWT) triggert Reset → Einmal-Token (Tabelle `recovery_tokens`, TTL 30 min) → User registriert neuen Passkey via `recovery/options` + `recovery/verify` |
| Bootstrap-Erkennung | `GET /api/auth/bootstrap` → Login-Seite zeigt „Admin-Setup“ (Secret) oder „Einladung“ |
| Implementiert in | `backend/app/routes/auth.py`, `auth_utils.py`, `dependencies.py`; Bibliothek `webauthn>=3.0` (DER-Signaturen laut WebAuthn-Spec §6.5.5 verifiziert) |

## 2. Sessions & Berechtigungen

| Feature | Umsetzung |
|---|---|
| JWT-Session | `PyJWT` HS256, Payload `{sub, username, is_admin, iat, exp}`; TTL 60 min (`ACCESS_TOKEN_TTL_MINUTES`) |
| Auth-Dependency | `get_current_user` (HTTPBearer) prüft Signatur + Archivstatus; `require_admin` für Admin-Routen |
| Archivierte User gesperrt | `archived_at != NULL` → 401 bei jedem geschützten Endpoint |

## 3. Aufgaben (Tasks)

| Feature | Umsetzung |
|---|---|
| CRUD | `POST/GET/PUT/DELETE /api/tasks` |
| Monatsfilter | `?month=YYYY-MM` (validiert, inkl. Jahreswechsel-Logik) |
| Datumsbereich | `?start=YYYY-MM-DD&end=...` (für „Letzte Woche kopieren“) |
| Pagination | `limit`/`offset` |
| User-Scoping | User sieht nur eigene Tasks; `user_id`-Query nur für Admins (403 sonst) |
| Admin-Override | Admin darf Tasks anderer User lesen/editieren/löschen |
| Soft-Delete | `archived_at` statt physikalischem Löschen; `DELETE` liefert 404 bei erneutem Löschen |
| Kategorie-Validierung | `category_id` muss dem Task-Besitzer gehören |
| Validierung | Beschreibung non-empty + `max_length=10000`, `fisi_area` max 255, Datumstyp erzwungen |
| Frontend | Dashboard mit Monats-Navigation, Quick-Add-Formular, Edit-Modal, Lösch-Bestätigung, „**Letzte Woche kopieren**“ (Tasks der Vorwoche via `start`/`end` laden, je +7 Tage duplizieren) |

## 4. Kategorien (FiSi-Bereiche)

| Feature | Umsetzung |
|---|---|
| CRUD | `POST/GET/PUT/DELETE /api/categories` |
| Farbe | `#RRGGBB` validiert per Regex, Standard `#4B5563` |
| Owner/Admin-Regeln | Edit/Delete nur Owner oder Admin |
| Task-Verweis | Beim Löschen werden `task.category_id` auf NULL gesetzt (keine hängenden Referenzen) |
| Frontend | Liste mit Farb-Chips, Modal mit `<input type="color">` |

## 5. Templates (HTML für PDF)

| Feature | Umsetzung |
|---|---|
| Upload | `multipart/form-data` (`POST /api/templates`), Datei max 1 MB, UTF-8 erzwungen |
| Speicherung | `/appdata/dumbbureau/templates/{user_id}/{template_id}.html` |
| Sanitizing | **bleach** mit Allowlist (Tags/Attribute/Protokolle http, https, mailto); Jinja2-Blöcke (`{{ }}`, `{% %}`, `{# #}`) werden vor dem Sanitizing per Placeholder geschützt und danach wiederhergestellt |
| Standard-Template | `is_default` Flag; beim Setzen wird das alte Default zurückgesetzt (genau ein Default) |
| Update/Delete | Name/Beschreibung/Datei/Default änderbar; Datei wird beim Löschen von Disk entfernt |
| Eingebautes Default | `pdf_generator.DEFAULT_TEMPLATE` + `frontend/templates/default.html` als Beispiel |

## 6. PDF-Export

| Feature | Umsetzung |
|---|---|
| Endpoint | `POST /api/pdf/export` `{month, template_id?, include_archived?, user_id?}` |
| Download | `GET /api/pdf/{id}` (FileResponse, JWT-geschützt); Frontend lädt per fetch+Blob (Authorization-Header bei `<a download>` nicht möglich) |
| Rendering | Jinja2 **`SandboxedEnvironment`** mit `DictLoader({})` → SSTI geblockt (`__class__.__mro__` wirft SecurityError, `config` unsichtbar), `autoescape=True` gegen HTML-Injection |
| PDF-Erzeugung | WeasyPrint ≥62; **SSRF-Schutz**: `URLFetcher(allowed_protocols=["data"])` — keine externen/file-URLs |
| Speicherung | `/appdata/dumbbureau/exports/{user_id}/{pdf_id}.pdf`, DB-Record `pdf_exports` |
| Admin | Export für andere User via `user_id` (nur Admin) |
| Default-Template | Ohne `template_id`: User-Default oder eingebautes Berichtsheft-Template |

## 7. Verschlüsselung (AES-128-GCM)

| Feature | Umsetzung |
|---|---|
| Algorithmus | AES-128-GCM (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`), authentifiziert |
| Key-Ableitung | **Argon2id** (`argon2-cffi`, `hash_secret_raw`, Type.ID, 64 MiB) aus `ENCRYPTION_KEY` (Fallback `SECRET_KEY`) → 16-Byte-Master-Key, einmalig lazy gecacht |
| Anwendung | Task-Beschreibungen + Audit-Log-Details **at rest** verschlüsselt; API liefert transparent Klartext |
| Format | `enc:v1:` + Base64(nonce(12) + ciphertext); zufällige Nonce je Eintrag |
| Abwärtskompatibel | Werte ohne Prefix (Legacy-Klartext) werden unverändert durchgereicht |
| Implementiert in | `backend/app/crypto.py`; integriert in `tasks.py`, `audit.py`, `admin.py`, `pdf.py` |

## 8. Admin-Funktionen

| Feature | Umsetzung |
|---|---|
| User-Liste | `GET /api/admin/users` inkl. `task_count`, Status (aktiv/archiviert), Admin-Flag |
| Audit-Log | `GET /api/admin/audit-log?limit&offset`, Details entschlüsselt, Usernamen aufgelöst |
| Task-Viewing | `GET /api/admin/user/{id}/tasks?month=...` (loggt `admin_viewed_tasks`) |
| Archivierung | `POST /api/admin/user/{id}/archive` (mit `reason`, Selbst-Archivierung blockiert) + `/unarchive` |
| Einladungen | `POST /api/admin/invites` (Token einmalig im Klartext) + `GET /api/admin/invites` (nur Hash/Status) |
| Audit-Aktionen | `user_registered`, `user_logged_in`, `recovery_triggered`, `passkey_recovered`, `task_created/updated/deleted`, `category_*`, `template_*`, `pdf_exported`, `invite_created`, `admin_viewed_tasks`, `user_archived/unarchived` |
| Wartung | `python -m app.maintenance` archiviert Tasks > 1 Jahr |

## 9. Frontend (Vanilla JS SPA)

| Feature | Umsetzung |
|---|---|
| Kein Build | Reine statische Dateien, nginx ausgeliefert; `Api` nutzt relativen `/api`-Pfad (nginx proxied zum Backend → keine CORS-Probleme) |
| SPA-Navigation | Hash-Router in `main.js` (`#/dashboard`, `#/categories`, `#/templates`, `#/export`, `#/admin`), keine Page-Reloads; Auth-Guard + Admin-Guard |
| Views | `views.js`: Dashboard, Kategorien, Templates, Export, Admin (Tabs: User/Audit/Invites) |
| Login | `pages/login.html` (getrennte Pre-Auth-Seite), Redirect-Schleife vermieden |
| i18n | DE/EN-Wörterbuch (`i18n.js`), Umschalter in Login + Sidebar, `data-i18n`-Attribute, Persistenz in localStorage (88 definierte, 74 genutzte Keys — konsistent) |
| Session-Handling | `storage.js` (localStorage); 401 → auto-Logout + Redirect zum Login |
| Offline-Aware | Fetch-Fehler → „Netzwerkfehler“-Meldung statt Crash |
| UX | Dark Theme (CSS-Variablen), Mobile-First (Sidebar kollabiert), Toasts, Modals, Farb-Chips, Print-Stylesheet |
| PDF-Download | Authentifizierter Download via fetch→Blob→ObjectURL |
| Invite-Code | Nach Erstellung sichtbar mit „Kopieren“-Button (clipboard API) |

## 10. Infrastruktur & Konfiguration

| Feature | Umsetzung |
|---|---|
| Ports | Frontend auf Host-Port **8360** (`FRONTEND_PORT`), Backend optional **8361** (`BACKEND_PORT`). TLS endet am eigenen Reverse Proxy; Standard-Docker-Bridge (keine feste Subnetz-Konfiguration) |
| Volle Env-Konfigurierbarkeit | Alle Variablen in `.env`/`.env.example` (Secrets, WebAuthn, TTLs, Pfade, Rate Limiting, Logging) — pydantic-settings + Compose-Defaults |
| Daten-Haltbarkeit | `APPDATA_DIR` (Host) → `/appdata/dumbbureau` (Container): db.sqlite, templates/, exports/, logs/ |
| Healthcheck | Backend `curl -f /health` (Compose), Auto-Restart `unless-stopped` |
| Datenbank | SQLite (WAL-Modus), `create_all` beim Start (idempotent), 11 Tabellen; Backups extern (z. B. Unraid) |
| Logging | Log-Level via Env, robuster Parse (Fallback INFO), Warnungen bei schwachem `SECRET_KEY`/unset `ADMIN_RECOVERY_SECRET`, globaler 500-Handler; Docker-Log-Rotation (`max-size=10m`, `max-file=3`) |
| nginx | `client_max_body_size 5m`, `/api/`-Proxy mit `proxy_read_timeout 300s`, leitet `X-Real-IP`/`X-Forwarded-For` des Reverse Proxys durch, SPA-Fallback |

## 11. Tests & Qualität

| Feature | Umsetzung |
|---|---|
| Integrationstests | `backend/tests/` — 108 Checks: Auth-Flow (23), Tasks (17), Categories/Templates (25), PDF (19), Admin (19), Crypto (5) |
| Virtueller Authenticator | Software-Security-Key (ES256, Self-Attestation, DER-Signaturen) simuliert echten YubiKey inkl. Replay-/UV-Prüfungen |
| Runner | `python tests/run_all.py` (isolierte Temp-DB je Suite) |
| Smoke-Test | Echter uvicorn-Server verifiziert: `/health`, `/api/auth/bootstrap`, Auth-Guards über HTTP |
| Versions-Pins | `webauthn>=3.0,<4` (API-Bruch zu 2.x vermieden), `cryptography>=49`, `weasyprint>=62` |
| Statische Checks | JS-Syntax (node), Compose-YAML, i18n-Key-Konsistenz |
| Lokal nicht testbar | WeasyPrint-PDF (braucht Pango → nur im Docker-Image), Browser-E2E |
