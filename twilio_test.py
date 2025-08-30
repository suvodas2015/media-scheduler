from twilio.rest import Client

ACCOUNT_SID = "ACad148527704f0c316bb2d1888bf83eff"
AUTH_TOKEN = "841b0cdcc70497c369cb9b4661c6cf73"

client = Client(ACCOUNT_SID, AUTH_TOKEN)

message = client.messages.create(
    from_="whatsapp:+14155238886",  # Sandbox number
    to="whatsapp:+919830051812",    # Full number with country code
    body="Test message from Twilio Sandbox 🚀",
    media_url=["https://www.twilio.com/docs/documents/257/placeholder.png"]
)

print("SID:", message.sid)
