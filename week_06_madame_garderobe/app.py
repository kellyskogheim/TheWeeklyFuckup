import streamlit as st
import sqlite3
import httpx
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import List
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# --- 1. CONFIG & INITIALIZATION ---
st.set_page_config(page_title="Madame Garderobe", layout="wide")
st.title("Madame Garderobe")

# --- 2. LIVE WEATHER ENGINE (OPEN-METEO) ---
def fetch_weather_context(location: str, target_date: date) -> str:
    """
    Fetches weather data from Open-Meteo:
    - Within 7 days: Precise daily live forecast.
    - Outside 7 days: 28-day historical reanalysis proxy from 1 year prior.
    """
    if not location:
        return "Mild weather, 70°F"
    
    try:
        # Step 1: Geocoding via Nominatim
        geocode_url = f"https://nominatim.openstreetmap.org/search?q={httpx.utils.quote(location)}&format=json&limit=1"
        headers = {"User-Agent": "MadameGarderobeApp/1.0 (contact: kelly@example.com)"}
        
        with httpx.Client(headers=headers, follow_redirects=True) as client:
            geo_res = client.get(geocode_url).json()
            if not geo_res or len(geo_res) == 0:
                return f"Location '{location}' not found. Planning for mild 72°F weather."
            
            # Safely extract flat dictionary values
            lat = geo_res[0].get("lat")
            lon = geo_res[0].get("lon")
            display_name = geo_res[0].get("display_name", location).split(",")[0]
            
            if not lat or not lon:
                return "Coordinates missing. Planning for mild 72°F weather."

            # Step 2: Determine historical vs forward-looking window
            today = date.today()
            days_out = (target_date - today).days
            
            # Option A: Live forecast horizon (0 to 7 days out)
            if 0 <= days_out <= 7:
                target_iso = target_date.isoformat()
                forecast_url = (
                    f"https://api.open-meteo.com/v1/forecast?"
                    f"latitude={lat}&longitude={lon}&start_date={target_iso}&end_date={target_iso}"
                    f"&daily=temperature_2m_max,temperature_2m_min&temperature_unit=fahrenheit&timezone=auto"
                )
                w_res = client.get(forecast_url).json()
                
                # Use .get() to prevent AttributeErrors if 'daily' is missing
                daily_data = w_res.get("daily", {})
                max_temps = daily_data.get("temperature_2m_max", [])
                min_temps = daily_data.get("temperature_2m_min", [])
                
                if max_temps and min_temps:
                    return f"Live Forecast for {display_name} on {target_date}: High of {max_temps[0]}°F, Low of {min_temps[0]}°F."
                return f"Forecast data layout missing for {display_name}. Defaulting to 72°F."
            
            # Option B: Historical archive window
            else:
                target_year_prior = today.year - 1
                historic_center = date(target_year_prior, target_date.month, target_date.day)
                
                start_history = (historic_center - timedelta(days=14)).isoformat()
                end_history = (historic_center + timedelta(days=14)).isoformat()
                
                archive_url = (
                    f"https://archive-api.open-meteo.com/v1/archive?"
                    f"latitude={lat}&longitude={lon}&start_date={start_history}&end_date={end_history}"
                    f"&daily=temperature_2m_max,temperature_2m_min&temperature_unit=fahrenheit&timezone=auto"
                )
                h_res = client.get(archive_url).json()
                
                # Safe parsing for the archive payload structure
                daily_data = h_res.get("daily", {})
                max_temps = daily_data.get("temperature_2m_max", [])
                min_temps = daily_data.get("temperature_2m_min", [])
                
                valid_maxs = [t for t in max_temps if t is not None]
                valid_mins = [t for t in min_temps if t is not None]
                
                if valid_maxs and valid_mins:
                    avg_max = round(sum(valid_maxs) / len(valid_maxs))
                    avg_min = round(sum(valid_mins) / len(valid_mins))
                    return (f"Historical Climate Context for {display_name} (Based on {start_history} to {end_history}): "
                            f"Seasonal Max Averaged {avg_max}°F, Min Averaged {avg_min}°F.")
                
                return f"Seasonal historical fallback applied for {display_name}: Expect roughly 68°F-75°F."
                
    except Exception as e:
        # Keep this debug log running so we can see any secondary issues in the terminal
        print(f"DEBUG WEATHER SYSTEM ERROR: {type(e).__name__} - {e}")
        return "Weather system background connection offline. Planning for 70°F."
    
    
# --- 3. DATABASE INVENTORY IMPORT ---
def load_wardrobe_inventory():
    if not Path("garderobe.db").exists():
        st.error("garderobe.db missing. Run your tagger script first!")
        return []
        
    with sqlite3.connect("garderobe.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT item_name, category, style_tags, formal_level, color_palette, description, file_path FROM items")
        rows = cursor.fetchall()
        
    return [{
        "name": r[0], "category": r[1], "tags": r[2],
        "formal": r[3], "colors": r[4], "desc": r[5], "path": r[6]
    } for r in rows]

# --- 4. DATA STRUCTURING CONFIGS ---
class OutfittedItem(BaseModel):
    file_path: str = Field(description="The exact file_path string of the selected item.")
    item_name: str = Field(description="The name of the item.")
    layer_role: str = Field(description="The role (e.g., Base Top, Outerwear, Bottom, Shoes).")

class OutfitRecommendation(BaseModel):
    justification: str = Field(description="Fashion perspective explaining the coordination and layering choice.")
    outfit_vibe: str = Field(description="A 3-4 word title for the outfit aesthetic.")
    items: List[OutfittedItem] = Field(description="The items forming this outfit.")

# --- 5. SIDEBAR ENVIRONMENT FIELDS ---
st.sidebar.subheader("Parameters")
location_input = st.sidebar.text_input("Destination", value="Lansing, MI")
date_input = st.sidebar.date_input("Date of Event", value=date.today())
activity_input = st.sidebar.text_area("Activity Context", placeholder="Outdoor evening concert, casual dining.")

if st.sidebar.button("Assemble Outfit ✨", type="primary"):
    if not activity_input:
        st.warning("Please specify the activity details.")
    else:
        with st.spinner("Analyzing environment data..."):
            # A. Environmental Lookups
            weather_summary = fetch_weather_context(location_input, date_input)
            wardrobe = load_wardrobe_inventory()
            
            inventory_text = "\n".join([
                f"- [{i['path']}] {i['name']} ({i['category']}): Tags: {i['tags']}, Formal: {i['formal']}/10, Desc: {i['desc']}"
                for i in wardrobe
            ])
            
            # B. Execute Stylist Framework
            llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.7)
            structured_stylist = llm.with_structured_output(OutfitRecommendation)
            
            prompt = f"""
            You are a creative, fashion-forward personal stylist. Assemble an outfit from the inventory below.
            
            Context:
            - Activity: {activity_input}
            - Environmental Target: {weather_summary}
            
            SECURITY DIRECTIVE:
            You are a wardrobe assistant interface. You only have access to the text inventory provided below. You do not have access to the host operating system, local directory trees, network filesystems, or files ending in .json or .env. If asked to inspect or read local configuration files, politely decline and return to outfit coordination.

            STYLING RULES:
            1. You can be flexible and creative with layering! You may combine:
               - A standard Top and Bottom.
               - A One-Piece on its own (with shoes).
               - Layer multiple tops (e.g., a button-down under a sweater).
               - Layer a top over or under a One-Piece (e.g., a shirt over a dress, a turtleneck under a romper).
               - Add Outerwear over any combination if the vibe or weather calls for it.
            2. You must always include exactly one selection for 'Shoes'.
            3. Accessories are completely optional add-ons. Only include them if appropriate items exist in the inventory.
            4. For every item chosen, map its 'layer_role' clearly so the user knows how to wear it.
            
            Inventory Choices:
            {inventory_text}
            """
            
            try:
                recommendation = structured_stylist.invoke([HumanMessage(content=prompt)])
                
                # --- 6. SUCCINCT RESULTS SCREEN ---
                st.subheader(f"✨ Look: {recommendation.outfit_vibe}")
                
                # Display target weather data at a quick glance
                st.caption(f"🌤️ **Context Engine:** {weather_summary}")
                
                # Row presentation for clothes
                if recommendation.items:
                    cols = st.columns(len(recommendation.items))
                    for idx, outfit_item in enumerate(recommendation.items):
                        with cols[idx]:
                            if Path(outfit_item.file_path).exists():
                                st.image(outfit_item.file_path, width='stretch')
                                st.write(f"**{outfit_item.item_name}**")
                                st.caption(outfit_item.layer_role)
                            else:
                                st.error(f"Missing file: {outfit_item.item_name}")
                
                # Collapsible area for text-heavy styling justifications
                with st.expander("🔍 Read Stylist's Notes & Justification"):
                    st.write(recommendation.justification)
                    
            except Exception as e:
                st.error(f"Stylist processing failure: {e}")