import os
import re
import time
from datetime import datetime, timedelta
from queue import Queue

import pandas as pd
import streamlit as st
from dateutil import parser as date_parser
from dateutil import tz
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from st_aggrid import AgGrid, GridOptionsBuilder

# ---------------- STREAMLIT CONFIG (must be FIRST Streamlit call) ----------------
st.set_page_config(page_title="WhatsApp Messaging Scheduler", layout="wide", initial_sidebar_state="expanded")



# ---------------- APP IMPORTS (helpers) ----------------
from secrets_helper import init_secrets_and_auth

def get_user_roles(username: str, roles_map: dict) -> set[str]:
    """Return the role(s) for a username."""
    if not username:
        return set()
    role = roles_map.get(username)
    if role is None:
        lower_map = {str(u).lower(): r for u, r in roles_map.items()}
        role = lower_map.get(str(username).lower())
    return {role} if role else set()

def has_role(role: str) -> bool:
    """Check if current logged-in user has a given role."""
    roles = st.session_state.get("roles", set())
    return role in roles

# ---------------- PATHS & SECRETS ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # -> your project dir
SECRETS_PATH = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
assert os.path.exists(SECRETS_PATH), f"secrets.toml not found at: {SECRETS_PATH}"
print("Using secrets at:", SECRETS_PATH)

# --- Auth singleton: create once, reuse ---
if "authenticator" not in st.session_state or "roles_map" not in st.session_state:
    authenticator, roles_map = init_secrets_and_auth(secrets_path=SECRETS_PATH, debug=False)
    st.session_state.authenticator = authenticator
    st.session_state.roles_map = roles_map
    st.write("Auth loaded. Users in roles_map:", len(roles_map))

authenticator = st.session_state.authenticator
roles_map = st.session_state.roles_map



# ---------------- LOGIN ----------------
name, auth_status, username = authenticator.login('main', fields={'Form name': 'Login'})

if auth_status:
    roles = get_user_roles(username, roles_map)
    st.session_state['roles'] = roles
    st.success(f"Welcome {name}!")
elif auth_status is False:
    st.error("Username/password is incorrect")
else:
    st.warning("Please log in")

# Sidebar: cookie reset (kept near top so it's always available)
try:
    COOKIE_NAME = st.secrets["cookie"]["name"]
except Exception:
    COOKIE_NAME = "wamsession"

with st.sidebar:
    st.subheader("Login")
    if st.button("Clear login cookie"):
        try:
            # Clear the configured cookie and common fallbacks
            authenticator.cookie_manager.delete(COOKIE_NAME)
            if COOKIE_NAME != "wamsession":
                authenticator.cookie_manager.delete("wamsession")
        except Exception as e:
            st.warning(f"Couldn't delete cookie: {e}")
        else:
            st.success("Cookie cleared. Reload the page and log in again.")
            st.stop()

# Gate the app
if auth_status:
    st.caption(f"Signed in as **{name}**")
elif auth_status is False:
    st.error("Invalid username/password")
    st.stop()
else:
    st.info("Please enter your credentials.")
    st.stop()

# Provide a proper logout in the sidebar
with st.sidebar:
    authenticator.logout("Logout", "sidebar")

# ---------------- DIRECTORIES ----------------
UPLOADS_DIR = "uploads"
LOGS_DIR = "logs"
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# ---------------- TIMEZONE ----------------
try:
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = tz.gettz("Asia/Kolkata")

# ---------------- SESSION STATE ----------------
st.session_state.setdefault("logs", {"scheduled": [], "delivered": [], "failed": []})
st.session_state.setdefault("scheduled_ids", set())
st.session_state.setdefault("active_upload_log", None)
st.session_state.setdefault("refresh_toggle", False)
st.session_state.setdefault("log_queue", Queue())
st.session_state.setdefault("DELAY_SECONDS", 1.0)

# === Twilio (frontend) helpers ===
def get_twilio_creds_from_state():
    """Read Twilio creds from session_state (set via the UI)."""
    sid = (st.session_state.get("ACCOUNT_SID") or "").strip()
    tok = (st.session_state.get("AUTH_TOKEN") or "").strip()
    wa_from = (st.session_state.get("FROM_WHATSAPP") or "").strip()
    return sid, tok, wa_from

def validate_twilio_creds_frontend():
    """Validate Twilio creds the user typed in the UI (no secrets.toml)."""
    sid, tok, wa_from = get_twilio_creds_from_state()
    errors = []
    if not re.fullmatch(r"AC[0-9a-fA-F]{32}", sid or ""):
        errors.append("Invalid Twilio Account SID (must start with 'AC' + 32 hex chars)")
    if not tok or len(tok) < 20:
        errors.append("Twilio Auth Token looks too short")
    if not wa_from or not wa_from.startswith("whatsapp:"):
        errors.append("From WhatsApp number must start with 'whatsapp:' (e.g., whatsapp:+1415XXXXXXX)")
    return errors

# ---------------- CSS ----------------
st.markdown(
    """
<style>
[data-testid="stSidebar"] > div:first-child {background-color: #8B2500; padding-top:14px;}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] label, [data-testid="stSidebar"] p {color:white;}
.stButton>button, .stDownloadButton>button { width:100%; margin:6px 0; color:black !important; background-color:#1E3A8A !important;
  border-radius:8px !important; border:1px solid #000 !important; transition: background-color 0.2s ease !important; }
.stButton>button:hover, .stDownloadButton>button:hover {background-color:#8B2500 !important; color:black !important;}
div[data-testid="stFileUploadDropzone"] button, div[data-testid="stFileUploadDropzone"] div > button {
  background-color: #8B2500 !important; color: white !important; border-radius: 8px !important; transition: background-color 0.2s ease !important; }
div[data-testid="stFileUploadDropzone"] button:hover, div[data-testid="stFileUploadDropzone"] div > button:hover {
  background-color: #1E3A8A !important; color: white !important; }
.twilio-shell input {border:2px solid red !important; padding:6px 8px !important; border-radius:6px !important;}
.twilio-shell input:hover, .twilio-shell input:focus {border-color:darkred !important;}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------- LOGGING HELPERS ----------------
def enqueue_log(kind, payload):
    try:
        st.session_state.log_queue.put((kind, payload), block=False)
    except Exception:
        pass

def drain_log_queue(max_items=10000):
    moved = 0
    while moved < max_items:
        try:
            kind, payload = st.session_state.log_queue.get_nowait()
        except Exception:
            break
        kind = kind if kind in ("scheduled", "delivered", "failed") else "scheduled"
        st.session_state.logs.setdefault(kind, []).append(payload)
        moved += 1

# ---------------- DATA HELPERS ----------------
DATETIME_CANDS = [
    "datetime","date_time","date/time","date time","timestamp","scheduled_at","scheduled",
    "sendtime","send_time","send_date","time","date",
]
DATE_CANDS = ["date", "send_date", "day"]
TIME_CANDS = ["time", "send_time", "hour", "minute"]
MOBILE_CANDS = ["mobile", "phone", "contact", "number", "mobile_number"]
MEDIA_CANDS = ["media","media_path","image","url","file","media_url"]

def try_parse_datetime(val):
    if val is None or (isinstance(val, float) and pd.isna(val)): return None
    if isinstance(val, (pd.Timestamp, datetime)):
        return val.to_pydatetime() if isinstance(val, pd.Timestamp) else val
    s = str(val).strip()
    if s == "": return None
    for dayfirst in (True, False):
        try:
            return date_parser.parse(s, fuzzy=True, dayfirst=dayfirst)
        except Exception:
            continue
    try:
        dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
        if not pd.isna(dt): return dt.to_pydatetime()
    except Exception:
        pass
    return None

def to_ist(dt):
    if dt is None: return None
    if dt.tzinfo is None:
        try: return dt.replace(tzinfo=IST)
        except Exception: return datetime.fromtimestamp(dt.timestamp(), IST)
    try: return dt.astimezone(IST)
    except Exception: return dt.replace(tzinfo=IST)

def normalize_phone(raw):
    if raw is None: return ""
    s = str(raw).strip()
    if re.match(r"^\d+\.?\d*e[+-]?\d+$", s, re.IGNORECASE):
        s = "{:.0f}".format(float(s))
    s = re.sub(r"[()\s\-]", "", s)
    if s.startswith("+"):
        return re.sub(r"[^\d+]", "", s)
    digits = re.sub(r"\D", "", s)
    if len(digits) == 10:
        return "+91" + digits
    elif len(digits) > 10:
        if digits.startswith("0"):
            digits = digits.lstrip("0")
        return "+" + digits
    return digits

def find_col_by_candidates(cols, candidates):
    cols_l = [c.lower() for c in cols]
    for cand in candidates:
        if cand in cols_l:
            return cols[cols_l.index(cand)]
    for cand in candidates:
        for i, c in enumerate(cols_l):
            if cand in c:
                return cols[i]
    return None

def read_any_table(uploaded_file):
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    if name.endswith(".csv"):
        try:
            return pd.read_csv(uploaded_file, dtype=str)
        except Exception:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, encoding="latin1", low_memory=False, dtype=str)
    else:
        try:
            uploaded_file.seek(0)
            return pd.read_excel(uploaded_file, engine="openpyxl", dtype=str)
        except Exception:
            try:
                uploaded_file.seek(0)
                return pd.read_excel(uploaded_file, dtype=str)
            except Exception:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, encoding="latin1", low_memory=False, dtype=str)

def post_process_mobile_column(df):
    mobile_col = find_col_by_candidates(df.columns, MOBILE_CANDS)
    if mobile_col:
        df[mobile_col] = df[mobile_col].astype(str).str.strip()
    return df

def parse_row_datetime(row, cols):
    dt_col = find_col_by_candidates(cols, DATETIME_CANDS)
    if dt_col and pd.notna(row.get(dt_col, None)) and str(row.get(dt_col)).strip() != "":
        dt = try_parse_datetime(row.get(dt_col))
        if dt: return dt
    date_col = find_col_by_candidates(cols, DATE_CANDS)
    time_col = find_col_by_candidates(cols, TIME_CANDS)
    if date_col and time_col and pd.notna(row.get(date_col, None)):
        combined = f"{row.get(date_col,'')} {row.get(time_col,'')}"
        dt = try_parse_datetime(combined)
        if dt: return dt
    for c in cols:
        v = row.get(c)
        if pd.isna(v): continue
        s = str(v)
        if re.search(r"\d{1,4}[-/:\s]\d{1,4}", s):
            dt = try_parse_datetime(s)
            if dt: return dt
    return None

def parse_to_jobs(df, source_filename_base):
    cols = df.columns.tolist()
    name_col = find_col_by_candidates(cols, ["name", "full name", "fullname", "patient"])
    mobile_col = find_col_by_candidates(cols, MOBILE_CANDS)
    media_col = find_col_by_candidates(cols, MEDIA_CANDS)

    jobs, conversion_log_rows = [], []
    for idx, row in df.iterrows():
        phone = normalize_phone(row.get(mobile_col, "") if mobile_col else "")
        name = row.get(name_col, "") if name_col else ""
        media = row.get(media_col, "") if media_col else ""

        raw_dt = parse_row_datetime(row, cols)
        if raw_dt is None:
            scheduled_at = datetime.now().replace(tzinfo=IST) + timedelta(seconds=5)
            detected_tz = "NoDateGiven"
            converted_ist = scheduled_at
        else:
            if raw_dt.tzinfo is None:
                detected_tz = "Assumed IST"
                scheduled_at = raw_dt.replace(tzinfo=IST)
            else:
                detected_tz = str(raw_dt.tzinfo)
                scheduled_at = to_ist(raw_dt)
            converted_ist = to_ist(raw_dt) if raw_dt else scheduled_at

        jid = f"{phone}|{media}|{converted_ist.timestamp() if converted_ist else datetime.now().timestamp()}|{idx}"
        jobs.append({
            "job_id": jid,
            "mobile_number": phone,
            "name": name,
            "media_url": media if pd.notna(media) else "",
            "scheduled_at": scheduled_at,
        })

        dt_src_col = find_col_by_candidates(cols, DATETIME_CANDS)
        original_value = row.get(dt_src_col, "") if dt_src_col else ""
        if not original_value:
            date_col = find_col_by_candidates(cols, DATE_CANDS)
            time_col = find_col_by_candidates(cols, TIME_CANDS)
            if date_col:
                original_value = str(row.get(date_col, ""))
            if date_col and time_col:
                original_value += " " + str(row.get(time_col, ""))

        conversion_log_rows.append({
            "row_index": int(idx),
            "mobile_number": phone,
            "original_value": original_value,
            "detected_timezone": detected_tz,
            "converted_ist": converted_ist.isoformat() if converted_ist else "",
        })

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_base = re.sub(r"[^\w\-]", "_", source_filename_base)
    log_filename = f"{safe_base}_log_{ts}.csv"
    log_path = os.path.join(LOGS_DIR, log_filename)
    pd.DataFrame(conversion_log_rows).to_csv(log_path, index=False)
    st.session_state.active_upload_log = log_path
    return jobs

# ---------------- SCHEDULER SINGLETON ----------------
if "scheduler" not in st.session_state:
    st.session_state.scheduler = BackgroundScheduler()
    st.session_state.scheduler.start()
scheduler = st.session_state.scheduler

# ---------------- SENDER ----------------
def send_whatsapp_message(job, creds, delay_seconds=1.0):
    sid, tok, wa_from = creds
    try:
        client = Client(sid, tok)

        to_number = job["mobile_number"]
        if to_number and not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"

        media_arg = None
        media = job.get("media_url", "")
        if media:
            if re.match(r"^https?://", media, re.IGNORECASE):
                media_arg = [media]
            else:
                raise ValueError(f"media_url must be a public http(s) URL: {media}")

        msg = client.messages.create(
            from_=wa_from,
            to=to_number,
            body=f"Hello {job.get('name', '')}",
            media_url=media_arg,
        )

        enqueue_log("delivered", {**job, "sid": getattr(msg, "sid", "")})

    except TwilioRestException as e:
        enqueue_log("failed", {**job, "error": str(e)})
    except Exception as e:
        enqueue_log("failed", {**job, "error": str(e)})
    finally:
        try:
            d = float(delay_seconds or 0)
            if d > 0:
                time.sleep(d)
        except Exception:
            pass

def schedule_job(job):
    if job["job_id"] in st.session_state.scheduled_ids:
        return
    creds = get_twilio_creds_from_state()
    delay = float(st.session_state.get("DELAY_SECONDS", 1.0))

    scheduler.add_job(
        send_whatsapp_message,
        "date",
        run_date=job["scheduled_at"],
        args=[job, creds, delay],
        id=job["job_id"],
        replace_existing=True,
        misfire_grace_time=60,
    )
    st.session_state.scheduled_ids.add(job["job_id"])
    enqueue_log("scheduled", job)

# ---------------- SIDEBAR ----------------
with st.sidebar:
    if os.path.exists("logo tablets.png"):
        st.image("logo tablets.png", width=140)
    st.markdown("<h2>Dashboard</h2>", unsafe_allow_html=True)

    if has_role("admin"):
        st.subheader("Message Settings")
        st.session_state.DELAY_SECONDS = st.number_input(
            "Delay between messages (seconds)",
            min_value=0.0, max_value=60.0,
            value=float(st.session_state.get("DELAY_SECONDS", 1.0)),
            step=0.5,
        )
    else:
        st.caption("Pacing is configured by Admin.")

    # Log panes
    for label, key in [("Scheduled Messages", "scheduled"),
                       ("Delivered Messages", "delivered"),
                       ("Failed Messages", "failed")]:
        with st.expander(label, expanded=False):
            drain_log_queue()  # keep fresh
            rows = st.session_state.logs.get(key, [])
            if rows:
                df = pd.DataFrame(rows)
                gb = GridOptionsBuilder.from_dataframe(df)
                gb.configure_default_column(sortable=True, filter=True, resizable=True)
                gb.configure_grid_options(domLayout='autoHeight')
                AgGrid(df, gridOptions=gb.build(), fit_columns_on_grid_load=True, height=200)

            active_log = st.session_state.get("active_upload_log", None)
            if active_log and os.path.exists(active_log):
                try:
                    with open(active_log, "rb") as f:
                        data = f.read()
                    st.download_button("Download Log Report", data=data,
                        file_name=os.path.basename(active_log), mime="text/csv", key=f"dl_{key}")
                except Exception:
                    csv_bytes = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
                    st.download_button("Download Log Report", data=csv_bytes,
                        file_name=f"{key}_logs.csv", mime="text/csv", key=f"dl2_{key}")
            else:
                csv_bytes = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
                st.download_button("Download Log Report", data=csv_bytes,
                    file_name=f"{key}_logs.csv", mime="text/csv", key=f"dl3_{key}")

            if st.button("Clear Logs", key=f"clear_{key}"):
                st.session_state.logs[key] = []
                a = st.session_state.get("active_upload_log", None)
                if a and os.path.exists(a):
                    try: os.remove(a)
                    except Exception: pass
                    st.session_state.active_upload_log = None
                st.session_state.refresh_toggle = not st.session_state.refresh_toggle

# ---------------- MAIN AREA ----------------
left_col, _ = st.columns([3, 1])
with left_col:
    st.markdown("<h1>WhatsApp Messaging Scheduler</h1>", unsafe_allow_html=True)

    # Twilio credentials UI (first) —— then validate
    is_admin = has_role("admin")

    with st.expander("Twilio Credentials", expanded=True):
        if is_admin:
            st.markdown('<div class="twilio-shell">', unsafe_allow_html=True)
            st.session_state["ACCOUNT_SID"] = st.text_input(
                "Account SID",
                value=st.session_state.get("ACCOUNT_SID", ""),
                type="password",
                key="acct_sid"
            )
            st.session_state["AUTH_TOKEN"] = st.text_input(
                "Auth Token",
                value=st.session_state.get("AUTH_TOKEN", ""),
                type="password",
                key="auth_tok"
            )
            st.session_state["FROM_WHATSAPP"] = st.text_input(
                "From WhatsApp Number (e.g., whatsapp:+1415XXXXXXX)",
                value=st.session_state.get("FROM_WHATSAPP", "whatsapp:+"),
                key="from_wa"
            )
            st.markdown('</div>', unsafe_allow_html=True)
            st.caption("These credentials are stored only in memory for this session.")
        else:
            # Non-admins can see whether sending is configured, but not the secrets
            sid_ok = bool(st.session_state.get("ACCOUNT_SID"))
            tok_ok = bool(st.session_state.get("AUTH_TOKEN"))
            from_ok = bool(st.session_state.get("FROM_WHATSAPP"))
            st.write(
                f"Twilio configured: SID={'✅' if sid_ok else '❌'}, "
                f"Token={'✅' if tok_ok else '❌'}, "
                f"From={'✅' if from_ok else '❌'}"
            )

    # Validate AFTER input fields are present
    errs = validate_twilio_creds_frontend()
    if errs:
        st.error(" • " + "\n • ".join(errs))
        st.stop()

    # Quick Test sender
    st.markdown("### Quick Test")
    test_to = st.text_input("Send a test message to (E.164, e.g., +91XXXXXXXXXX)", value="")
    if st.button("Send WhatsApp Test"):
        sid, tok, wa_from = get_twilio_creds_from_state()
        if not re.match(r"^\+?\d{10,15}$", test_to.replace("whatsapp:", "")):
            st.error("Enter a valid E.164 number, e.g. +91XXXXXXXXXX")
        else:
            if not test_to.startswith("whatsapp:"):
                test_to = f"whatsapp:{test_to}"
            try:
                client = Client(sid, tok)
                msg = client.messages.create(
                    from_=wa_from,
                    to=test_to,
                    body="Streamlit test ✅ If you see this, Twilio WhatsApp works!"
                )
                st.success(f"Sent! SID: {msg.sid}")
            except TwilioRestException as e:
                st.error(f"Twilio error: {e}")
            except Exception as e:
                st.error(f"Error: {e}")

    st.markdown("<h2><b>Upload the CSV / Excel</b></h2>", unsafe_allow_html=True)
    uploaded_files = st.file_uploader(
        "Choose CSV or Excel files",
        type=["csv", "xls", "xlsx", "xlsm", "xlsb", "ods"],
        accept_multiple_files=True,
        help="Columns accepted: name, mobile_number, media_path/Media_URL, date, time OR combined datetime column.",
    )

    if uploaded_files:
        total_scheduled = 0
        for uploaded in uploaded_files:
            base_name = os.path.splitext(uploaded.name)[0]
            df = read_any_table(uploaded)
            df = post_process_mobile_column(df)
            if df is None or df.empty:
                st.warning(f"No data found in {uploaded.name}.")
                continue

            st.markdown(f"**Preview: {uploaded.name} (first 10 rows)**")
            AgGrid(
                df.head(10),
                gridOptions=GridOptionsBuilder.from_dataframe(df.head(10)).build(),
                height=200,
                fit_columns_on_grid_load=True,
            )

            jobs = parse_to_jobs(df, base_name)
            for job in jobs:
                schedule_job(job)
            total_scheduled += len(jobs)

        if total_scheduled:
            st.success(f"Scheduled {total_scheduled} messages from {len(uploaded_files)} file(s).")

            # your existing imports
            from apscheduler.schedulers.background import BackgroundScheduler
            import time
            import os
            import atexit
            from flask import Flask


            # your existing functions and job logic
            def send_whatsapp_message():
                print("Sending WhatsApp message...")


            # create scheduler and add your existing jobs
            scheduler = BackgroundScheduler()
            scheduler.add_job(send_whatsapp_message, "interval", minutes=1)
            scheduler.start()

            # shut down gracefully
            atexit.register(lambda: scheduler.shutdown())

            # Flask app to keep Render process alive
            app = Flask(__name__)


            @app.route("/")
            def home():
                return "Scheduler is running on Render!"


            # run flask server (MUST be last!)
            if __name__ == "__main__":
                port = int(os.environ.get("PORT", 5000))  # Render provides PORT
                app.run(host="0.0.0.0", port=port)

