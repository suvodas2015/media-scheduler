import pandas as pd
from twilio.rest import Client

# Twilio credentials
account_sid = "ACad148527704f0c316bb2d1888bf83eff"
auth_token = "841b0cdcc70497c369cb9b4661c6cf73"
client = Client(account_sid, auth_token)

# Path to your CSV file
csv_file = "recipients.csv"

# Load CSV
df = pd.read_csv(csv_file)


# ✅ Function to clean and standardize phone numbers
def clean_number(num):
    if pd.isna(num):
        return None
    num = str(num).strip()
    num = num.replace('"', '').replace("'", "").replace(" ", "")
    num = num.split('.')[0]  # remove decimals like 9.19874E+11

    # Remove any leading +
    if num.startswith("+"):
        num = num[1:]

    # Ensure starts with 91 (India)
    if not num.startswith("91"):
        num = "91" + num

    return f"+{num}"


# Clean all numbers
df["mobile_number"] = df["mobile_number"].apply(clean_number)

print("📂 Cleaned numbers:")
print(df["mobile_number"])

# Loop through contacts and send messages
for index, row in df.iterrows():
    phone = row["mobile_number"]
    name = str(row["name"]).strip()
    media_url = row["Media_URL"] if "Media_URL" in df.columns and pd.notna(row["Media_URL"]) else None

    body_text = "Hello Shivangi, this is a message from Twilio."


    try:
        if media_url:
            message = client.messages.create(
                from_="whatsapp:+918583966708",  # ✅ Your Twilio WhatsApp-enabled number
                to=f"whatsapp:{phone}",
                body=body_text,
                media_url=[media_url]
            )
        else:
            message = client.messages.create(
                from_="whatsapp:+918583966708",
                to=f"whatsapp:{phone}",
                body=body_text
            )

        print(f"✅ Sent to {name} ({phone}) - SID: {message.sid}")

    except Exception as e:
        print(f"❌ Error sending to {name} ({phone}): {e}")
