# src/core/config.py

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://user:pass@localhost/jahresabschluss"

    # Application
    app_name: str = "Jahresabschluss-System"
    debug: bool = False

    # File Storage - use project-relative path
    @property
    def upload_path(self) -> str:
        """Always return a path within the project directory"""
        project_root = Path(__file__).parent.parent.parent
        return str(project_root / 'uploads')

    max_upload_size: int = 10 * 1024 * 1024  # 10MB

    # Azure AI Services
    azure_form_recognizer_endpoint: str = ""
    azure_form_recognizer_key: str = ""
    azure_use_prebuilt_model: bool = True

    # Claude API
    anthropic_api_key: str = ""
    claude_model: str = "claude-3-sonnet-20240229"
    claude_max_tokens: int = 1024

    # AI Processing
    ai_confidence_threshold: float = 0.8
    ai_enable_caching: bool = True

    class Config:
        env_file = ".env"


settings = Settings()