from pydantic_settings import BaseSettings
from pathlib import Path
import os


class Settings(BaseSettings):
    # Application settings
    SECRET_KEY: str = "your-secret-key-here"  # Default value for development
    APP_NAME: str = "BCR Analysis"
    DEBUG: bool = False

    # Database settings
    DATABASE: str = str(Path("instance/bcr.db"))
    db_username: str = ""
    db_password: str = ""

    # File upload settings
    UPLOAD_FOLDER: str = str(Path("instance/uploads"))
    MAX_UPLOAD_SIZE: int = 100 * 1024 * 1024  # 100MB

    # Dandelion settings
    GERMLINE_PATH: str = ""  # Will be set from environment
    IGDATA_PATH: str = ""  # Will be set from environment
    BLASTDB_PATH: str = ""  # Will be set from environment

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"  # Allow extra fields from environment

    def setup_environment(self):
        """Setup environment variables for dandelion processing"""
        # Create necessary directories
        Path(self.UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
        Path(self.DATABASE).parent.mkdir(parents=True, exist_ok=True)

        # Set dandelion environment variables
        os.environ["GERMLINE"] = self.GERMLINE_PATH
        os.environ["IGDATA"] = self.IGDATA_PATH
        os.environ["BLASTDB"] = self.BLASTDB_PATH


# Create global settings instance
settings = Settings()
