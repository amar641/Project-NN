import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    MONGODB_DATABASE: str = os.getenv("MONGODB_DATABASE", "voting_db")
    
    APP_NAME: str = "Reverse Voting System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False") == "True"
    ROUND_DURATION_SECONDS: int = int(os.getenv("ROUND_DURATION", "60"))
    
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/app.log")
    AZURE_ENABLED: bool = os.getenv("AZURE_ENABLED", "False") == "True"

settings = Settings()