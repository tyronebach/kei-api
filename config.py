from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/kei.db"
    api_token: str = "changeme"
    valid_scopes: list[str] = ["home", "salon", "woodwards", "synthhub", "household"]
    cors_origins: list[str] = []
    allow_insecure_default_token: bool = False

    model_config = {"env_file": ".env", "env_prefix": "KEI_"}


settings = Settings()
