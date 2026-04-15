from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# --- LLM Provider ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))

# --- Database ---
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()
SQLITE_PATH = os.getenv("SQLITE_PATH", str(BASE_DIR / "db" / "demo.db"))
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "")
POSTGRES_USER = os.getenv("POSTGRES_USER", "")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

# --- Agent ---
MAX_AGENT_LOOPS = int(os.getenv("MAX_AGENT_LOOPS", "3"))
MAX_PREVIEW_ROWS = int(os.getenv("MAX_PREVIEW_ROWS", "200"))

# --- Paths ---
MEMORY_PATH = BASE_DIR / "memory"
LOG_PATH = BASE_DIR / "logs" / "agent_runs.jsonl"

# --- SQL Security ---
TABLE_ALLOWLIST = [
    "fact_signups",
    "fact_orders",
    "dim_country",
    "dim_device",
]

DANGEROUS_SQL_KEYWORDS = frozenset([
    "insert", "update", "delete", "drop", "create", "alter",
    "truncate", "merge", "copy", "call", "grant", "revoke",
])
