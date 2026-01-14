# Merlin Google Drive Backup Integration Guide

This guide explains how to enable automatic backup of your Merlin chat history to Google Drive.

---

## 1. Set Up Google Drive API Credentials
- Go to https://console.cloud.google.com/apis/credentials
- Create a new project (if needed).
- Enable the Google Drive API for your project.
- Create OAuth 2.0 Client ID credentials (Desktop or Web app).
- Download the `credentials.json` file and place it in your Merlin project directory.

## 2. Install Required Python Packages
```
pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

## 3. Python Backup Script Example
This script uploads your zipped chat history to your Google Drive root folder.

```python
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle

SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_PICKLE = 'token.pickle'

# Authenticate and build the Drive service
creds = None
if os.path.exists(TOKEN_PICKLE):
    with open(TOKEN_PICKLE, 'rb') as token:
        creds = pickle.load(token)
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
    with open(TOKEN_PICKLE, 'wb') as token:
        pickle.dump(creds, token)
service = build('drive', 'v3', credentials=creds)

# Path to your zipped chat history
zip_path = 'merlin_chat_history.zip'
file_metadata = {'name': os.path.basename(zip_path)}
media = MediaFileUpload(zip_path, mimetype='application/zip')
file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
print('Uploaded file ID:', file.get('id'))
```

## 4. Automate Backup
- Call this script after exporting your chat history zip (or on a schedule).
- You can integrate it into your FastAPI endpoint or run as a separate process.

---

This setup gives you secure, automatic Merlin chat backups to your Google Drive!