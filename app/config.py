from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://txnuser:txnpass@postgres:5432/txndb"
    REDIS_URL: str = "redis://redis:6379/0"
    GEMINI_API_KEY: str = ""
    UPLOAD_DIR: str = "/app/uploads"

    class Config:
        env_file = ".env"


settings = Settings()
