# MedShield Deployment Guide

## Prerequisites

- **Python 3.9+**
- **Pinecone account** (for vector storage)
- **Groq API key** (for cloud LLM)
- **Ollama** (optional, for local LLM PII detection)
- **SQLite** (included with Python)

---

## Environment Variables

Create a `.env` file in the project root:

```env
# Required
GROQ_API_KEY=your-groq-api-key
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_ENVIRONMENT=us-east-1

# Optional
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1
OPENAI_API_KEY=your-openai-api-key

# Server
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
LOG_LEVEL=INFO

# Security
SECRET_KEY=change-this-in-production

# Testing
TESTING_MODE=false
```

---

## Local Development

### Quick Start

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt

# 2. Run tests
python -m pytest tests/ -v

# 3. Start server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 4. Open browser
# Navigate to http://localhost:8000
```

### With Ollama (Local LLM)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull model
ollama pull llama3.1

# Start Ollama (runs on port 11434)
ollama serve

# Start MedShield backend
cd backend
uvicorn main:app --reload
```

---

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY synthetic_data/ ./synthetic_data/
COPY .env .

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  medshield:
    build: .
    ports:
      - "8000:8000"
    environment:
      - GROQ_API_KEY=${GROQ_API_KEY}
      - PINECONE_API_KEY=${PINECONE_API_KEY}
      - PINECONE_ENVIRONMENT=${PINECONE_ENVIRONMENT}
    volumes:
      - ./data:/app/backend/database
    restart: unless-stopped
```

### Build and Run

```bash
docker build -t medshield .
docker run -p 8000:8000 --env-file .env medshield
```

---

## Production Considerations

### Security

- **Change SECRET_KEY** to a strong random value
- **Use HTTPS** in production (reverse proxy with nginx)
- **Rate limiting**: Configure nginx or use FastAPI middleware
- **CORS**: Restrict `allow_origins` in `main.py` to your domain

### Database Backups

```bash
# Backup identity vault (contains PII - handle with care!)
cp backend/database/identity_vault.db backup/identity_vault_$(date +%Y%m%d).db

# Backup sessions
cp backend/database/sessions.db backup/sessions_$(date +%Y%m%d).db
```

### Monitoring

- **Health check**: `GET /health`
- **Privacy report**: `GET /api/chat/privacy-report`
- **Application logs**: Configure `LOG_LEVEL=INFO` or `DEBUG`

### Privacy Audit Logs

```bash
# Check for any privacy violations
python -c "
from database.identity_vault import identity_vault
report = identity_vault.verify_privacy_compliance()
print(f'Privacy compliant: {report[\"privacy_compliant\"]}')
print(f'Cloud exposed: {report[\"cloud_exposed_count\"]}')
print(f'Total operations: {report[\"total_operations\"]}')
"
```

---

## Troubleshooting

### Common Issues

#### Groq API Errors
```
Error: Invalid API key
```
**Solution**: Verify `GROQ_API_KEY` in `.env` file.

#### Ollama Connection Failed
```
Warning: local LLM unavailable, using regex fallback
```
**Solution**: This is non-critical. The system falls back to regex-based PII detection. To fix, ensure Ollama is running: `ollama serve`

#### Pinecone Connection Failed
```
Warning: Failed to initialize Pinecone stores, using mocks
```
**Solution**: Check `PINECONE_API_KEY` and `PINECONE_ENVIRONMENT`. In testing mode, mock stores are used automatically.

#### Database Locked
```
Error: database is locked
```
**Solution**: Ensure only one instance is running, or use WAL mode for SQLite.

---

## Testing in Production

```bash
# Run health check
curl http://localhost:8000/health

# Test chat endpoint
curl -X POST http://localhost:8000/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, what can you help with?"}'

# Check privacy compliance
curl http://localhost:8000/api/chat/privacy-report
```
