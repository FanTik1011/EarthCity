import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev_secret_key_change_me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///earthcity.sqlite3"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
