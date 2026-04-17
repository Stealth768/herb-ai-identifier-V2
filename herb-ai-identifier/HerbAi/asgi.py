import os
from dotenv import load_dotenv
from django.core.asgi import get_asgi_application

load_dotenv()
GEMINI_API_KEY = os.getenv('AIzaSyA-GsqzpZvEQx8DVg9r6igecAy-iaPss5I')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'HerbAi.settings')

application = get_asgi_application()
