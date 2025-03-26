import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    """Application settings"""
    
    # Base paths
    APP_DIR: str = str(Path(__file__).parent.parent.absolute())
    DATA_DIR: str = str(Path(APP_DIR) / "data")
    
    # Database
    DATABASE_PATH: str = str(Path(DATA_DIR) / "ocr.db")
    
    # Google Cloud
    GOOGLE_APPLICATION_CREDENTIALS: str = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    VERTEX_AI_PROJECT_ID: str = os.environ.get("VERTEX_AI_PROJECT_ID", "")
    VERTEX_AI_LOCATION: str = os.environ.get("VERTEX_AI_LOCATION", "us-central1")
    
    # Model settings
    GEMINI_MODEL: str = "gemini-1.5-flash-002"  # For OCR document extraction
    GEMINI_VISION_MODEL: str = "gemini-pro"  # For text spotting
    
    # For backward compatibility with old .env files
    DEBUG: str = "False"
    DB_PATH: str = "data/ocr.db"
    UPLOAD_DIR: str = "uploads"
    OUTPUT_DIR: str = "outputs"
    DEFAULT_MODEL: str = "gemini-1.5-flash-002"
    MAX_TOKENS: str = "2048"
    TEMPERATURE: str = "0.0"
    
    # Model config
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Allow extra fields
    )

_settings = None

def get_settings() -> Settings:
    """Get application settings"""
    global _settings
    if _settings is None:
        _settings = Settings()
        # Ensure data directory exists
        os.makedirs(_settings.DATA_DIR, exist_ok=True)
    return _settings 