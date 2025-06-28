# Jahresabschluss-System mit AI - Phase 1 & 2

Ein intelligentes System für die Automatisierung von Jahresabschlüssen mit KI-Unterstützung.

## 🌟 Features

### Phase 1 - Basis Import-System ✅
- **Multi-Format Import**: Bank CSV, PayPal, Stripe, Mollie, DATEV
- **Dokumenten-Upload**: PDF, JPEG, PNG für spätere Verarbeitung
- **Transaktions-Management**: Verwaltung und Überprüfung importierter Transaktionen
- **Web-Interface**: Benutzerfreundliche Oberfläche mit Alpine.js

### Phase 2 - AI Integration ✅
- **Automatische Dokumentenextraktion**: Azure Document Intelligence für PDFs/Bilder
- **Intelligente Kontierung**: Claude AI generiert SKR04-konforme Buchungsvorschläge
- **Smart Matching**: Automatische Zuordnung von Dokumenten zu Transaktionen
- **Auto-Booking**: Automatische Buchung bei hoher Konfidenz (>80%)

## 🚀 Quick Start

### Option 1: Docker (Empfohlen)

```bash
# 1. Repository klonen
git clone <your-repo-url>
cd jahresabschluss-system

# 2. Environment konfigurieren
cp .env.example .env
# Bearbeiten Sie .env und fügen Sie Ihre API Keys ein

# 3. Docker Container starten
docker-compose up -d

# 4. Öffnen Sie http://localhost:8000
```

### Option 2: Lokale Installation

```bash
# 1. Python Virtual Environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Dependencies installieren
pip install -r requirements.txt

# 3. Datenbank initialisieren
python init_db.py

# 4. Server starten
python run.py
```

## 📋 Voraussetzungen

- Python 3.11+
- PostgreSQL 15+
- Redis (optional, für AI Caching)
- Azure Cognitive Services Account (für Phase 2)
- Anthropic Claude API Key (für Phase 2)

## 🔧 Konfiguration

### Essenzielle Umgebungsvariablen

```env
# Datenbank
DATABASE_URL=postgresql://user:pass@localhost/jahresabschluss

# Phase 2: AI Services (optional)
AZURE_FORM_RECOGNIZER_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_FORM_RECOGNIZER_KEY=your-key
ANTHROPIC_API_KEY=your-anthropic-key
```

### AI Services einrichten

#### Azure Document Intelligence
1. Azure Portal → Cognitive Services → Form Recognizer erstellen
2. Endpoint und Key kopieren
3. In .env eintragen

#### Claude API
1. [Anthropic Console](https://console.anthropic.com/) öffnen
2. API Key generieren
3. In .env eintragen

## 📁 Unterstützte Dateiformate

### Import-Formate
- **Bank CSV**: Deutsche Banken (Sparkasse, Commerzbank, etc.)
- **PayPal CSV**: Transaktionsexporte
- **Stripe CSV**: Unified payments export
- **Mollie CSV**: Settlement reports
- **DATEV CSV**: Buchungsexporte

### Dokumente (für AI-Verarbeitung)
- **PDF**: Rechnungen, Belege
- **JPEG/PNG**: Gescannte Dokumente, Fotos von Belegen

## 🔄 Workflow

### 1. Import (Phase 1)
```
Datei Upload → Parsing → Speicherung → Transaktionsübersicht
```

### 2. AI-Verarbeitung (Phase 2)
```
Dokument → Azure Extraction → Transaction Matching → Claude Booking → Auto-Book
```

## 📊 API Endpoints

### Phase 1 - Import
- `POST /api/imports/file` - Datei importieren
- `GET /api/imports/list` - Import-Historie
- `GET /api/imports/{id}/transactions` - Transaktionen anzeigen

### Phase 2 - AI Processing
- `POST /api/ai/process/{document_id}` - Dokument verarbeiten
- `POST /api/ai/process/batch` - Batch-Verarbeitung
- `POST /api/ai/match/find` - Transaktionen matchen
- `GET /api/ai/suggestions/{document_id}` - Buchungsvorschläge

## 🧪 Testing

### System Health Check
```bash
curl http://localhost:8000/health
```

### AI Services Status
```bash
curl http://localhost:8000/api/ai/stats
```

### Dokument verarbeiten
```bash
# Mit Auto-Booking
curl -X POST "http://localhost:8000/api/ai/process/{document_id}?auto_book=true"
```

## 📈 Konfidenz-Level

### Dokument-Extraktion
- **Hoch** (>90%): Alle Felder eindeutig erkannt
- **Mittel** (70-90%): Hauptfelder erkannt
- **Niedrig** (<70%): Manuelle Prüfung erforderlich

### Transaction Matching
- **Perfekt** (>95%): Betrag + Datum + Referenz stimmen
- **Sehr gut** (>85%): Betrag + Datum stimmen überein
- **Gut** (>70%): Betrag stimmt, Datum ähnlich
- **Unsicher** (<70%): Nur als Vorschlag

### Auto-Booking Schwellwerte
- **Automatisch** (>85%): Buchung wird erstellt
- **Review** (70-85%): Manuelle Bestätigung
- **Manuell** (<70%): Vollständige manuelle Eingabe

## 🐛 Troubleshooting

### Import-Probleme
- Prüfen Sie das Dateiformat
- Bank CSV: "Konto" im Dateinamen
- PayPal: "Download.CSV" oder "paypal" im Namen
- Encoding: UTF-8 oder Windows-1252

### AI Service Fehler

**Azure nicht verfügbar**
- API Key prüfen
- Endpoint muss mit `/` enden
- Firewall/Proxy Einstellungen

**Claude Fehler**
- API Key gültig?
- Rate Limits beachten
- Modell verfügbar?

### Performance
- Redis für Caching aktivieren
- Batch-Processing für viele Dokumente
- Rate Limits anpassen

## 🔒 Sicherheit

- API Keys nur in Umgebungsvariablen
- Niemals Keys in Code committen
- Regelmäßige Key-Rotation
- HTTPS in Produktion verwenden

## 📚 Architektur

```
├── API Layer (FastAPI)
│   ├── Import Routes
│   └── AI Processing Routes
├── Application Services
│   ├── Matching Service
│   └── Booking Service
├── Infrastructure
│   ├── Database (PostgreSQL)
│   ├── File Storage
│   ├── AI Services
│   │   ├── Azure Document Intelligence
│   │   └── Claude API
│   └── Importers
└── Domain
    ├── Entities
    └── Business Rules (SKR04)
```

## 🚧 Roadmap

### Phase 3 (Geplant)
- Machine Learning für besseres Matching
- Lernende Buchungsvorschläge
- Multi-Mandanten-Fähigkeit

### Phase 4 (Geplant)
- Erweiterte Reports
- E-Bilanz Export
- API für Drittsysteme

## 🤝 Contributing

1. Fork das Repository
2. Feature Branch erstellen (`git checkout -b feature/AmazingFeature`)
3. Änderungen committen (`git commit -m 'Add AmazingFeature'`)
4. Branch pushen (`git push origin feature/AmazingFeature`)
5. Pull Request öffnen

## 📝 Lizenz

Dieses Projekt ist lizenziert unter der MIT License.

## 🙏 Danksagungen

- Azure Cognitive Services für Document Intelligence
- Anthropic für Claude AI
- FastAPI Framework
- Alpine.js für reactive UI