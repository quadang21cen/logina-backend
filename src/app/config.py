from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Database Configuration
    POSTGRES_USER: str = Field(default="logina_user")
    POSTGRES_PASSWORD: str = Field(default="logina_secure_password")
    POSTGRES_DB: str = Field(default="logina_db")
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    DATABASE_URL: str = Field(default="postgresql+asyncpg://logina_user:logina_secure_password@localhost:5432/logina_db")

    MONGO_INITDB_ROOT_USERNAME: str = Field(default="root")
    MONGO_INITDB_ROOT_PASSWORD: str = Field(default="mongo_secure_password")
    MONGO_DB: str = Field(default="logina_mongo")
    MONGO_HOST: str = Field(default="localhost")
    MONGO_PORT: int = Field(default=27017)
    MONGO_URI: str = Field(default="mongodb://root:mongo_secure_password@localhost:27017/logina_mongo?authSource=admin")

    # Cache Configuration (Redis)
    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379)
    REDIS_URL: Optional[str] = Field(default=None)

    # Security / Authentication
    JWT_SECRET: str = Field(default="super_secret_logina_key_change_me_in_production")
    JWT_EXPIRATION_TIME: str = Field(default="3600s")

    # LLM / AI Integration Keys
    OPENAI_API_KEY: str = Field(default="your_openai_api_key_here")
    ANTHROPIC_API_KEY: str = Field(default="your_anthropic_api_key_here")
    GEMINI_API_KEY: str = Field(default="your_gemini_api_key_here")


    # Service Ports
    GATEWAY_PORT: int = Field(default=3000)

settings = Settings()
