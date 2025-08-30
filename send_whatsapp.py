import pandas as pd
from twilio.rest import Client
import re




# Twilio credentials
TWILIO_WHATSAPP_NUMBER = "whatsapp:8583966708"  # Sandbox number
ACCOUNT_SID = "ACad148527704f0c316bb2d1888bf83eff"
AUTH_TOKEN = "841b0cdcc70497c369cb9b4661c6cf73"

client = Client(ACCOUNT_SID, AUTH_TOKEN)

def send_whatsapp_media():
    try:
        df = pd.read_csv("recipients.csv", dtype={'mobile_number': str})
        print("CSV columns:", list(df.columns))

        # Normalize headers (lowercase + no spaces)
        df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]

        # Try to find phone column
        phone_col = None
        for possible in ["mobile_number", "phone", "number", "contact"]:
            if possible in df.columns:
                phone_col = possible
                break

        if not phone_col:
            print("❌ No phone number column found! Make sure CSV has one.")
            return

        # Try to find media column
        media_col = None
        for possible in ["media_path", "media_url", "file", "url"]:
            if possible in df.columns:
                media_col = possible
                break

        for _, row in df.iterrows():
            mobile_number = str(row[phone_col]).strip()
            mobile_number = row['mobile_number'].strip()
            mobile_number = mobile_number.replace(".0", "")  # quick fix if still float string
            to_number = f"whatsapp:+{mobile_number}"

            media_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/React-icon.svg/1024px-React-icon.svg.png"

            print("Sending media URL:", media_url)  # <-- Add this line here

            try:
                to_number = f"whatsapp:+{mobile_number}"
                message = client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                body="Here's your scheduled message!",
                media_url=[media_url],
                to=to_number
                )
                print(f"✅ Message sent to {mobile_number}. SID: {message.sid}")
            except Exception as e:
                print(f"❌ Failed to send to {mobile_number}: {e}")

    except FileNotFoundError:
        print("❌ recipients.csv not found! Make sure the file is in the same folder.")

if __name__ == "__main__":
    send_whatsapp_media()
