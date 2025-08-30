import streamlit as st
from secrets_helper import init_secrets_and_auth, get_user_roles

st.set_page_config(page_title="WhatsApp Scheduler", page_icon="📆", layout="wide")

# Build authenticator & configs from secrets.toml
try:
    authenticator, roles_map, twilio_cfg = init_secrets_and_auth()
except Exception as e:
    st.error(f"Configuration error: {e}")
    st.stop()

# Render login form (appears until authenticated)
name, authentication_status, username = authenticator.login("Login", "main")

if authentication_status is False:
    st.error("Username/password is incorrect.")
elif authentication_status is None:
    st.warning("Please enter your username and password.")
else:
    # Authenticated
    st.sidebar.success(f"Logged in as: {username}")
    authenticator.logout("Logout", "sidebar")

    # Role checks
    user_roles = get_user_roles(username, roles_map)

    # Show Twilio config health (optional)
    with st.expander("Twilio configuration status"):
        ok = all([twilio_cfg.account_sid, twilio_cfg.auth_token, twilio_cfg.from_whatsapp])
        st.write("Loaded:", "✅" if ok else "⚠️ Missing values")
        st.code(
            f"from: {twilio_cfg.from_whatsapp or '(not set)'}\n"
            f"sid:   {'set' if twilio_cfg.account_sid else '(not set)'}\n"
            f"token: {'set' if twilio_cfg.auth_token else '(not set)'}"
        )

    st.markdown("## Dashboard")

    # Admin-only section
    if "admin" in user_roles:
        st.subheader("🔐 Admin Panel")
        st.info("Only users with the 'admin' role can see this section.")

    # Ops section (visible to ops and admin)
    if "ops" in user_roles or "admin" in user_roles:
        st.subheader("🛠️ Ops Tools")
        st.write("Schedule WhatsApp messages, monitor jobs, etc.")

    # If user has no explicit role
    if not user_roles:
        st.subheader("👤 User Area")
        st.write("You are authenticated but have no explicit role.")
