# AI Incident & Root-Cause Analyzer

A developer-focused log analysis tool that parses system logs, flags anomalous error spikes, groups duplicate error traces, and traces propagation paths to identify the likely root cause of backend incidents. 

The frontend is designed around a dark, minimal developer interface (Japanese Cyber Minimalism) using high-density typography, Space Grotesk/Inter, and crimson-red accent indicators.

---

## Architecture Flow

```
   [ Upload Logs ] (.log, .txt, .json, .csv)
          │
          ▼
   [ Log Ingestion ] ──────────► [ Normalize Logs ]
                                        │
                                        ▼
                               [ Write to Postgres ]
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          ▼                             ▼                             ▼
   [ Anomaly Detection ]       [ Error Grouping ]            [ Root Cause Engine ]
   - Z-score spikes            - TF-IDF Vectorizer           - Chronological order
   - Isolation Forest          - Cosine Similarity           - Upstream/infra weights
          │                             │                             │
          └─────────────────────────────┼─────────────────────────────┘
                                        ▼
                               [ Create Incident ]
                                        │
                                        ▼
                               [ Render Dashboard ]
```

---

## Tech Stack

* **Frontend**: HTML5, CSS3 (Vanilla), Javascript (ES6), Chart.js
* **Backend**: FastAPI, Uvicorn, Pandas, Scikit-learn (Isolation Forest), Pydantic
* **Database**: PostgreSQL, SQLAlchemy, Alembic (migrations)
* **Testing**: pytest, httpx (TestClient)

---

## Quick Start

### 1. Database Setup
The app requires PostgreSQL. If you are on macOS and use Homebrew, run:

```bash
# Start Postgres
brew services start postgresql@18

# Create application database
createdb incident_analyzer
```

### 2. Environment Setup
Clone the repository and set up a Python virtual environment:

```bash
# Create and activate environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

Create a `.env` file in the root directory (you can copy the example template):

```bash
cp .env.example .env
```

Default settings in `.env`:
```env
DATABASE_URL=postgresql://localhost/incident_analyzer
HOST=127.0.0.1
PORT=8000
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
```

### 3. Migrations and Seeding
Run Alembic migrations to create the database schemas, and populate seed data to view the dashboard without immediately uploading logs:

```bash
# Run schema migrations
alembic upgrade head

# Seed database with mock incidents and sample logs
python3 backend/services/seed.py
```

### 4. Running the App
Start the dev server:

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and navigate to `http://127.0.0.1:8000` to access the dashboard.

---

## How It Works

### Log Parsing & Ingestion
The parser (`backend/services/parser.py`) normalizes logs into a structured schema containing timestamps, services, levels, status codes, and request identifiers. It matches JSON formats, standard brackets (`[2026-08-19 10:00:00] [service] [LEVEL]`), key-value syslog-like messages, and comma-separated variables.

### Anomaly Detection
Anomalies are flagged using a hybrid approach (`backend/services/anomaly_detector.py`):
1. **Z-Score Spike Detection**: Measures the error count deviations within sliding time buckets. Spikes exceeding a configurable threshold are flagged.
2. **Isolation Forest**: Multi-dimensional outlier detection that groups anomalous features (logs count, error ratios) to isolate complex traffic deviations.

### Error Grouping
Similar error messages are clustered using character/word **TF-IDF vectorization** and **Cosine Similarity** (`backend/services/similarity.py`). Variable fields (timestamps, UUIDs, IDs, IPs) are stripped to avoid cluster fragmentation, allowing the UI to group duplicate failures together.

### Root-Cause Scoring
The scoring engine (`backend/services/root_cause.py`) evaluates the propagation of failures using the following rules:
* **Chronological Priority**: Services experiencing the first anomalous spikes in a time-window receive the highest root-cause score.
* **Service Role Priority**: Upstream and infrastructure layers (like databases, message brokers, authentication services) receive higher base weights than client-facing APIs.
* **Propagation Weight**: Services whose failures precede anomalies in multiple downstream services are scored higher.

The output determines a "Likely Root Cause", listing an evidence trail and a calculated confidence percentage.

---

## API Reference

* `GET /health` - Checks application and PostgreSQL availability.
* `GET /api/analytics` - Aggregated stats for the dashboard (system health score, error timeline, severity distributions).
* `GET /api/incidents` - Query and search incidents list (supports filtering by severity, status, and text search).
* `GET /api/incidents/{id}` - Details of a single incident, returns its chronological timeline and evidence.
* `PATCH /api/incidents/{id}/status` - Update incident state (`OPEN`, `INVESTIGATING`, `RESOLVED`, `CLOSED`).
* `GET /api/services` - List monitored services and their current metrics.
* `POST /api/logs/upload` - Ingest raw log files and run the analysis pipeline.

---

## Tests
Verify the installation by running the test suite:

```bash
PYTHONPATH=. pytest tests/
```

---

## Production Deployment
To run in a production environment:

1. Update the `CORS_ORIGINS` in `.env` to match your client domains.
2. Restrict database access and use strong credentials in `DATABASE_URL`.
3. Spawn a WSGI server proxying Uvicorn workers:
   ```bash
   gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
   ```
4. Set up an SSL reverse proxy (e.g. Nginx or Caddy) in front of the application.
