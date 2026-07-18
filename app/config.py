from dotenv import load_dotenv
import os
from pathlib import Path



BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_ENDPOINT = os.getenv("OPENAI_API_ENDPOINT")
ANTHROPIC_API_ENDPOINT = os.getenv("ANTHROPIC_API_ENDPOINT")