import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = os.getenv("ADMIN_ID", "")

# Groq API
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama-3.3-70b-versatile")

# Database (Supabase)
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Hugging Face (Image Gen)
HF_TOKEN = os.getenv("HF_TOKEN", "")

# Tavily (Web Search)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
