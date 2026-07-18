"""
src/foot_predictor/config.py

Charge la configuration depuis .env.{APP_ENV} (dev / test / prod)
et expose l'URL de connexion PostgreSQL correspondante.
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    # "disable" en local (Docker), "require" pour Neon en prod
    postgres_sslmode: str = "disable"

    model_config = SettingsConfigDict(
        env_file=f".env.{os.getenv('APP_ENV', 'dev')}",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            f"?sslmode={self.postgres_sslmode}"
        )


@lru_cache
def get_settings() -> Settings:
    """Instance mise en cache : APP_ENV doit être fixé avant le premier appel."""
    return Settings()
