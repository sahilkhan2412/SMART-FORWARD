import time
from app import email_monitor

print("EMAIL WORKER STARTING...", flush=True)

time.sleep(15)

print("EMAIL WORKER STARTED...", flush=True)

email_monitor()
