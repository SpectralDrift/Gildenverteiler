# Gildenverteiler

Eine lokale Webseite, die Wikinger anhand ihrer Gildenranglisten optimal und
innerhalb festgelegter Größenbereiche auf genau sechs Gilden verteilt. Es werden nur Module
aus der Python-Standardbibliothek verwendet.

## Starten

Für den späteren HTTPS-Zugriff über Tailscale Funnel:

```bash
python3 server.py
```

Der Server fragt das gemeinsame Passwort zweimal verdeckt ab. Es muss mindestens
16 Zeichen lang sein und wird nur im Arbeitsspeicher gehalten. Der Dienst bleibt
auf `127.0.0.1:8888` beschränkt; Tailscale übernimmt später HTTPS.

Für einen lokalen Test ohne HTTPS muss die unsichere Cookie-Ausnahme bewusst
aktiviert werden:

```bash
python3 server.py --allow-insecure-http
```

Danach `http://127.0.0.1:8888` öffnen. Diese Ausnahme nicht für einen
öffentlichen Funnel verwenden.

Anmeldungen gelten zwölf Stunden. Fehlversuche führen nicht zu einer gemeinsamen
Sperre, da alle öffentlichen Funnel-Zugriffe am lokalen Server über dieselbe
Proxy-Adresse ankommen können.

## Wertung

Bei `m` Gilden gibt der erste Wunsch `m` Punkte, der zweite `m - 1` Punkte und
so weiter. Der Optimierer maximiert die Gesamtpunktzahl. Gleichzeitig müssen
die eingestellten Größenbereiche der sechs Gilden eingehalten werden. Minimum
und Maximum lassen sich für jede Gilde getrennt festlegen; gleiche Werte ergeben
eine exakte Größe. Zulässig sind ganzzahlige Größen von 2 bis 8.

„egal“ kann an beliebigen Positionen stehen. Alle nicht ausdrücklich genannten
Gilden sind gleichwertig und erhalten die Punktzahl der besten mit „egal“
belegten Position. Gibt es mehrere optimale Lösungen, wird bei jeder Berechnung mit
sicherem Systemzufall gleichmäßig eine davon ausgewählt.

Die aktuelle Konfiguration kann unter einem Namen als einzelne JSON-Datei im
Ordner `configurations/` auf dem Raspberry Pi gespeichert und nach Anmeldung
wieder geladen werden. Enthalten sind Gilden, Wikinger und Ranglisten.

Lokale Standardnamen können als JSON-Liste in `default_vikings.json` abgelegt
werden. Diese Datei wird von Git ignoriert. Fehlt sie oder ist sie ungültig,
verwendet die Anwendung automatisch `Wikinger1` bis `Wikinger18`.

Tests starten mit:

```bash
python3 -m unittest -v
```
