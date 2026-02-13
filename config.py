from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/kei.db"
    api_token: str = "changeme"

    model_config = {"env_file": ".env", "env_prefix": "KEI_"}


settings = Settings()
