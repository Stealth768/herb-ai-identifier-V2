import os
from pathlib import Path
from django.apps import AppConfig
from dotenv import load_dotenv
from google import genai



BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / '.env'

# THE VAULT
load_dotenv(dotenv_path=env_path)

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

# ASSIGN THE KEY
API_KEY = os.getenv("GEMINI_API_KEY")

# CLIENT
if API_KEY:
    print(f"[SUCCESS] API Key loaded from {env_path}")
    client = genai.Client(api_key=API_KEY)
else:
    print(f"[ERROR] Key still missing at {env_path}")
    client = None
