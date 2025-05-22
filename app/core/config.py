from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    # Application Settings
    app_env: str = "development"
    debug: bool = True
    secret_key: str
    
    # Authentication
    login_username: str 
    login_password: str
    
    # Server Settings
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Database Settings
    database_url: str = "sqlite:///instance/bcr.db"
    db_username: str 
    db_password: str
    
    # CORS Settings
    allowed_origins: list[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]
    
    # File Storage
    upload_dir: str = "instance/uploads"
    max_upload_size: int = 10485760  # 10MB in bytes
    
    # BLAST/IGBLAST Settings

    germlines_path: str = "app/database/germlines"
    igdata_path: str = "app/database/igblast"
    blastdb_path: str = "app/database/blast"
    
    # Logging
    log_level: str = "INFO"
    log_file: str = "instance/app.log"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"  # Allow extra fields from environment variables

@lru_cache()
def get_settings() -> Settings:
    return Settings()
