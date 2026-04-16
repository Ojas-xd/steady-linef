# AI Queue Management System (AQMS)

This project has:
- `frontend` (Vite + React) in the project root
- `backend` (FastAPI + YOLO + Prophet) in `backend/`

The YOLO module in this codebase is exposed through:
- `GET /api/crowd/count`
- `POST /api/crowd/analyze` (upload an image file field named `file`)

## Prerequisites

- Node.js 18+ and npm
- Python 3.10+ and pip

## 1) Start Backend Server

From project root:

```bash
cd backend
python -m venv venv
```

Activate virtual environment:

- Windows (PowerShell):

```powershell
.\venv\Scripts\Activate.ps1
```

- macOS/Linux:

```bash
source venv/bin/activate
```

Install backend dependencies:

```bash
pip install -r requirements.txt
```

Optional: create `.env` inside `backend/`:

```env
DATABASE_URL=sqlite:///./queue.db
SECRET_KEY=change-me-in-production
YOLO_MODEL_PATH=yolov8n.pt
```

Seed demo data (optional):

```bash
python -m app.seed
```

Run backend:

```bash
uvicorn app.main:app --reload --port 8000
```

Backend docs:
- `http://localhost:8000/docs`

## 2) Start Frontend Server

Open a second terminal in project root:

```bash
npm install
npm run dev
```

Frontend default URL:
- `http://localhost:5173`

If needed, set API URL in frontend `.env` (project root):

```env
VITE_API_BASE_URL=http://localhost:8000
```

## 3) Quick YOLO Check

1. Confirm backend is running and open `http://localhost:8000/docs`.
2. Test `GET /api/crowd/count` (should return JSON count).
3. Test `POST /api/crowd/analyze` by uploading a queue/crowd image.
4. Open frontend camera/crowd page and verify count updates.

## Common YOLO Issues

- First YOLO request can be slow because model loads lazily.
- If model file path is wrong, check `YOLO_MODEL_PATH` in `backend/.env`.
- Ensure `ultralytics` and `opencv-python-headless` installed from `requirements.txt`.
- If frontend shows mock data, backend might be unreachable; check `VITE_API_BASE_URL`.

