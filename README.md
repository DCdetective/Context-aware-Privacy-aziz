# 🏥 MedShield v2 - Privacy-Preserving Medical Chatbot

A privacy-first multi-agent medical chatbot system designed for hospital receptionist tasks.

## 🔒 Privacy Architecture

**Core Principle**: NO Personally Identifiable Information (PII) ever leaves the local environment.

### Privacy Flow:
1. **User Input** → Contains PII (names, ages, etc.)
2. **Local Gatekeeper (Ollama)** → Detects & removes PII, assigns UUIDs
3. **Cloud Agents (Groq)** → Process ONLY pseudonymized UUIDs + metadata
4. **Local Re-identification** → Restore real identity for final output

### Vector Databases:
- **Vector DB 1 (SQLite)**: Stores PII locally (NEVER exposed to cloud)
- **Vector DB 2 (Pinecone)**: Stores UUID-linked metadata + synthetic hospital data

## 🎯 Features

- ✅ Appointment Booking
- ✅ Follow-up Scheduling
- ✅ Medical Summary Generation
- ✅ Conversational ChatGPT-style Interface
- ✅ Privacy Transformation Visualization
- ✅ RAG-based Synthetic Knowledge

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Ollama installed locally
- Groq API key
- Pinecone API key

### Installation

1. Clone the repository
2. Copy `.env.example` to `.env` and fill in your API keys
3. Install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

4. Run the application:
```bash
python main.py
```

5. Open browser: http://localhost:8000

## 📁 Project Structure

See `docs/ARCHITECTURE.md` for detailed architecture documentation.

## 🧪 Testing

```bash
cd backend
pytest
```

## 📚 Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Privacy Design](docs/PRIVACY_DESIGN.md)
- [API Documentation](docs/API_DOCUMENTATION.md)
- [Testing Guide](docs/TESTING_GUIDE.md)

## 🎓 Academic Project

This is a final year project demonstrating privacy-preserving AI in healthcare.
