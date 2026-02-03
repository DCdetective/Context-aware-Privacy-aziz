from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """Application configuration settings."""
    
    # Groq API Configuration
    groq_api_key: str
    
    # Pinecone Configuration
    pinecone_api_key: str
    pinecone_environment: str
    pinecone_index_metadata: str = "medshield-metadata"
    pinecone_index_synthetic: str = "medshield-synthetic"
    
    # Ollama Configuration
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    
    # OpenAI Configuration (for embeddings)
    openai_api_key: Optional[str] = None
    
    # Database Configuration
    sqlite_db_path: str = "database/identity_vault.db"
    
    # Server Configuration
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_url: str = "http://localhost:8000"
    
    # Logging
    log_level: str = "INFO"
    
    # Testing mode
    testing_mode: bool = False
    
    # Security
    secret_key: str = "change-this-in-production"
    
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


settings = Settings()
