from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Robot Data Pipeline Backend"
    APP_VERSION: str = "1.0.0"
    DATABASE_URL: str = "sqlite:///./robot_data.db"
    API_V1_PREFIX: str = "/api/v1"

    class Config:
        env_file = ".env"


settings = Settings()
