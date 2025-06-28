# Quick Start Guide - Phase 1

## 🚀 Schnellstart (5 Minuten)

### Option 1: Mit Docker (Empfohlen)

```bash
# 1. .env Datei erstellen
cp .env.example .env

# 2. Docker Container starten
docker-compose up -d

# 3. Öffnen Sie http://localhost:8000
```

### Option 2: Lokale Installation

```bash
# 1. Python Virtual Environment erstellen
python -m venv venv

# 2. Aktivieren
# Mac/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# 3. Dependencies installieren
pip install -r requirements.txt

# 4. .env Datei erstellen und anpassen
cp .env.example .env
# Bearbeiten Sie .env und setzen Sie DATABASE_URL

# 5. Datenbank initialisieren
python init_db.py

# 6. Server starten
python run.py
```

## 📁 Unterstützte Dateiformate

### 1. **Zahlungskonten (Neuer gemeinsamer Tab)**

#### Bank CSV
- Dateiendung: `.csv`
- Beispiel: `Konto_3222594_250114_101756.csv`
- Format: Semikolon-getrennt, 8 Spalten
- Wird automatisch als Bank-Import erkannt wenn "Konto" im Dateinamen

#### PayPal CSV
- Dateiendung: `.csv`
- Beispiel: `Download.CSV`
- Format: Komma-getrennt, UTF-8
- Enthält Transaktionsinformationen wie Datum, Betrag, Gebühren, Partner

#### Stripe CSV
- Dateiendung: `.csv`
- Beispiel: `unified_payments4.csv`
- Format: Komma-getrennt, UTF-8
- Enthält Payment-Daten mit umfangreichen Metadaten

### 2. **DATEV CSV**
- Dateiendung: `.csv`
- Beliebiger Dateiname (ohne "Konto", "PayPal", "Stripe")
- Format: Windows-1252 oder UTF-8 Encoding
- Automatische Format-Erkennung (Klassisch oder Belegexport)

### 3. **Belege**
- Dateiendungen: `.pdf`, `.jpg`, `.jpeg`, `.png`
- Werden für Phase 2 (AI-Verarbeitung) gespeichert

## 🧪 Test mit Beispieldateien

1. Öffnen Sie http://localhost:8000
2. Wählen Sie den passenden Tab:
   - **Zahlungskonten**: Für Bank-, PayPal- und Stripe-Importe
   - **DATEV Import**: Für DATEV-Exporte
   - **Belege**: Für PDF-Rechnungen und Bilddateien
3. Im Zahlungskonten-Tab:
   - Wählen Sie den Provider (Bank, PayPal oder Stripe)
   - Optional: Geben Sie Kontoinformationen ein
   - Laden Sie die entsprechende CSV-Datei hoch
4. Ziehen Sie eine Datei in den Upload-Bereich oder klicken Sie "Dateien auswählen"

## 🔍 API Dokumentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 📊 Datenbank prüfen

```bash
# Mit Docker:
docker-compose exec postgres psql -U postgres -d jahresabschluss

# Lokal:
psql -d jahresabschluss

# Nützliche Queries:
\dt                          -- Alle Tabellen anzeigen
SELECT * FROM import_batches;  -- Import-Historie
SELECT source_type, COUNT(*) FROM import_batches GROUP BY source_type; -- Import-Statistik
SELECT * FROM imported_transactions LIMIT 10;  -- Importierte Transaktionen
```

## 🐛 Troubleshooting

### Import-Module nicht gefunden
```bash
# Stellen Sie sicher, dass Sie im Hauptverzeichnis sind:
python run.py
```

### Datenbankverbindung fehlgeschlagen
```bash
# Prüfen Sie PostgreSQL Status:
# Mac:
brew services list | grep postgresql
# Linux:
systemctl status postgresql
# Docker:
docker-compose ps
```

### Permission denied beim Upload
```bash
# Upload-Verzeichnis erstellen:
mkdir -p uploads
chmod 755 uploads
```

### PayPal/Stripe-Import wird nicht erkannt
- PayPal: Datei sollte "paypal" im Namen haben oder "Download.CSV" heißen
- Stripe: Datei sollte "stripe", "payments" oder "unified_payments" im Namen haben
- Alternative: Verwenden Sie den "Zahlungskonten" Tab und wählen Sie den Provider manuell

### Bank-Import wird nicht erkannt
- Stellen Sie sicher, dass "Konto" im Dateinamen vorkommt
- Beispiel: `Konto_1234567_250114_101756.csv`
- Alternative: Verwenden Sie den "Zahlungskonten" Tab und wählen Sie "Bank"

## 📈 Nächste Schritte (Phase 2)

Nach erfolgreichem Test von Phase 1:
1. Azure Form Recognizer API Keys besorgen
2. Anthropic Claude API Key besorgen
3. .env mit API Keys aktualisieren
4. Phase 2 Features aktivieren:
   - Automatische Dokumentenerkennung für PDFs/Bilder
   - Intelligente Kontierung mit Claude
   - Automatisches Matching von Zahlungen zu Belegen

## 🆘 Support

Bei Problemen:
1. Logs prüfen: `docker-compose logs -f app`
2. Konsolen-Output beachten
3. API Docs konsultieren: http://localhost:8000/docs
4. Beispiel-Importe:
   ```bash
   # PayPal
   curl -X POST "http://localhost:8000/api/imports/file" \
        -F "file=@Download.CSV" \
        -F "account_name=PayPal Geschäft"
   
   # Stripe
   curl -X POST "http://localhost:8000/api/imports/file" \
        -F "file=@unified_payments4.csv" \
        -F "account_name=Stripe Produktion"
   ```