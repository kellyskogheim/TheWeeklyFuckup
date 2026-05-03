import sqlite3
from datetime import datetime, date
from typing import Optional, Tuple, List, Dict
import re

try:
    from transformers import pipeline
except ImportError:  # type: ignore
    pipeline = None

def get_active_user() -> Optional[Dict[str, str]]:
    with sqlite3.connect("sweeps_tracker.db") as conn:
        cursor = conn.execute("SELECT * FROM users WHERE is_active = 1 LIMIT 1")
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
    return None


def calculate_age(birth_date: date, today: date) -> int:
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return age


def parse_eligibility(eligibility: str) -> Tuple[int, List[str], List[str]]:
    # Parse min_age, excluded_states, and included_states from eligibility text.
    # Examples handled:
    # - "Open to residents of the fifty (50) United States and DC, ages 18 and older."
    # - "Open to residents of the forty-eight (48) contiguous United States and DC (excludes AK, HI) ages 18 and older."
    # - "Open to residents of the fifty (50) United States, DC, (excluding AZ, FL, and NV) and Canada (excludes Quebec), ages 18 and older."
    # - "Open to residents of the IL, IN, WI, ages 18 and older." -> included_states: IL, IN, WI
    # - "Open worldwide to those ages 18 and older."
    # - "Not stated."
    text = eligibility or ""
    min_age = 18
    excluded_states: List[str] = []
    included_states: List[str] = []

    # Age parsing: prefer explicit age language, avoid matching numbers in the location text.
    age_match = re.search(r"\b(?:ages?|age)\s*(?:of\s*)?(\d{1,2})\s*(?:\+|and older|or older|and up|years old)?\b", text, re.I)
    if not age_match:
        age_match = re.search(r"\b(\d{1,2})\s*(?:\+|and older|or older|and up)\b", text, re.I)
    if age_match:
        min_age = int(age_match.group(1))

    # Find exclude/except phrases and extract state abbreviations.
    exclude_phrases = re.findall(r"\b(?:exclud(?:es|ing)|except)\b([^\.\(\);]*)", text, re.I)
    for phrase in exclude_phrases:
        phrase = phrase.replace('and', ',')
        codes = re.findall(r"\b([A-Z]{2})\b", phrase)
        excluded_states.extend(code.upper() for code in codes)

    # Also capture parenthesized excludes, e.g. (excludes AK, HI)
    parenthesized = re.findall(r"\((?:exclud(?:es|ing)|except)\s*([^)]*)\)", text, re.I)
    for phrase in parenthesized:
        phrase = phrase.replace('and', ',')
        codes = re.findall(r"\b([A-Z]{2})\b", phrase)
        excluded_states.extend(code.upper() for code in codes)

    # Check for included-states-only eligibility (e.g., "Open to residents of the IL, IN, WI")
    # Look for state codes right after "residents of"
    if not excluded_states:  # Only parse included if no excludes
        included_match = re.search(r"residents?\s+of\s+(?:the\s+)?([A-Z]{2}(?:\s*,\s*[A-Z]{2})*)", text, re.I)
        if included_match:
            codes_text = included_match.group(1)
            codes_text = codes_text.replace(',', ' ')
            codes = re.findall(r"\b([A-Z]{2})\b", codes_text)
            included_states = sorted(set(code.upper() for code in codes))

    # Remove duplicates and normalize
    excluded_states = sorted(set(excluded_states))
    return min_age, excluded_states, included_states


def _build_llm_eligibility_prompt(user: Dict[str, str], age: int, rules_url: str, rules_text: str) -> str:
    return (
        "You are an eligibility assistant for sweepstakes entries. "
        "Evaluate whether the user below is eligible for the sweepstakes. "
        "Use only the user details and rules content provided. "
        "Answer with exactly True or False.\n\n"
        "User:\n"
        f"- state: {user.get('state_code', 'unknown')}\n"
        f"- zip: {user.get('zip_code', 'unknown')}\n"
        f"- country: {user.get('country', 'unknown')}\n"
        f"- age: {age}\n\n"
        "Giveaway rules URL:\n"
        f"{rules_url or 'N/A'}\n\n"
        "Rules text:\n"
        f"{rules_text}\n\n"
        "If the user is eligible under these rules, respond with True. Otherwise respond with False. "
        "Do not add any additional explanation."
    )


def _fetch_rules_text(rules_url: str) -> str:
    if not rules_url:
        return ""
    try:
        import requests
        response = requests.get(rules_url, timeout=15)
        response.raise_for_status()
        html = re.sub(r'<[^>]+>', ' ', response.text)
        return re.sub(r'\s+', ' ', html).strip()[:4000]
    except Exception:
        return ""


def is_eligible_with_llm(user: Dict[str, str], rules_url: str, model_name: str = 'facebook/opt-125m') -> bool:
    if pipeline is None:
        raise RuntimeError(
            'transformers is required for LLM eligibility checks. Install it with uv add transformers.'
        )

    birth_date = datetime.strptime(user['birth_date'], '%Y-%m-%d').date()
    age = calculate_age(birth_date, date.today())
    rules_text = _fetch_rules_text(rules_url)
    prompt = _build_llm_eligibility_prompt(user, age, rules_url, rules_text)

    generator = pipeline('text-generation', model=model_name, device='cpu')
    result = generator(prompt, max_new_tokens=32, do_sample=False)
    output = result[0]['generated_text'] if result else ''
    match = re.search(r'\b(True|False)\b', output, re.I)
    return match is not None and match.group(1).lower() == 'true'


def is_eligible(user: Dict[str, str], eligibility: str, today: date) -> bool:
    if not eligibility:
        return True
    
    min_age, excluded_states, included_states = parse_eligibility(eligibility)
    
    # Check age
    birth_date = datetime.strptime(user['birth_date'], '%Y-%m-%d').date()
    age = calculate_age(birth_date, today)
    if age < min_age:
        return False
    
    # Check state
    state = user['state_code'].upper()
    
    # If there are included states, user must be in one of them
    if included_states:
        if state not in included_states:
            return False
    # Otherwise, check excluded states
    elif state in excluded_states:
        return False
    
    return True


def get_eligible_giveaways() -> List[Dict[str, str]]:
    user = get_active_user()
    if not user:
        return []
    
    today = date.today()
    
    with sqlite3.connect("sweeps_tracker.db") as conn:
        # Get active giveaways
        giveaways = conn.execute("""
            SELECT id, name, entry_url, frequency, eligibility, start_date, end_date
            FROM giveaways
            WHERE status = 'active'
        """).fetchall()
        
        eligible = []
        for g in giveaways:
            g_dict = dict(zip(['id', 'name', 'entry_url', 'frequency', 'eligibility', 'start_date', 'end_date'], g))
            
            # Check eligibility
            if not is_eligible(user, g_dict['eligibility'], today):
                continue
            
            # Check entry history based on frequency
            freq = g_dict['frequency']
            if freq in ['Daily Entry', 'Weekly Entry', 'Monthly Entry', 'Unlimited Entry']:
                # Check if already entered based on rules
                if freq in ['Daily Entry', 'Unlimited Entry']:
                    # Exclude if entered today
                    cursor = conn.execute("""
                        SELECT 1 FROM entries 
                        WHERE giveaway_id = ? AND DATE(entry_date) = DATE('now')
                        LIMIT 1
                    """, (g_dict['id'],))
                    if cursor.fetchone():
                        continue
                elif freq == 'Weekly Entry':
                    # Exclude if entered within last week
                    cursor = conn.execute("""
                        SELECT 1 FROM entries 
                        WHERE giveaway_id = ? AND entry_date >= DATE('now', '-7 days')
                        LIMIT 1
                    """, (g_dict['id'],))
                    if cursor.fetchone():
                        continue
                elif freq == 'Monthly Entry':
                    # Exclude if entered within last month
                    cursor = conn.execute("""
                        SELECT 1 FROM entries 
                        WHERE giveaway_id = ? AND entry_date >= DATE('now', '-1 month')
                        LIMIT 1
                    """, (g_dict['id'],))
                    if cursor.fetchone():
                        continue
            else:
                # For other frequencies, exclude if any entry exists
                cursor = conn.execute("""
                    SELECT 1 FROM entries WHERE giveaway_id = ? LIMIT 1
                """, (g_dict['id'],))
                if cursor.fetchone():
                    continue
            
            eligible.append(g_dict)
        
        return eligible


def record_entry(giveaway_id: int, entry_date: datetime) -> None:
    with sqlite3.connect("sweeps_tracker.db") as conn:
        conn.execute("INSERT INTO entries (giveaway_id, entry_date) VALUES (?, ?)", (giveaway_id, entry_date))
        conn.commit()


def init_db():
    with sqlite3.connect("sweeps_tracker.db") as conn:
        cursor = conn.cursor()
        
        # 1. Giveaways Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                entry_url TEXT NOT NULL,
                frequency TEXT,          -- e.g., 'Daily', 'Weekly', 'Once'
                eligibility TEXT,        -- Summary of rules (e.g., 'US 18+')
                start_date DATE,
                end_date DATE,
                rules_url TEXT,
                status TEXT DEFAULT 'pending', -- 'active', 'disregarded', 'pending'
                LoadDate DATE,
                UpdateDate DATE,
                
                -- Ensure uniqueness by URL and Start Date
                UNIQUE(entry_url, start_date)
            )
        ''')

        # 2. Entry Log (To track entries)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                giveaway_id INTEGER,
                entry_date DATETIME,
                FOREIGN KEY (giveaway_id) REFERENCES giveaways (id)
            )
        ''')

        # 3. Winnings Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS winnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                giveaway_id INTEGER,
                prize_description TEXT NOT NULL,
                fair_market_value REAL, -- Important for taxes!
                date_won DATE,
                status TEXT DEFAULT 'pending', -- 'pending', 'received', 'claimed'
                tax_form_received BOOLEAN DEFAULT 0, -- Track if you got a 1099-MISC
                FOREIGN KEY (giveaway_id) REFERENCES giveaways (id)
            )
        ''')

        # 4. Users Table 
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT,
            last_name TEXT,
            email TEXT,
            state_code TEXT,      -- e.g., 'MI'
            birth_date DATE,
            zip_code TEXT,        
            phone_number TEXT,    
            address TEXT,
            city TEXT,
            country TEXT,
            is_active BOOLEAN DEFAULT 1
        )
        ''')
        # # Insert your profile 
        # cursor.execute('''
        #     INSERT OR IGNORE INTO users (first_name, last_name, email, state_code, birth_date, zip_code, phone_number, address, city, country)
        #     VALUES ('FirstName', 'LastName', 'email@address.com', 'ST', 'YYYY-MM-DD', '12345', '555-123-4567', '123 Main St', 'Anytown', 'USA')
        # ''')
        # # 
        
        conn.commit()

init_db()