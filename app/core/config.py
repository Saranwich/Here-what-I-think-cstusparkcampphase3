from dotenv import load_dotenv
import os
from pathlib import Path



# app/core/config.py -> app/core -> app -> project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_ENDPOINT = os.getenv("OPENAI_API_ENDPOINT")
ANTHROPIC_API_ENDPOINT = os.getenv("ANTHROPIC_API_ENDPOINT")