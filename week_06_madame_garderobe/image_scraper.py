import os
import base64
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime, timedelta

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def scrape_wardrobe_images():
    service = get_gmail_service()
    
    # Calculate "yesterday" in Gmail search format (YYYY/MM/DD)
    yesterday = (datetime.now() - timedelta(1)).strftime('%Y/%m/%d')
    today = datetime.now().strftime('%Y/%m/%d')
    query = f'after:{yesterday} before:{today} has:attachment'
    
    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])

    if not messages:
        print("No messages found from yesterday with attachments.")
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