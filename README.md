# Jahresabschluss-System - Phase 1

## Übersicht
Phase 1 implementiert die grundlegende Import-Funktionalität für:
- Bank CSV-Dateien (Kontoauszüge deutscher Banken)
- PayPal CSV-Exporte
- Stripe CSV-Exporte
- Mollie CSV-Exporte
- DATEV CSV-Dateien
- PDF-Dokumente und Bilddateien (JPEG, PNG) für spätere AI-Verarbeitung

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

### Unterstützte Formate

#### Zahlungskonten Tab
Kombiniert verschiedene Zahlungsdienstleister:
- **Bank Import**: `.csv` - Kontoauszüge deutscher Banken (Format: Konto_XXXXX_DDMMYY_HHMMSS.csv)
- **PayPal Import**: `.csv` - PayPal-Transaktionsexporte
- **Stripe Import**: `.csv` - Stripe Payments Exporte
- **Mollie Import**: `.csv` - Mollie Settlement Reports

#### DATEV Tab
- **DATEV Import**: `.csv` - DATEV-Exporte (klassisch oder Belegexport)

#### Belege Tab  
- **Dokumente**: `.pdf`, `.jpg`, `.jpeg`, `.png` - Rechnungen und Belege (werden in Phase 2 mit AI verarbeitet)

### API-Endpunkte

**Import einer Datei:**
```bash
# Bank CSV
curl -X POST "http://localhost:8000/api/imports/file" \
     -F "file=@Konto_1234567_250114_101756.csv" \
     -F "account_name=Geschäftskonto Sparkasse" \
     -F "iban=DE12345678901234567890" \
     -F "bic=DEUTDEFF"

# PayPal CSV
curl -X POST "http://localhost:8000/api/imports/file" \
     -F "file=@Download.CSV" \
     -F "account_name=PayPal Geschäftskonto"

# Stripe CSV
curl -X POST "http://localhost:8000/api/imports/file" \
     -F "file=@unified_payments4.csv" \
     -F "account_name=Stripe Hauptkonto"

# Mollie CSV
curl -X POST "http://localhost:8000/api/imports/file" \
     -F "file=@mollie_settlement.csv" \
     -F "account_name=Mollie Geschäftskonto"
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

### PayPal CSV Format
- Komma-getrennt (`,`)
- Wichtige Spalten:
  - Datum, Uhrzeit
  - Name (Transaktionspartner)
  - Typ (Transaktionstyp)
  - Status
  - Währung
  - Brutto, Gebühr, Netto
  - Transaktionscode
  - Betreff

### Stripe CSV Format
- Komma-getrennt (`,`)
- Wichtige Spalten:
  - id (Stripe ID)
  - Created date (UTC)
  - Amount (in Cents)
  - Fee
  - Currency
  - Status
  - Customer Email
  - Description
  - Metadata-Felder

### Mollie CSV Format
- Komma-getrennt (`,`)
- Wichtige Spalten:
  - Date
  - Payment method
  - Currency
  - Amount
  - Status
  - ID (Mollie Transaktions-ID)
  - Description
  - Consumer name
  - Settlement amount
  - Settlement reference

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
│   │   │   ├── paypal.py      # PayPal CSV Importer
│   │   │   ├── stripe.py      # Stripe CSV Importer
│   │   │   ├── mollie.py      # Mollie CSV Importer
│   │   │   ├── datev.py       # DATEV Importer
│   │   │   ├── pdf.py         # PDF/Image Importer
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
- Bei PayPal-CSV: Typischerweise "Download.CSV"
- Bei Stripe-CSV: Sollte "payments" oder "stripe" im Namen haben
- Bei Mollie-CSV: Sollte "mollie" im Namen haben (z.B. mollie*settlement*.csv)
- Bei DATEV-CSV: Beliebiger Name, System erkennt Format automatisch
- Logs prüfen in der Konsole

**Mollie Settlement Reports:**
- Mollie erstellt oft mehrere Settlement-Dateien pro Monat
- Jede Datei enthält eine Settlement-Referenz
- Dateien können über den "Zahlungskonten" Tab gebündelt importiert werden
- Settlement Amount ist der Nettobetrag nach Gebühren

**Module nicht gefunden:**
- Verwenden Sie `python run.py` statt direktes Ausführen
- Stellen Sie sicher, dass die virtuelle Umgebung aktiviert ist
- `pip install -r requirements.txt` wurde ausgeführt

## Beispiel-Dateien

Sie können diese Beispiel-Dateien zum Testen verwenden:
- Bank CSV: `Konto_3222594_250114_101756.csv`
- PayPal CSV: `Download.CSV` 
- Stripe CSV: `unified_payments4.csv`
- Mollie CSV: `mollie*settlement*.csv`
- DATEV CSV: Beliebige DATEV-Export-Datei
- PDF/Bilder: Beliebige Rechnung als PDF, JPEG oder PNG

## Nächste Schritte (Phase 2)

Phase 2 wird hinzufügen:
- Azure AI Document Intelligence Integration
- Claude API für intelligente Kontierung
- Automatisches Matching und Buchungsvorschläge
- Intelligente Kategorisierung von PayPal/Stripe/Mollie Transaktionen
- Automatische Gebührenbuchungen für Payment Provider

## Support

Bei Problemen:
1. Prüfen Sie die Konsolen-Ausgabe
2. Schauen Sie in die API-Docs: http://localhost:8000/docs
3. Prüfen Sie die Logs
4. Erstellen Sie ein Issue im Repository