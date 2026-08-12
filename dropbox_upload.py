#!/usr/bin/env python3
"""
dropbox_upload.py — Hall Collins CMA Generator
Silently uploads a generated CMA PDF to a shared Dropbox folder.

Credentials are read from Streamlit secrets (st.secrets) when running on
Streamlit Cloud, or from environment variables / a local .env file when
running locally.

Required secrets / env vars:
    DROPBOX_APP_KEY        — from the Dropbox App Console
    DROPBOX_APP_SECRET     — from the Dropbox App Console
    DROPBOX_REFRESH_TOKEN  — long-lived refresh token (see README for setup)
    DROPBOX_FOLDER         — destination folder path, e.g. /Hall Collins/CMAs
"""

import io


def _get_secret(key: str, default: str = "") -> str:
    """Try st.secrets first, then os.environ, then default."""
    try:
        import streamlit as st
        return st.secrets.get(key, "")
    except Exception:
        pass
    import os
    return os.environ.get(key, default)


def upload_cma_to_dropbox(pdf_bytes: bytes, filename: str) -> tuple[bool, str]:
    """
    Upload pdf_bytes to Dropbox as /DROPBOX_FOLDER/filename.

    Returns (success: bool, message: str).
    """
    app_key      = _get_secret("DROPBOX_APP_KEY")
    app_secret   = _get_secret("DROPBOX_APP_SECRET")
    refresh_token = _get_secret("DROPBOX_REFRESH_TOKEN")
    folder       = _get_secret("DROPBOX_FOLDER", "/Listings/0. CMAs/CMAs")

    if not all([app_key, app_secret, refresh_token]):
        return False, "Dropbox credentials not configured — skipping upload."

    try:
        import dropbox
        from dropbox.exceptions import ApiError, AuthError
        from dropbox.files import WriteMode

        dbx = dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=app_key,
            app_secret=app_secret,
        )

        # Ensure folder path is clean
        folder = folder.rstrip("/")
        dest_path = f"{folder}/{filename}"

        dbx.files_upload(
            pdf_bytes,
            dest_path,
            mode=WriteMode("overwrite"),
            autorename=False,
        )
        return True, f"✅ Saved to Dropbox: `{dest_path}`"

    except ImportError:
        return False, "dropbox package not installed."
    except AuthError as e:
        return False, f"Dropbox auth error: {e}"
    except ApiError as e:
        return False, f"Dropbox API error: {e}"
    except Exception as e:
        return False, f"Dropbox upload failed: {e}"
