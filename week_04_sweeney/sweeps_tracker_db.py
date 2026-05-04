import sqlite3
from datetime import datetime, date

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