# secrets_helper.py

from typing import Optional, Dict
import os

# Streamlit (optional at import time)
try:
    import streamlit as st
    _HAS_STREAMLIT = True
except Exception:
    _HAS_STREAMLIT = False

# TOML loader: py311+ has tomllib; else fall back to 'toml'
try:
    import tomllib as _toml  # Python 3.11+
except Exception:
    try:
        import toml as _toml  # pip install toml
    except Exception:
        _toml = None

import streamlit_authenticator as stauth

def _load_secrets_dict(secrets_path: Optional[str] = None) -> Dict:
    """
    Returns a dict of secrets.
    Priority:
      1) If secrets_path is provided -> load that file.
      2) Else if running under Streamlit and st.secrets is non-empty -> use st.secrets.
      3) Else -> load default .streamlit/secrets.toml file.
    """
    # 1) Explicit path wins
    if secrets_path:
        path = secrets_path
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"Could not find secrets file at '{path}'. "
                "Provide a valid path or ensure the file exists."
            )
        if _toml is None:
            raise ModuleNotFoundError(
                "No TOML parser available. On Python < 3.11, install the 'toml' package: pip install toml"
            )
        with open(path, "rb") as f:
            data = _toml.load(f)
        if not isinstance(data, dict) or not data:
            raise ValueError(f"Secrets file '{path}' is empty or invalid TOML.")
        return data

    # 2) Use st.secrets if available AND non-empty
    if _HAS_STREAMLIT:
        try:
            sec = dict(st.secrets)  # type: ignore
            if sec:
                return sec
        except Exception:
            pass

    # 3) Fallback to default file
    path = os.environ.get("SECRETS_TOML") or os.path.join(".streamlit", "secrets.toml")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Could not find secrets file at '{path}'. "
            "Either run with Streamlit (which loads st.secrets) or provide a valid path."
        )
    if _toml is None:
        raise ModuleNotFoundError(
            "No TOML parser available. On Python < 3.11, install the 'toml' package: pip install toml"
        )
    with open(path, "rb") as f:
        data = _toml.load(f)
    if not isinstance(data, dict) or not data:
        raise ValueError(f"Secrets file '{path}' is empty or invalid TOML.")
    return data


def _build_roles_map(cfg: Dict) -> Dict[str, str]:
    """
    Supports either:
      [roles_map]        -> username = "role"
      [roles]            -> role = ["user1", "user2"]
    Returns: {username: role}
    """
    # Preferred explicit mapping
    roles_map = cfg.get("roles_map")
    if isinstance(roles_map, dict) and roles_map:
        return {str(u): str(r) for u, r in roles_map.items()}

    # Convert from group -> [users] format
    roles = cfg.get("roles", {})
    out: Dict[str, str] = {}
    if isinstance(roles, dict):
        for role, users in roles.items():
            if isinstance(users, (list, tuple)):
                for u in users:
                    u = str(u)
                    # first role wins (avoid surprise overwrites)
                    out.setdefault(u, str(role))
    return out

def get_user_roles(username: str, roles_map: Dict[str, str]):
    """
    Return a set of roles for the given username.
    Current schema supports a single role per user, so we return {role} or empty set.
    Matching is case-insensitive on username.
    """
    if username is None:
        return set()
    # try exact, then case-insensitive
    role = roles_map.get(username)
    if role is None:
        # build a lowercase lookup on the fly
        lower_map = {str(u).lower(): r for u, r in roles_map.items()}
        role = lower_map.get(str(username).lower())
    return {role} if role else set()



def init_secrets_and_auth(secrets_path: Optional[str] = None, debug: bool = False):
    """
    Single source of truth:
      - Loads secrets (st.secrets or TOML file)
      - Normalizes & validates cookie key
      - Builds streamlit-authenticator
      - Returns: (authenticator, roles_map)
    """
    cfg = _load_secrets_dict(secrets_path)

    # --- required sections ---
    users = cfg.get("users", {})
    if not users or not isinstance(users, dict):
        raise ValueError("No users found in secrets. Add a [users] section with at least one user.")

    cookie = cfg.get("cookie", {})
    if not cookie or not isinstance(cookie, dict):
        raise ValueError("Missing [cookie] section in secrets.")

    roles_map = _build_roles_map(cfg)

    # --- normalize + validate cookie key once ---
    raw_key = str(cookie.get("key", ""))
    normalized_key = "".join(raw_key.split())  # strip spaces/newlines/zero-width chars

    if debug and _HAS_STREAMLIT:
        st.write({
            "secrets_keys": sorted(list(cfg.keys())),
            "cookie_name": cookie.get("name"),
            "cookie_key_len": len(normalized_key),
        })

    if len(normalized_key) < 32:
        raise ValueError("Cookie key too short/invalid. Provide a random string ≥ 32 chars (64 hex recommended).")

    # --- build credentials (must exist before Authenticate) ---
    creds = {"usernames": {}}
    for uname, u in users.items():
        if not isinstance(u, dict) or "password" not in u:
            raise ValueError(f"User '{uname}' is missing a 'password' (hashed) in [users.{uname}]")
        creds["usernames"][uname] = {
            "name": u.get("name", uname),
            "password": u["password"],  # already hashed
        }

    # --- authenticator ---

    # --- authenticator ---
    authenticator = stauth.Authenticate(
        creds,
        str(cookie.get("name", "session")),
        normalized_key,
        int(cookie.get("expiry_days", 30)),
    )

    return authenticator, roles_map
