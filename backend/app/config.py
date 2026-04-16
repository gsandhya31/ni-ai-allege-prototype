"""Central configuration: env vars + mutable admin toggles persisted to disk."""
import json
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
SAMPLES_DIR = BACKEND_DIR / "samples"
DB_DIR = BACKEND_DIR / "app" / "db"

DB_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BACKEND_DIR / ".env")

# ----- Static (env-driven) config -----
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:8080")

# ----- Paths -----
INBOX_DIR = DATA_DIR / "inbox"
SENT_DIR = DATA_DIR / "sent"
REFERENCE_DIR = DATA_DIR / "reference"
AUDIT_DB = DB_DIR / "audit.db"
CASES_DB = DB_DIR / "cases.db"
SETTINGS_FILE = DB_DIR / "settings.json"

INBOX_DIR.mkdir(parents=True, exist_ok=True)
SENT_DIR.mkdir(parents=True, exist_ok=True)
REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

# ----- Broker domain list -----
BROKER_DOMAINS = {
    "tpicap.com",
    "tullettprebon.com",
    "icap.com",
    "bgcpartners.com",
    "tradition.com",
    "marexspectron.com",
    "gfigroup.com",
}

# Domain -> canonical counterparty name. Used for sender-domain inference.
DOMAIN_TO_COUNTERPARTY = {
    "gs.com": "Goldman Sachs International",
    "goldmansachs.com": "Goldman Sachs International",
    "jpmorgan.com": "JPMorgan Chase",
    "jpmchase.com": "JPMorgan Chase",
    "db.com": "Deutsche Bank AG",
    "deutsche-bank.com": "Deutsche Bank AG",
    "hsbc.com": "HSBC Bank plc",
    "citi.com": "Citigroup Global Markets",
    "citigroup.com": "Citigroup Global Markets",
    "barclays.com": "Barclays Capital",
    "bnpparibas.com": "BNP Paribas",
    "ubs.com": "UBS AG",
    "morganstanley.com": "Morgan Stanley",
    "credit-suisse.com": "Credit Suisse",
    "socgen.com": "Societe Generale",
    "rbccm.com": "RBC Capital Markets",
}

# ----- Mutable settings (persisted to settings.json, editable from Admin UI) -----
DEFAULT_SETTINGS: Dict[str, Any] = {
    "use_llm": True,
    "extended_thinking": False,
    "assigned_analyst_filter": "Gopi",
}


def load_settings() -> Dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
            # Merge with defaults so new keys appear automatically
            merged = {**DEFAULT_SETTINGS, **data}
            return merged
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> None:
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


# Initialise on import
SETTINGS: Dict[str, Any] = load_settings()


def update_setting(key: str, value: Any) -> Dict[str, Any]:
    SETTINGS[key] = value
    save_settings(SETTINGS)
    return SETTINGS
