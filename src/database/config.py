
import os
from pathlib import Path
import streamlit as st
from supabase import create_client, Client


def get_secret(key: str, default: str = "") -> str:
    """Retrieve secrets from Streamlit, local TOML, or environment."""

    # 1. Streamlit secrets
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass

    # 2. Local secrets.toml
    try:
        import tomllib

        local_secrets = (
            Path(__file__).resolve().parent.parent.parent
            / ".streamlit"
            / "secrets.toml"
        )

        if local_secrets.exists():
            with open(local_secrets, "rb") as f:
                data = tomllib.load(f)

            if key in data:
                return str(data[key])

    except Exception:
        pass

    # 3. Environment variables
    return os.environ.get(key, default)


SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_KEY = get_secret("SUPABASE_KEY")

SUPABASE_SERVICE_ROLE_KEY = get_secret(
    "SUPABASE_SERVICE_ROLE_KEY"
)

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase URL or API key is missing.")

# Existing client: preserve existing application functionality.
supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# Trusted server-side client: biometric database operations only.
supabase_admin: Client | None = None

if SUPABASE_SERVICE_ROLE_KEY:
    supabase_admin = create_client(
        SUPABASE_URL,
        SUPABASE_SERVICE_ROLE_KEY
    )
