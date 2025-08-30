import os
import pandas as pd
from twilio.rest import Client
from apscheduler.schedulers.blocking import BlockingScheduler
from dateutil import tz
from datetime import datetime
import time

# ========= Config =========
CSV_PATH = "messages.csv"
TIMEZONE = tz.gettz("Asia/Kolkata")
DRY_RUN = True  # start True to only log; set to False to actually send

# Twilio creds
ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM")  # e.g., +91XXXXXXXXXX

if not all([ACCOUNT_SID, AUTH_TOKEN, WHATSAPP_FROM]):
    raise RuntimeError("Missing TWILIO env vars. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM")

client = Client(ACCOUNT_SID, AUTH_TOKEN)

def send_whatsapp(to_number: str, body: str):
    msg = client.messages.create(
        from_ = f"whatsapp:{WHATSAPP_FROM}",
        to    = f"whatsapp:{to_number}",
        body  = body
    )
    print(f"[SENT] {to_number} SID={msg.sid}")

def schedule_messages(rows):
    sched = BlockingScheduler(timezone=TIMEZONE)

    for idx, row in rows.iterrows():
        phone = str(row["phone"]).strip()
        body  = str(row["message"])
        send_at_str = str(row["send_at"]).strip()

        # parse time as IST
        try:
            # pandas may read as Timestamp already
            if isinstance(row["send_at"], pd.Timestamp):
                send_time_ist = row["send_at"].to_pydatetime().replace(tzinfo=TIMEZONE)
            else:
                send_time_ist = datetime.strptime(send_at_str, "%Y-%m-%d %H:%M").replace(tzinfo=TIMEZONE)
        except Exception as e:
            print(f"[SKIP] Row {idx}: invalid send_at '{send_at_str}': {e}")
            continue

        now_ist = datetime.now(TIMEZONE)
        if send_time_ist <= now_ist:
            print(f"[SKIP] Row {idx}: time {send_time_ist} is not in the future")
            continue
        if not phone.startswith("+"):
            print(f"[SKIP] Row {idx}: phone must be E.164 (+country...), got '{phone}'")
            continue
        if not body or body.strip() == "":
            print(f"[SKIP] Row {idx}: empty message")
            continue

        def job(to=phone, text=body):
            if DRY_RUN:
                print(f"[DRY-RUN WOULD SEND] {to} :: {text}")
            else:
                try:
                    send_whatsapp(to, text)
                except Exception as ex:
                    print(f"[ERROR] Sending to {to}: {ex}")

        # schedule
        sched.add_job(job, "date", run_date=send_time_ist)
        print(f"[SCHEDULED] {phone} at {send_time_ist.strftime('%Y-%m-%d %H:%M %Z')} :: {body[:60]}")

    print("[INFO] Scheduler started. Waiting for jobs...")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n[INFO] Stopped.")

def main():
    # Load CSV
    df = pd.read_csv(CSV_PATH)
    required = {"phone", "message", "send_at"}
    if not required.issubset(df.columns):
        raise RuntimeError(f"CSV must have columns: {required}. Found: {list(df.columns)}")

    # Coerce send_at to datetime if possible
    try:
        df["send_at"] = pd.to_datetime(df["send_at"], format="%Y-%m-%d %H:%M", errors="coerce")
    except Exception:
        pass

    # Show a quick summary
    print("=== PREVIEW ===")
    print(df.head())
    print("===============")

    schedule_messages(df)

if __name__ == "__main__":
    main()
