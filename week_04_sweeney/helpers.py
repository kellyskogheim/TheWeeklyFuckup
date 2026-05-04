import sqlite3
from datetime import datetime, date
from typing import Optional, Tuple, List, Dict
import re


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


def update_giveaway_status(giveaway_id: int, status: str) -> None:
    """Update the status of a giveaway (e.g., to 'disregarded')."""
    with sqlite3.connect("sweeps_tracker.db") as conn:
        conn.execute("UPDATE giveaways SET status = ?, UpdateDate = DATE('now') WHERE id = ?", (status, giveaway_id))
        conn.commit()

