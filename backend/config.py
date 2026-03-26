"""DataChat configuration — API keys and model names."""
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
GEMINI_PRO_MODEL  = os.environ.get("GEMINI_PRO_MODEL",  "gemini-3.1-pro-preview")
GEMINI_FLASH_MODEL = os.environ.get("GEMINI_FLASH_MODEL", "gemini-3.1-flash-lite-preview")

# How many rows to pass to the interpreter (keep context small)
MAX_ROWS_FOR_INTERPRETATION = 50
