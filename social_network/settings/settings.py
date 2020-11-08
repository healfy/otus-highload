from social_network.settings.base import (
    BaseSettings,
    UvicornSettings,
    DatabaseSettings,
)

CONFIG_PATH = 'settings/settings.json'


class Settings(BaseSettings):
    DEBUG = True
    UVICORN = UvicornSettings()
    DATABASE = DatabaseSettings(PASSWORD='password', NAME='otus_highload')


settings = Settings.from_json(CONFIG_PATH)