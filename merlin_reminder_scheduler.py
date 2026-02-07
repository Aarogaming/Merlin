# Merlin Reminder Scheduler
# Example: Schedule a daily reminder at a set time (prints to console or can trigger notification)

import time
import datetime

REMINDER_HOUR = 9  # 9am
REMINDER_MINUTE = 0
MESSAGE = "Time to check in with Merlin!"

print("Merlin reminder scheduler running.")

while True:
    now = datetime.datetime.now()
    if now.hour == REMINDER_HOUR and now.minute == REMINDER_MINUTE:
        print(f"[{now}] {MESSAGE}")
        # Optionally, trigger a desktop notification here
        time.sleep(60)  # Avoid duplicate reminders in the same minute
    time.sleep(30)
