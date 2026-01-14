# MerlinPythonCLIChat.py
# Simple Python CLI chat client for Merlin REST API
import os
import requests

API_URL = 'http://localhost:8000/merlin/chat'
HISTORY_URL = 'http://localhost:8000/merlin/history/'
API_KEY = os.environ.get('MERLIN_API_KEY', 'merlin-secret-key')
user_id = input('Enter your user ID (default): ') or 'default'

print('Merlin CLI Chat. Type "exit" to quit. Type "/history" to load chat history.')
while True:
    user_input = input('You: ')
    if user_input.strip().lower() == 'exit':
        break
    if user_input.strip().lower() == '/history':
        try:
            resp = requests.get(HISTORY_URL + user_id, headers={'X-Merlin-Key': API_KEY}, timeout=10)
            if resp.ok:
                history = resp.json().get('history', [])
                for entry in history:
                    print('You:', entry.get('user', ''))
                    print('Merlin:', entry.get('merlin', ''))
            else:
                print('[History API Error]')
        except Exception as e:
            print('[History Network Error]', e)
        continue
    try:
        resp = requests.post(
            API_URL,
            json={'user_input': user_input, 'user_id': user_id},
            headers={'X-Merlin-Key': API_KEY},
            timeout=10
        )
        if resp.ok:
            print('Merlin:', resp.json().get('reply', '[No reply]'))
        else:
            print('Merlin: [API Error]')
    except Exception as e:
        print('Merlin: [Network Error]', e)
