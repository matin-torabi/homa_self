import os
from supabase import create_client, Client
from dotenv import load_dotenv


API_ID = 39895969     
API_HASH = "0bb4503a1c1bcdf74b01bd8fa4580d75" 
SESSION_NAME="my_selfbot"

BOT_TOKEN = "8978251563:AAGfmEIQXTbDihh3KyBn0vGx349A3YDX9VQ" 
PANEL_BOT_TOKEN = "8897179845:AAFrHmB7XdTKfy592fEO-A6Gr13nXsHaPs8"
BOT_USERNAME = "Homa_panel_dev_bot"

CHANNELS = [
    {'id': "@Homa_self_Ch", 'url': "https://t.me/Homa_self_Ch"},
    {'id': "@Homa_self_Gp", 'url': "https://t.me/Homa_self_Gp"},
]

SESSIONS_FILE = "sessions.json"

# supabase configuration
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
