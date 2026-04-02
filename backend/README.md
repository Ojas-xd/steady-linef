# AI Queue Management — FastAPI Backend

## Quick Start

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Seed sample data
python -m app.seed

# Run the server
uvicorn app.main:app --reload --port 8000
```

API docs at: http://localhost:8000/docs

## Demo Credentials

| Role     | Email              | Password    |
|----------|--------------------|-------------|
| Admin    | admin@queue.ai     | admin123    |
| Staff    | staff@queue.ai     | staff123    |
| Customer | customer@queue.ai  | customer123 |

## Environment Variables

Create a `.env` file (optional):

```
DATABASE_URL=sqlite:///./queue.db
SECRET_KEY=your-secret-key
YOLO_MODEL_PATH=yolov8n.pt
```

## Endpoints

| Method | Path                          | Description              |
|--------|-------------------------------|--------------------------|
| POST   | /api/auth/login               | Login → JWT              |
| POST   | /api/auth/register            | Register new user        |
| POST   | /api/tokens/                  | Issue token (QR scan)    |
| GET    | /api/tokens/                  | List all tokens          |
| GET    | /api/tokens/{id}              | Get token details        |
| PATCH  | /api/tokens/{id}/serve        | Staff categorize & serve |
| PATCH  | /api/tokens/{id}/complete     | Mark completed           |
| GET    | /api/tokens/{id}/status       | Queue position & ETA     |
| GET    | /api/dashboard/stats          | Dashboard stats          |
| GET    | /api/dashboard/forecast       | Hourly forecast          |
| GET    | /api/display/now-serving      | TV display data          |
| GET    | /api/analytics/               | Analytics data           |
| GET    | /api/crowd/count              | Latest crowd count       |
| POST   | /api/crowd/analyze            | YOLO frame analysis      |
