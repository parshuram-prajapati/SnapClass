
import os
from pathlib import Path

import streamlit as st
from supabase import create_client, Client


def get_secret(key: str, default: str = "") -> str:
    """Read secrets from Streamlit, local TOML, or environment."""

    # Streamlit Cloud secrets
    try:
        value = st.secrets.get(key)
        if value:
            return str(value).strip()
    except Exception:
        pass

    # Local secrets.toml
    try:
        import tomllib

        secrets_path = (
            Path(__file__).resolve().parents[2]
            / ".streamlit"
            / "secrets.toml"
        )

        if secrets_path.exists():
            with open(secrets_path, "rb") as file:
                data = tomllib.load(file)

            value = data.get(key)
            if value:
                return str(value).strip()

    except Exception:
        pass

    # Environment variables
    return os.environ.get(key, default).strip()


SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_KEY = get_secret("SUPABASE_KEY")

SUPABASE_SERVICE_ROLE_KEY = get_secret(
    "SUPABASE_SERVICE_ROLE_KEY"
)


# Validate normal Supabase configuration
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL or SUPABASE_KEY is missing. "
        "Check your Streamlit secrets configuration."
    )


# Normal application client
supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# Trusted server-side admin client
supabase_admin: Client | None = None

if SUPABASE_SERVICE_ROLE_KEY:
    supabase_admin = create_client(
        SUPABASE_URL,
        SUPABASE_SERVICE_ROLE_KEY
    )
else:
    import logging

    logging.warning(
        "SUPABASE_SERVICE_ROLE_KEY is missing. "
        "Admin operations and password reset will be unavailable."
    )
