# Jahresabschluss-System - Phase 1

## Übersicht
Phase 1 implementiert die grundlegende Import-Funktionalität für:
- Bank XML-Dateien (GDPdU-Format)
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
2. Ziehen Sie Dateien in den Upload-Bereich oder klicken Sie auf "Dateien auswählen"
3. Unterstützte Formate:
   - `.xml` - Bank-Exporte im GDPdU-Format
   - `.csv` - DATEV-Exporte (Dateiname sollte "datev" enthalten)
   - `.pdf` - Belege (werden gespeichert für Phase 2 AI-Verarbeitung)

### API-Endpunkte

**Import einer Datei:**
```bash
curl -X POST "http://localhost:8000/api/imports/file" \
     -F "file=@bank_export.xml"
```

**Import-Status abfragen:**
```bash
curl "http://localhost:8000/api/imports/status/{import_id}"
```

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
│   │   │   ├── bank_xml.py
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
# NICHT: python start_phase1.py
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
- Bei CSV-Dateien: Stellen Sie sicher, dass "datev" im Dateinamen vorkommt
- Logs prüfen in der Konsole

**Module nicht gefunden:**
- Verwenden Sie `python run.py` statt direktes Ausführen
- Stellen Sie sicher, dass die virtuelle Umgebung aktiviert ist
- `pip install -r requirements.txt` wurde ausgeführt

## Beispiel-Dateien

Sie können diese Beispiel-Dateien zum Testen verwenden:
- Bank XML: Die im Anhang bereitgestellte `Konto_3222594_250114_101756.xml`
- DATEV CSV: Beliebige DATEV-Export-Datei (Dateiname sollte "datev" enthalten)
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