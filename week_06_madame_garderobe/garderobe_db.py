import os
import sqlite3
import base64
import json
from pathlib import Path
from time import time
from PIL import Image
from langchain_core.messages import HumanMessage
from typing import List
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI

# --- 1. SETUP DATABASE ---
DB_NAME = "garderobe.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE,
            item_name TEXT,
            category TEXT,
            style_tags TEXT,
            formal_level INTEGER,
            color_palette TEXT,
            description TEXT
        )
    ''')
    conn.commit()
    return conn

# --- 2. SETUP LANGCHAIN & VISION MODEL ---
class WardrobeItem(BaseModel):
    category: str = Field(description="Top, Bottom, Shoes, One-Piece, Outerwear, or Accessory")
    formal_level: int = Field(description="Integer 1-10 (1: ultra-casual, 10: formal)")
    style_tags: List[str] = Field(description="List of 5 fashion keywords (e.g., minimalist, boho)")
    color_palette: str = Field(description="Primary and secondary colors")
    description: str = Field(description="A one-sentence fashionable description")

# Using Flash for speed and cost-efficiency in tagging
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
structured_llm = llm.with_structured_output(WardrobeItem)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def tag_item(image_path):
    base64_image = encode_image(image_path)
    
    message = HumanMessage(
        content=[
            {"type": "text", "text": "Analyze this clothing item for my wardrobe app."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
        ]
    )
    
    # This now returns a WardrobeItem object directly!
    return structured_llm.invoke([message])

# --- 3. MAIN EXECUTION LOOP ---
def main():
    conn = init_db()
    cursor = conn.cursor()
    
    garderobe_path = Path("garderobe")
    image_files = list(garderobe_path.glob("*.png"))
    
    print(f"Found {len(image_files)} items in garderobe.")

    for img_path in image_files:
        # Check if already processed
        cursor.execute("SELECT id FROM items WHERE file_path = ?", (str(img_path),))
        if cursor.fetchone():
            continue
        
        print(f"Tagging: {img_path.name}...")
        tags = tag_item(img_path)
        
        if tags:
            try:
                cursor.execute('''
                    INSERT INTO items (file_path, item_name, category, style_tags, formal_level, color_palette, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    str(img_path),
                    img_path.stem, # Uses filename as item name
                    tags.category,
                    ", ".join(tags.style_tags),
                    tags.formal_level,
                    tags.color_palette,
                    tags.description
                ))
                conn.commit()
                print(f"Successfully added {img_path.name} to database.")
            except sqlite3.IntegrityError:
                print(f"Skipping {img_path.name}: Already in database.")

    conn.close()
    print("Database update complete.")

if __name__ == "__main__":
    main()