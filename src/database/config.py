import os
from pathlib import Path
import streamlit as st
from supabase import create_client, Client

def get_secret(key: str, default: str = "") -> str:
    """Safely retrieves secret from st.secrets, local toml file, or environment variables."""
    # 1. Try streamlit secrets
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass

    # 2. Try local .streamlit/secrets.toml directly
    try:
        import tomllib
        local_secrets = Path(__file__).resolve().parent.parent.parent / ".streamlit" / "secrets.toml"
        if local_secrets.exists():
            with open(local_secrets, "rb") as f:
                data = tomllib.load(f)
                if key in data:
                    return str(data[key])
    except Exception:
        pass

    # 3. Try environment variables
    return os.environ.get(key, default)

SUPABASE_URL = get_secret("SUPABASE_URL", "")
SUPABASE_KEY = get_secret("SUPABASE_KEY", "")

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)
