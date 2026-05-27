
import sqlite3
import os
from pathlib import Path

DB_PATH = "garderobe.db"  

def update_wardrobe_item(item_id: int, name: str, category: str, tags: str, formal_rating: int, color: str, desc: str):
    """Updates all editable text fields for a specific wardrobe row."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE items 
            SET item_name = ?, category = ?, style_tags = ?, formal_level = ?, color_palette = ?, description = ?
            WHERE id = ?
        """, (name, category, tags, formal_rating, color, desc, item_id))
        conn.commit()

def delete_wardrobe_item(item_id: int):
    """
    Safely removes an item from the wardrobe system by deleting its 
    physical file on disk first, then removing its row from the database.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row  # Allows accessing columns by name
            cursor = conn.cursor()
            
            # Step 1: Query the file path before we erase the database row
            cursor.execute("SELECT path FROM items WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            
            if row:
                file_path_str = row['path']
                if file_path_str:
                    file_path = Path(file_path_str)
                    
                    # Step 2: Delete the physical file from the garderobe folder if it exists
                    if file_path.exists():
                        os.remove(file_path)
                        print(f"🗑️ Deleted local file: {file_path}")
                    else:
                        print(f"⚠️ Warning: Physical file {file_path} was already missing from disk.")
            
            # Step 3: Remove the item row from the database table
            cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
            conn.commit()
            print(f"✅ Successfully deleted item ID {item_id} from the database.")
            
    except Exception as e:
        print(f"❌ Error during item deletion workflow: {e}")
        raise e