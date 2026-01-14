# MerlinSlackBot.py
# Slack bot for Merlin REST API chat
import os
import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

MERLIN_API_URL = 'http://localhost:8000/merlin/chat'
MERLIN_API_KEY = os.environ.get('MERLIN_API_KEY', 'merlin-secret-key')
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_APP_TOKEN = os.environ.get('SLACK_APP_TOKEN')

app = App(token=SLACK_BOT_TOKEN)

@app.message("")
def handle_message(message, say):
    user_input = message.get('text', '')
    user_id = message.get('user', 'default')
    if user_input.strip().lower() == '/history':
        try:
            resp = requests.get(
                f'http://localhost:8000/merlin/history/{user_id}',
                headers={'X-Merlin-Key': MERLIN_API_KEY},
                timeout=10
            )
            if resp.ok:
                history = resp.json().get('history', [])
                reply = '\n'.join([f"You: {h.get('user','')}\nMerlin: {h.get('merlin','')}" for h in history])
            else:
                reply = '[History API Error]'
        except Exception as e:
            reply = f'[History Network Error] {e}'
        say(reply)
        return
    try:
        resp = requests.post(
            MERLIN_API_URL,
            json={'user_input': user_input, 'user_id': user_id},
            headers={'X-Merlin-Key': MERLIN_API_KEY},
            timeout=10
        )
        if resp.ok:
            reply = resp.json().get('reply', '[No reply]')
        else:
            reply = '[API Error]'
    except Exception as e:
        reply = f'[Network Error] {e}'
    say(reply)

if __name__ == "__main__":
    if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
        print('Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN in your environment.')
    else:
        SocketModeHandler(app, SLACK_APP_TOKEN).start()
