from twilio.rest import Client

ACCOUNT_SID = "ACad148527704f0c316bb2d1888bf83eff"
AUTH_TOKEN  = "841b0cdcc70497c369cb9b4661c6cf73"

client = Client(ACCOUNT_SID, AUTH_TOKEN)

msg = client.messages.create(
    from_="whatsapp:+918583966708",   # your Twilio approved WA sender
    to="whatsapp:+919830051812",      # your test phone
    body="✅ Test message from Production sender via Twilio"
)

print("Sent message SID:", msg.sid)
