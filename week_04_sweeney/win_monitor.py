import os.path
import sqlite3
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
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

def check_for_wins():
    service = get_gmail_service()
    # Search for emails from the last 7 days with "Congratulations" or "Winner"
    query = 'newer_than:7d (subject:Congratulations OR subject:Congrats OR subject:Winner OR subject:Won)'
    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])

    if not messages:
        print("No new potential win emails found.")
        return

    with sqlite3.connect("sweeps_tracker.db") as conn:
        cursor = conn.cursor()
        
        for msg in messages:
            txt = service.users().messages().get(userId='me', id=msg['id']).execute()
            subject = next(header['value'] for header in txt['payload']['headers'] if header['name'] == 'Subject')
            
            # Logic: Look for a giveaway name that is mentioned in the subject line
            # This uses Python substring search instead of SQLite LIKE matching.
            cursor.execute("""
                SELECT DISTINCT g.id, g.name
                FROM giveaways g
                JOIN entries e ON g.id = e.giveaway_id
            """)
            match = None
            lower_subject = subject.lower()
            for g_id, g_name in cursor.fetchall():
                if g_name and g_name.lower() in lower_subject:
                    match = (g_id, g_name)
                    break
            
            if match:
                g_id, g_name = match
                print(f"🌟 MATCH FOUND: '{subject}' matches entry for '{g_name}'!")
                
                # Check if we already logged this win to avoid duplicates
                cursor.execute("SELECT id FROM winnings WHERE giveaway_id = ? AND prize_description = ?", (g_id, subject))
                if not cursor.fetchone():
                    # Instead of assuming it's a win, log it for review
                    cursor.execute("""
                        INSERT INTO winnings (giveaway_id, prize_description, date_won, status)
                        VALUES (?, ?, DATE('now'), 'unverified')
                    """, (g_id, f"CHECK EMAIL: {subject}"))
                    conn.commit()
                    print(f"✅ Logged win for {g_name} in the winnings table.")
            else:
                print(f"❓ Potential win email found, but no matching entry in DB: '{subject}'")

if __name__ == '__main__':
    check_for_wins()