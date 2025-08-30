from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import time
from send_whatsapp import send_whatsapp_media

def send_whatsapp_media(mobile_number, media_url, message_body):
    # your Twilio message sending code here
    print(f"Sending message to {mobile_number} with media {media_url} and body {message_body}")
    # Use your Twilio client to send message here


def schedule_message_job():
    scheduler = BackgroundScheduler()
    scheduler.start()

    run_time = datetime.datetime.now() + datetime.timedelta(seconds=30)
    print(f"Scheduling message to send at {run_time}")

    scheduler.add_job(
        send_whatsapp_media,
        'date',
        run_date=run_time,
        args=[
            "+911234567890",
            "https://example.com/sample.jpg",
            "Hello from scheduler!"
        ]
    )

    try:
        # Keep the scheduler running
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("Scheduler stopped.")

if __name__ == "__main__":
    schedule_message_job()
