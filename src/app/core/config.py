from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/marketplace"
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ORDER_CREATE_LIMIT_MINUTES: int = 5
    ORDER_UPDATE_LIMIT_MINUTES: int = 5

    class Config:
        env_file = ".env"


settings = Settings()
