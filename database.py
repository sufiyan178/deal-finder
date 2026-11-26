import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load variables from .env file
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print("Checking environment variables...")
print(f"URL: {SUPABASE_URL}")
print(f"Key loaded: {'Yes' if SUPABASE_KEY else 'No'}")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Test query to check connection
try:
    response = supabase.table("products").select("*").limit(1).execute()
    print("Successfully connected to Supabase database!")
    print("Query response:", response)
except Exception as e:
    print("Connection error:", e)
    