import os, tomllib, re

PATH = r"C:\Users\SHIVANGI\PythonProject1\.streamlit\secrets.toml"
print("Reading:", PATH)
with open(PATH, "rb") as f:
    sec = tomllib.load(f)

print("Top-level keys:", list(sec.keys()))
users = sec.get("users")
print("[users] type:", type(users), "value:", users)

# Helpful diagnostics
if isinstance(users, dict):
    print("User subtables:", list(users.keys()))
else:
    print("⚠️ [users] is not a dict. Did you write [[users]] or 'users = {...}'?")

# Detect BOM on first key (common on Windows)
first_key = next(iter(sec.keys())) if sec else None
if first_key and first_key.startswith("\ufeff"):
    print("⚠️ BOM detected at start of file. Re-save as UTF-8 (no BOM).")
