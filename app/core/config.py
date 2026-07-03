from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # App
    APP_NAME: str = "ArchiveVault"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # Networking — separately configurable from the UI's host/port.
    # BIND_HOST/API_PORT control where gunicorn/uvicorn listens.
    # Keep BIND_HOST=127.0.0.1 when nginx is the public entrypoint (recommended).
    # Set BIND_HOST=0.0.0.0 to expose the API directly without nginx
    # (e.g. split-server setup with no domain/TLS yet).
    BIND_HOST: str = "127.0.0.1"
    API_PORT: int = 8000

    # SAS speed for retrieval estimates
    SAS_READ_SPEED_MBPS: float = 500.0

    # Admin setup
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""
    ADMIN_FULL_NAME: str = "IT Manager"

    @property
    def origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
