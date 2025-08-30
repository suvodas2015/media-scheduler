import os, re, secrets, shutil

ROOT = os.getcwd()
STREAMLIT_DIR = os.path.join(ROOT, ".streamlit")
SECRETS = os.path.join(STREAMLIT_DIR, "secrets.toml")
BACKUP = os.path.join(STREAMLIT_DIR, "secrets.toml.bak")

os.makedirs(STREAMLIT_DIR, exist_ok=True)

def gen_key():
    return secrets.token_hex(32)  # 64 hex chars

def ensure_cookie_block(text: str) -> str:
    # If no [cookie] section at all, append one cleanly
    if re.search(r"(?m)^\[cookie\]\s*$", text) is None:
        block = f'\n\n[cookie]\nname = "wamsession"\nkey  = "{gen_key()}"\nexpiry_days = 30\n'
        return (text.rstrip() + block + "\n") if text.strip() else block.lstrip()
    return text

def set_or_replace_name(text: str) -> str:
    # Inside [cookie] section, ensure name exists, else add it at top of the section
    def repl(m):
        section = m.group(0)
        if re.search(r'(?m)^\s*name\s*=\s*".*"\s*$', section) is None:
            section = section.replace("\n", '\nname = "wamsession"\n', 1)
        return section
    return re.sub(r"(?ms)^\[cookie\]\s*(.*?)(?=^\[|\Z)", repl, text)

def fix_key(text: str) -> str:
    # If key line exists but is short/invalid, replace value.
    # If missing, insert it after name.
    def repl(m):
        section = m.group(0)
        key_match = re.search(r'(?m)^\s*key\s*=\s*"(.*?)"\s*$', section)
        if key_match:
            current = key_match.group(1)
            if not isinstance(current, str) or len(current) < 32:
                section = re.sub(r'(?m)^(\s*key\s*=\s*)".*?"(\s*)$',
                                 r'\1"{}"\2'.format(gen_key()),
                                 section)
        else:
            # Insert after name=... if present, otherwise at top
            name_line = re.search(r'(?m)^\s*name\s*=\s*".*"\s*$', section)
            insertion = f'key  = "{gen_key()}"\n'
            if name_line:
                idx = name_line.end()
                section = section[:idx] + "\n" + insertion + section[idx:]
            else:
                # put key at top of the section body
                section = section.replace("\n", "\n" + insertion, 1)
        # Ensure expiry_days line exists; if not, add a default
        if re.search(r'(?m)^\s*expiry_days\s*=\s*\d+\s*$', section) is None:
            section = section.rstrip() + "\nexpiry_days = 30\n"
        return section
    return re.sub(r"(?ms)^\[cookie\]\s*(.*?)(?=^\[|\Z)", repl, text)

# 1) Load / create file
if not os.path.exists(SECRETS):
    with open(SECRETS, "w", encoding="utf-8") as f:
        f.write('[cookie]\nname = "wamsession"\nkey  = "{}"\nexpiry_days = 30\n'.format(gen_key()))
    print(f"Created {SECRETS} with a fresh cookie key.")
else:
    # 2) Backup
    shutil.copyfile(SECRETS, BACKUP)
    with open(SECRETS, "r", encoding="utf-8") as f:
        original = f.read()

    # 3) Patch
    text = original
    text = ensure_cookie_block(text)
    text = set_or_replace_name(text)
    text = fix_key(text)

    # 4) Save if changed
    if text != original:
        with open(SECRETS, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Updated {SECRETS}. Backup saved at {BACKUP}.")
    else:
        print("No changes needed; cookie settings already valid.")

print("Done. Restart Streamlit and, if needed, click 'Clear login cookie' in the sidebar.")
