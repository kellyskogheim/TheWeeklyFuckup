import os
import base64
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from google.auth.exceptions import RefreshError

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                # If the token was revoked or expired in Testing mode,
                # clear it out and force a fresh browser login flow
                print("Token expired or revoked by Google. Re-authenticating...")
                os.remove('token.json')
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)

def scrape_wardrobe_images():
    service = get_gmail_service()
    
    # Grabs anything with an attachment from the last 36 hours.
    query = 'newer_than:36h has:attachment'
    
    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])

    if not messages:
        print("No messages found from last 36 hours with attachments.")
        return

    if not os.path.exists('garderobe'):
        os.makedirs('garderobe')

    for msg in messages:
        message = service.users().messages().get(userId='me', id=msg['id']).execute()
        headers = message['payload']['headers']
        subject = next(h['value'] for h in headers if h['name'] == 'Subject')
        
        # Clean subject line for use as a filename
        safe_subject = "".join([c for c in subject if c.isalnum() or c in (' ', '_')]).rstrip()
        
        parts = message['payload'].get('parts', [])
        for part in parts:
            if part['filename'] and any(ext in part['filename'].lower() for ext in ['.jpg', '.png', '.jpeg']):
                attachment_id = part['body']['attachmentId']
                attachment = service.users().messages().attachments().get(
                    userId='me', messageId=msg['id'], id=attachment_id).execute()
                
                data = attachment['data']
                file_data = base64.urlsafe_b64decode(data.encode('UTF-8'))
                
                extension = os.path.splitext(part['filename'])[1]
                file_path = os.path.join('garderobe', f"{safe_subject}{extension}")
                
                with open(file_path, 'wb') as f:
                    f.write(file_data)
                print(f"Saved: {file_path}")

if __name__ == '__main__':
    scrape_wardrobe_images()