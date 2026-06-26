from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    LLM_API_KEY: str
    LLM_BASE_URL: str
    LLM_MODEL: str
    LLM_STREAMING: bool = False
    SERVER_PORT: int = 8000
    DATA_DIR: str = "./data"
    DATABASE_URL: str = "sqlite:///./quickapp.db"
    GENERATION_MAX_CONCURRENT: int = 10

    class Config:
        env_file = ".env"


settings = Settings()
