# Madame Garderobe - AI Wardrobe Assistant

Catalog your wardrobe and get outfit recommendations.

## Set-up

1. Take photos of your wardrobe and remove the background (press and hold image on iphone) and email them to your gmail with the subject line being the name of your wardrobe item.
2. Set-up Google cloud project with OAuth2 to enable read-only scraping of the images from your gmail (https://console.cloud.google.com/). Save secret key to credentials.json in the week_06_madame_garderobe directory. 
3. Install uv (https://docs.astral.sh/uv/getting-started/installation/)
4. Get API key from Google AI Studio (https://aistudio.google.com/). Save the API key in a .env file in the week_06_madame_garderobe directory: GOOGLE_API_KEY=[your copied key]

## Run 

Set-up the python project
```powershell
uv sync
```
Scrape the images from your email - this looks images sent to yourself in the last 36 hours.
If this is your first time running, there may be some additional steps that pop-up for the Oauth2 verification.
```powershell
uv run image_scraper.py
```

Catalog the images in garderobe.db
An LLM is used to tag and write descriptions here. The free tier throttled me at 20 requests per day, so I had to load my items over multiple days.
```powershell
uv run --env-file .env python garderobe_db.py
```

Run the app and plan your outfit
```powershell
uv run --env-file .env streamlit run app.py
```


