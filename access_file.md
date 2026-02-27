# MedShield Access & Run Instructions (Windows)

Yes — the project already has a runnable entry point and frontend pages.

## What to run
- Backend entry file: `backend/main.py`
- Frontend pages are served by the backend itself (no separate frontend server needed).

## 1) Open terminal at project root
Path:
`C:\Users\riswa\Desktop\Context-aware-Privacy-aziz`

## 2) Activate virtual environment
If you use the existing one in this project:
```powershell
.\8thsem\Scripts\Activate.ps1
```

## 3) Install dependencies (if not already installed)
```powershell
pip install -r backend/requirements.txt
```

## 4) Check `.env` file
Make sure root `.env` has at least:
```env
GROQ_API_KEY=...
PINECONE_API_KEY=...
TESTING_MODE=false
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
```

If you want to run without Pinecone in fallback/testing style, set:
```env
TESTING_MODE=true
```

## 5) Start backend server
```powershell
cd backend
python main.py
```

You should see Uvicorn running on port `8000`.

## 6) Open in browser
- Main chat UI: `http://localhost:8000/`
- Appointment page: `http://localhost:8000/appointment`
- Follow-up page: `http://localhost:8000/followup`
- Summary page: `http://localhost:8000/summary`
- Health check: `http://localhost:8000/health`

## 7) Sample input to test end-to-end flow
In chat (`/`), try:

```text
My name is John Doe, I am 45 years old male. I have chest pain for 2 days and want to book an appointment.
```

Expected behavior:
- UI shows response from the multi-agent pipeline.
- Privacy panel updates with PII transformation details.
- Backend processes through gatekeeper → coordinator → context/execution flow.

## 8) Stop server
Press `Ctrl + C` in the terminal running `python main.py`.

## Common issues
- Port busy: change `BACKEND_PORT` in `.env`.
- API key errors: verify `GROQ_API_KEY` / `PINECONE_API_KEY`.
- Ollama issues (if used): ensure Ollama is installed/running and model is available.
