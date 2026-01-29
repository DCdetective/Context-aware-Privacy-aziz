from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os
from pathlib import Path


class Settings(BaseSettings):
    """Application configuration settings."""
    
    # Groq API Configuration
    groq_api_key: str
    
    # Pinecone Configuration
    pinecone_api_key: str
    pinecone_environment: str
    pinecone_index_name: str = "medshield-semantic-store"
    
    # Ollama Configuration
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    
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
    
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


settings = Settings()
