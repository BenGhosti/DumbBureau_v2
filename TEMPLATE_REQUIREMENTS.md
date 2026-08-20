# PDF-Template-Anforderungen

Diese Datei beschreibt, wie eine PDF-Vorlage (Template) aufgebaut sein muss,
damit DumbBureau sie korrekt verarbeitet und die Task-Einträge sauber
einbettet — nicht als lose Tabelle über einem Hintergrundbild, sondern als
Teil der eigentlichen Dokumentstruktur.

**Diese Doku beschreibt den tatsächlichen IST-Zustand des Codes**
(`backend/app/pdf_generator.py`, `backend/app/routes/templates.py`), nicht
einen Wunschzustand. Wo der Code Grenzen oder Überraschungen hat, steht das
hier explizit — inklusive der Stellen, die technisch funktionieren, aber
beim Bauen einer eigenen Vorlage stolpern lassen können.

## 1. Grundformat

- Eine Datei, reines **HTML**, UTF-8-kodiert, max. **1 MB**.
- Kein separates CSS-File, kein Referenzieren externer Ressourcen (Details
  unten unter "Was verboten ist"). Alles Nötige muss **in der Datei selbst**
  stehen.
- Kein Template-Vererbungssystem: `{% extends %}`, `{% include %}` und
  `{% import %}` sind blockiert (siehe Abschnitt 4). Jede Vorlage ist
  eigenständig, es gibt kein gemeinsames Basis-Layout.

## 2. Verfügbare Variablen

Der Renderer (Jinja2, siehe Abschnitt 4) bekommt exakt diesen Kontext:

| Variable | Typ | Inhalt |
|---|---|---|
| `month` | String | Exportmonat im Format `YYYY-MM`, z. B. `2026-08` |
| `user.username` | String | Benutzername des Ziel-Users |
| `user.email` | String \| `None` | E-Mail, kann fehlen — immer mit `{% if user.email %}` prüfen |
| `tasks` | Liste | Alle Task-Einträge des Monats (Details unten) |
| `generated_at` | String | ISO-8601-Zeitstempel der PDF-Erzeugung |

Jeder Eintrag in `tasks` ist ein Objekt mit:

| Feld | Typ | Inhalt |
|---|---|---|
| `date` | String | ISO-Datum, z. B. `2026-08-15` |
| `category` | String \| `None` | Name der Kategorie — **kein** Farbwert! (siehe Abschnitt 6) |
| `description` | String | Die eigentliche Tätigkeitsbeschreibung (automatisch escaped, siehe Abschnitt 5) |
| `fisi_area` | String \| `None` | Optionales Freitextfeld |

Es gibt **keine** `category_color`, `category_id` oder ähnliche Felder im
PDF-Kontext — diese existieren nur im Frontend/API, nicht im PDF-Renderer.
Eine Vorlage, die versucht farbige Kategorie-Chips wie im Dashboard
darzustellen, muss selbst eine Farblogik implementieren (z. B. über
`{% if t.category == "Support" %}`-Verzweigungen) oder darauf verzichten.

## 3. Struktur für "integriertes" Layout statt Tabelle-auf-Hintergrundbild

Der mitgelieferte Standard-Fallback (siehe Abschnitt 7) verwendet eine
einzelne `<table>` für alle Tasks. Das ist die einfachste, aber nicht die
einzige Möglichkeit. Da der volle Kontext (`tasks`, `user`, `month`) als
strukturierte Daten ankommt — nicht als vorgerendertes HTML-Fragment —,
kann eine Vorlage jede beliebige HTML-Struktur um die Daten herum bauen:

- **Karten pro Task** statt Tabellenzeilen (`{% for t in tasks %}<div
  class="task-card">...</div>{% endfor %}`)
- **Gruppierung nach Kategorie oder Woche** (in Jinja2 mit `{% for %}` +
  manueller Datumslogik machbar, da Jinja2 kein `groupby`-Filter für
  beliebige Objekte ohne Sortierung mitbringt — die Liste ist bereits nach
  Datum aufsteigend sortiert, s. `routes/pdf.py`)
- **Kopf-/Fußzeilen mit Platzhaltern**, die feststehende Layout-Elemente
  (Firmenlogo als `data:`-Bild **in einem `<style>`-Block**, siehe
  Abschnitt 6, Auszubildenden-Info, Ausbilder-Feld für Unterschrift) mit
  den dynamischen Daten kombinieren — die Trennung zwischen "festes
  Layout" und "eingesetzte Daten" entsteht rein durch die Template-Autorin,
  nicht durch das System

Wichtig: Es gibt **keinen** separaten "Hintergrundbild-Mechanismus". Ein
Hintergrundbild ist technisch nur über CSS erreichbar (`background-image`
mit `data:`-URI, siehe Abschnitt 6) — es gibt keinen speziellen
`background`-Parameter, den das System getrennt von den Daten einsetzt. Ein
Template, das wie ein amtliches Formular mit fest positionierten Feldern
aussehen soll, muss das komplett selbst per CSS (`position: absolute` +
`data:`-Hintergrundbild) nachbauen — das System unterstützt das technisch
(WeasyPrint kann CSS-Positionierung), bietet aber keine Hilfestellung dafür.

## 4. Sicherheits-Sandbox (was technisch blockiert wird)

Der Renderer nutzt Jinja2s `SandboxedEnvironment` mit einem **leeren**
`DictLoader({})`:

- `{{ ausdruck }}` und `{% steuerung %}` funktionieren normal.
- `{% include "irgendwas" %}`, `{% extends "irgendwas" %}` und
  `{% import "irgendwas" %}` schlagen fehl, weil der Loader keine Dateien
  kennt — nicht weil sie explizit verboten sind, sondern weil es schlicht
  nichts zu laden gibt.
- Die Sandbox blockiert außerdem gefährliche Python-Introspektion
  (`{{ "".__class__ }}` und ähnliches) — Standard-Jinja2-Sandboxing.

## 5. Escaping — was automatisch sicher ist

`autoescape=True` ist aktiv. Das bedeutet: **`{{ t.description }}` wird
automatisch HTML-escaped.** Ein Task mit der Beschreibung `<b>fett</b>`
erscheint im PDF wörtlich als Text `<b>fett</b>`, nicht als fett
formatierter Text — das ist so gewollt (verhindert, dass ein User über
seinen eigenen Task-Text die PDF-Struktur bricht) und muss beim
Vorlagenbau nicht zusätzlich abgesichert werden.

Falls eine Vorlage bewusst rohes HTML aus einer Variable einsetzen möchte,
ginge das nur über `{{ variable | safe }}` — für die aktuell verfügbaren
Variablen (`description`, `fisi_area`, `category`, `username`) gibt es
dafür keinen legitimen Anwendungsfall; das würde die eigene
Injection-Absicherung wieder aufheben.

## 6. Was beim Hochladen entfernt wird (`sanitize_template_html`)

Jeder Upload/jedes Update läuft durch einen HTML-Sanitizer
(`bleach.clean`), **bevor** die Datei gespeichert wird. Das betrifft nur
reines HTML — Jinja2-Ausdrücke (`{{ ... }}`, `{% ... %}`, `{# ... #}`)
werden vorher geschützt und danach wieder eingesetzt, sind also von der
Bereinigung nicht betroffen.

**Erlaubte Tags:** `a, b, br, blockquote, caption, col, colgroup, div, em,
h1–h6, hr, i, img, li, ol, p, pre, span, strong, table, tbody, td, tfoot,
th, thead, tr, ul, u, small, sub, sup, section, header, footer, article,
main, aside, style`

**Wichtige Konsequenz — bitte unbedingt beachten:** `html`, `head`,
`body`, `title`, `meta`, `!DOCTYPE` stehen **nicht** auf der erlaubten
Liste und werden beim Speichern komplett entfernt. Ein hochgeladenes
Template mit vollständiger `<html><head>...</head><body>...</body></html>`-
Struktur verliert diese Hüll-Tags beim Upload — `<style>` bleibt zwar
erhalten, landet aber freischwebend an der Stelle im Dokument, an der es
im Original stand (meist mitten im sichtbaren Textfluss statt im `<head>`).
Das führt nicht zu einem Fehler (WeasyPrint akzeptiert das HTML-Fragment
trotzdem und erzeugt ein PDF), aber die Semantik "CSS gilt global für das
ganze Dokument" bleibt zwar technisch erhalten, ist aber leicht
überraschend beim Anschauen der gespeicherten Datei.

**Empfehlung für Template-Autoren:** `<style>` möglichst als erstes
Element im Template platzieren (nicht in einem `<head>`, den gibt es nach
dem Speichern ohnehin nicht mehr), damit die CSS-Regeln beim Lesen der
gespeicherten Datei sofort auffindbar sind.

**Erlaubte Attribute:**
- Auf allen erlaubten Tags: `class`, `id`, `title`, `style` — **aber siehe
  die kritische Einschränkung zu `style` direkt im Anschluss.**
- `a`: `href`, `target`
- `img`: `src`, `alt`, `width`, `height` — **aber siehe die kritische
  Einschränkung zu `img`/`src` unten.**
- `td`/`th`: `colspan`, `rowspan`, `align`, `valign`
- `table`: `border`, `cellpadding`, `cellspacing`, `width`
- `col`: `width`, `span`

### ⚠ Das `style`-Attribut wird immer geleert — nutzt es trotzdem nicht

`style` steht zwar formal auf der erlaubten Attributliste, aber der
Sanitizer (`bleach`) läuft **ohne konfigurierten CSS-Sanitizer**. Ohne den
verwirft `bleach` grundsätzlich **jeden** `style`-Attributwert vollständig
— unabhängig vom Inhalt. Getestet und bestätigt:

```
Eingabe:  <p style="text-align: center;">centered</p>
Ergebnis: <p style="">centered</p>

Eingabe:  <div style="color: red; font-weight: bold;">Test</div>
Ergebnis: <div style="">Test</div>
```

Das Attribut landet leer im gespeicherten Template — **jegliches
Inline-Styling per `style="..."` ist praktisch wirkungslos**, obwohl der
Upload dabei keinen Fehler wirft. Für Layout/Optik ausschließlich einen
`<style>`-**Block** verwenden (siehe Abschnitt 3/6 zur Platzierung), nicht
das `style`-Attribut auf einzelnen Tags.

### ⚠ `<img src="...">` mit `data:`-URIs funktioniert NICHT

Erlaubte URL-Schemata für `href`/`src`: `http`, `https`, `mailto` —
**nicht** `data:`. Trotz `img`/`src` auf der erlaubten Attribut-Liste
verliert ein `<img src="data:image/png;base64,...">` beim Speichern sein
komplettes `src`-Attribut:

```
Eingabe:  <img src="data:image/png;base64,iVBORw0KGgo=" alt="Logo">
Ergebnis: <img alt="Logo">
```

Da externe `http(s)`-Bilder beim PDF-Rendern selbst wieder blockiert
werden (Abschnitt 8, SSRF-Schutz), bleibt **`<img>` für praktische Zwecke
komplett unbrauchbar** — jede Bildquelle scheitert an einer der beiden
Hürden (Sanitizer beim Upload oder URLFetcher beim Rendern).

**Der einzige tatsächlich funktionierende Weg für Logos/Hintergrundbilder**
ist ein `data:`-URI **innerhalb eines `<style>`-Blocks** (nicht als
`img`-Tag, nicht als `style`-Attribut) — Größenangaben (`width`/`height`)
müssen ebenfalls in der CSS-Klasse stehen, nicht als `style="..."` auf
dem Element selbst, weil Letzteres wie oben gezeigt immer geleert wird:

```html
<style>
  .logo {
    width: 200px;
    height: 80px;
    background-image: url('data:image/png;base64,iVBORw0KGgo=');
    background-size: contain;
  }
</style>
<div class="logo"></div>
```

Getestet und bestätigt: Dieser komplette Block übersteht `sanitize_template_html`
unverändert — `<style>`-Block-Inhalte werden von `bleach` als reiner Text
behandelt, nicht als HTML-Attribut, weshalb `data:`-URIs darin erhalten
bleiben.

## 7. Referenz-Vorlage

Der eingebaute Fallback (verwendet, wenn kein eigenes Template hochgeladen
oder keins als Standard markiert wurde) lebt als Python-Konstante in
`backend/app/pdf_generator.py` (`DEFAULT_TEMPLATE`). Sie ist die
**einzige** Quelle der Wahrheit für das Fallback-Verhalten — der Text
weiter oben in dieser Doku (Abschnitt 2/3) basiert direkt darauf.

Es gab zusätzlich `frontend/templates/default.html` mit identischem
Inhalt, aber ohne jede Verdrahtung (vom Backend nicht geladen, im Frontend
nirgends verlinkt) — diese Datei und das dazugehörige, sonst leere
Verzeichnis wurden entfernt, um keine zwei divergierenden Kopien derselben
Vorlage im Repo zu haben. Falls künftig ein "Standard-Vorlage
herunterladen"-Button in der Templates-Ansicht gewünscht ist, sollte er
`pdf_generator.DEFAULT_TEMPLATE` über einen neuen Backend-Endpunkt
ausliefern, statt eine zweite Kopie im Frontend zu pflegen.

## 8. Sonstige technische Grenzen

- **Kein Netzwerkzugriff beim Rendern:** WeasyPrint bekommt einen
  `URLFetcher`, der ausschließlich `data:`-URIs erlaubt. Ein `<img
  src="https://...">` in einer Vorlage lädt **nicht** — das Bild bleibt
  leer/fehlt im PDF, es gibt keine Fehlermeldung darüber.
- **Kein Zugriff auf andere Monate/User:** Der Kontext enthält
  ausschließlich Daten des angefragten Exports (ein User, ein Monat). Eine
  Vorlage kann nicht z. B. "letzten Monat zum Vergleich" einblenden.
- **Seitenumbrüche:** WeasyPrint unterstützt Standard-CSS-Paginierung
  (`page-break-*`, `@page`-Regeln) — das ist nicht speziell für dieses
  System angepasst, reguläres WeasyPrint/CSS-Print-Verhalten gilt.
- **PDF-Dateiname beim Download** ist fest `berichtsheft-{month}.pdf`
  (siehe `routes/pdf.py`), unabhängig vom Template — nicht anpassbar über
  die Vorlage selbst.
