import tomllib, os
data = tomllib.load(open(os.path.join(".streamlit", "secrets.toml"), "rb"))
print("top:", data.keys())
print("users keys:", list(data.get("users", {}).keys()))
# If nested, you'll see ['admin', 'ops']; if flat, you'll see ['admin_name', ...]
