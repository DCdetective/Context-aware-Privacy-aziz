# MedShield Deployment Guide

## Prerequisites

### System Requirements
- **OS:** Windows 10/11, macOS 10.15+, or Linux (Ubuntu 20.04+)
- **Python:** 3.12.2 or higher
- **RAM:** Minimum 8GB (16GB recommended for Ollama)
- **Storage:** 10GB free space
- **Network:** Internet connection for cloud APIs

### Required Accounts
1. **Groq Account:** Free tier (https://console.groq.com)
2. **Pinecone Account:** Free tier (https://www.pinecone.io)
3. **Ollama:** Installed locally (https://ollama.ai)

## Step-by-Step Deployment

### 1. Install Ollama

**macOS/Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
Download and install from https://ollama.com/download

**Verify Installation:**
```bash
ollama --version
```

**Pull Llama 3.1 Model:**
```bash
ollama pull llama3.1
```

### 2. Clone and Setup Project

```bash
# Clone repository (or extract from zip)
cd medshield

# Create virtual environment
python3.12 -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 3. Configure Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit .env file
nano .env  # or use your preferred editor
```

**Required Configuration:**
```env
# Groq API (get from https://console.groq.com)
GROQ_API_KEY=your_groq_api_key_here

# Pinecone API (get from https://app.pinecone.io)
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_ENVIRONMENT=us-east-1-aws
PINECONE_INDEX_NAME=medshield-semantic-store

# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1

# Database
SQLITE_DB_PATH=./backend/database/identity_vault.db

# Server
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# Testing (set to false for production)
TESTING_MODE=false

# Logging
LOG_LEVEL=INFO
```

### 4. Initialize Database

```bash
cd backend
python -c "from database.identity_vault import identity_vault; print('Database initialized')"
```

### 5. Run Tests

```bash
# Run all tests
python run_tests.py

# Or run specific test suites
pytest tests/test_identity_vault.py -v
pytest tests/test_privacy_compliance.py -v
```

### 6. Start the Application

```bash
# From backend directory
python main.py
```

**Expected Output:**
```
============================================================
🏥 MedShield - Privacy-Preserving Medical Assistant
============================================================
Initializing Local Identity Vault...
Database path: ./backend/database/identity_vault.db
Identity Vault initialized successfully
Initializing Semantic Anchor Store...
Semantic Store: 0 anchors stored
Initializing Multi-Agent System...
  - Gatekeeper Agent (Ollama) ✓
  - Coordinator Agent (Groq) ✓
  - Worker Agent (Groq) ✓
============================================================
🚀 System Ready
============================================================
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 7. Access the Application

Open your web browser and navigate to:
```
http://localhost:8000
```

## Verification Checklist

- [ ] Ollama installed and llama3.1 model pulled
- [ ] Python 3.12.2 installed
- [ ] Virtual environment activated
- [ ] Dependencies installed
- [ ] .env file configured with API keys
- [ ] Database initialized
- [ ] All tests passing
- [ ] Server starts without errors
- [ ] Frontend accessible in browser
- [ ] Health endpoint returns 200: `curl http://localhost:8000/health`

## Troubleshooting

### Ollama Connection Issues

**Problem:** "Error calling Ollama: Connection refused"

**Solution:**
```bash
# Check Ollama is running
ollama list

# If not running, start it
ollama serve

# Verify connection
curl http://localhost:11434/api/tags
```

### Groq API Errors

**Problem:** "Error calling Groq API: Invalid API key"

**Solution:**
1. Verify API key in .env file
2. Check key at https://console.groq.com
3. Ensure no extra spaces in API key
4. Restart server after updating .env

### Pinecone Connection Issues

**Problem:** "Failed to initialize Pinecone"

**Solution:**
1. Verify Pinecone API key and environment
2. Check index name matches configuration
3. Ensure free tier hasn't expired
4. Use mock store for testing: `TESTING_MODE=true`

### Port Already in Use

**Problem:** "Address already in use: 8000"

**Solution:**
```bash
# Find process using port 8000
# On Linux/Mac:
lsof -i :8000
# On Windows:
netstat -ano | findstr :8000

# Kill the process or use different port
# Edit .env: BACKEND_PORT=8001
```

### Module Import Errors

**Problem:** "ModuleNotFoundError: No module named 'fastapi'"

**Solution:**
```bash
# Ensure virtual environment is activated
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Reinstall dependencies
pip install -r backend/requirements.txt
```

## Production Deployment (Future)

### Docker Deployment

```dockerfile
# Dockerfile (future enhancement)
FROM python:3.12-slim

WORKDIR /app
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY requirements.txt /app/

RUN pip install -r requirements.txt

EXPOSE 8000
CMD ["python", "backend/main.py"]
```

### Environment-Specific Configurations

- **Development:** `TESTING_MODE=true`, `LOG_LEVEL=DEBUG`
- **Staging:** `TESTING_MODE=false`, `LOG_LEVEL=INFO`
- **Production:** Add authentication, HTTPS, monitoring

## Maintenance

### Regular Tasks

1. **Database Backup:**
```bash
cp backend/database/identity_vault.db backend/database/identity_vault_backup_$(date +%Y%m%d).db
```

2. **Log Rotation:**
```bash
# Implement log rotation for production
```

3. **Update Dependencies:**
```bash
pip list --outdated
pip install --upgrade <package_name>
```

### Monitoring

**Health Check Endpoint:**
```bash
curl http://localhost:8000/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "components": {
    "identity_vault": "operational",
    "semantic_store": "operational",
    "gatekeeper_agent": "operational",
    "coordinator_agent": "operational",
    "worker_agent": "operational"
  }
}
```

## Support

For issues during deployment:
1. Check logs in console output
2. Verify all prerequisites installed
3. Review troubleshooting section
4. Check test results: `python run_tests.py`
