# Jahresabschluss-System - Phase 1

## Übersicht
Phase 1 implementiert die grundlegende Import-Funktionalität für:
- Bank CSV-Dateien (Kontoauszüge deutscher Banken)
- DATEV CSV-Dateien
- PDF-Dokumente (für spätere AI-Verarbeitung)

## Installation

1. **Voraussetzungen**
   - Python 3.11+
   - PostgreSQL 15+

2. **Setup**
   ```bash
   # Repository klonen (falls noch nicht geschehen)
   git clone <your-repo-url>
   cd jahresabschluss-system

   # Virtuelle Umgebung erstellen
   python -m venv venv
   
   # Aktivieren:
   # Mac/Linux:
   source venv/bin/activate
   # Windows:
   venv\Scripts\activate

   # Dependencies installieren
   pip install -r requirements.txt

   # .env Datei erstellen und anpassen
   cp .env.example .env
   ```

3. **Datenbank Setup**
   ```bash
   # PostgreSQL Datenbank erstellen
   createdb jahresabschluss
   
   # Oder mit psql:
   psql -U postgres -c "CREATE DATABASE jahresabschluss;"

   # .env anpassen mit Ihrer Datenbank-URL:
   # DATABASE_URL=postgresql://username:password@localhost:5432/jahresabschluss
   ```

4. **Datenbank initialisieren**
   ```bash
   # Option 1: Mit Python Script
   python init_db.py

   # Option 2: Mit SQL direkt
   psql -d jahresabschluss -f migrations/schema/001_create_tables.sql
   ```

## Start

```bash
# Server starten
python run.py

# Alternative: Direkt mit uvicorn
PYTHONPATH=. uvicorn src.api.main:app --reload
```

Die Anwendung ist dann verfügbar unter:
- Web-UI: http://localhost:8000
- API-Docs: http://localhost:8000/docs

## Verwendung

### Web-Interface
1. Öffnen Sie http://localhost:8000
2. Wählen Sie den entsprechenden Tab für Ihren Import-Typ
3. Ziehen Sie Dateien in den Upload-Bereich oder klicken Sie auf "Dateien auswählen"
4. Unterstützte Formate:
   - **Bank Import**: `.csv` - Kontoauszüge deutscher Banken (Format: Konto_XXXXX_DDMMYY_HHMMSS.csv)
   - **DATEV Import**: `.csv` - DATEV-Exporte (klassisch oder Belegexport)
   - **Belege**: `.pdf` - Rechnungen und Belege (werden in Phase 2 mit AI verarbeitet)

### API-Endpunkte

**Import einer Datei:**
```bash
curl -X POST "http://localhost:8000/api/imports/file" \
     -F "file=@Konto_1234567_250114_101756.csv"
```

**Import-Status abfragen:**
```bash
curl "http://localhost:8000/api/imports/status/{import_id}"
```

## Datei-Formate

### Bank CSV Format
- Semikolon-getrennt (`;`)
- Spalten:
  1. Referenznummer
  2. Buchungsdatum (DD.MM.YYYY)
  3. Betrag (Deutsches Format: 1.234,56)
  4. Valutadatum
  5. Leer/Reserviert
  6. Partner/Empfänger
  7. Verwendungszweck
  8. Kontonummer

### DATEV CSV Format
- Unterstützt klassische DATEV-Exporte und Belegexporte
- Automatische Format-Erkennung
- Verschiedene Encodings werden unterstützt (CP1252, UTF-8, etc.)

## Datei-Struktur Phase 1

```
jahresabschluss-system/
├── run.py                 # Start-Script
├── init_db.py            # DB-Initialisierung
├── requirements.txt      # Python Dependencies
├── .env.example          # Umgebungsvariablen-Vorlage
├── .gitignore
│
├── src/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI App
│   │   └── routers/
│   │       ├── __init__.py
│   │       └── imports.py       # Import-Endpunkte
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py           # Konfiguration
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── importers/          # Import-Module
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── bank_csv.py    # Bank CSV Importer
│   │   │   ├── datev.py
│   │   │   ├── pdf.py
│   │   │   └── factory.py
│   │   └── database/          # Datenbank
│   │       ├── __init__.py
│   │       ├── connection.py
│   │       └── models.py
│   └── presentation/
│       ├── __init__.py
│       └── templates/
│           └── index.html     # Web-UI
│
└── migrations/
    └── schema/
        └── 001_create_tables.sql
```

## Troubleshooting

**Import-Fehler beim Start:**
```bash
# Stellen Sie sicher, dass Sie im Hauptverzeichnis sind und verwenden:
python run.py
```

**Datenbankverbindung fehlgeschlagen:**
- Prüfen Sie die DATABASE_URL in .env
- Format: `postgresql://user:password@localhost:5432/jahresabschluss`
- Stellen Sie sicher, dass PostgreSQL läuft:
  ```bash
  # Mac:
  brew services list | grep postgresql
  # Linux:
  systemctl status postgresql
  ```

**Import schlägt fehl:**
- Prüfen Sie das Dateiformat
- Bei Bank-CSV: Dateiname sollte "Konto" enthalten
- Bei DATEV-CSV: Beliebiger Name, System erkennt Format automatisch
- Logs prüfen in der Konsole

**Module nicht gefunden:**
- Verwenden Sie `python run.py` statt direktes Ausführen
- Stellen Sie sicher, dass die virtuelle Umgebung aktiviert ist
- `pip install -r requirements.txt` wurde ausgeführt

## Beispiel-Dateien

Sie können diese Beispiel-Dateien zum Testen verwenden:
- Bank CSV: `Konto_3222594_250114_101756.csv` (Ihre bereitgestellte Datei)
- DATEV CSV: Beliebige DATEV-Export-Datei
- PDF: Beliebige Rechnung als PDF

## Nächste Schritte (Phase 2)

Phase 2 wird hinzufügen:
- Azure AI Document Intelligence Integration
- Claude API für intelligente Kontierung
- Automatisches Matching und Buchungsvorschläge

## Support

Bei Problemen:
1. Prüfen Sie die Konsolen-Ausgabe
2. Schauen Sie in die API-Docs: http://localhost:8000/docs
3. Prüfen Sie die Logs
4. Erstellen Sie ein Issue im Repository