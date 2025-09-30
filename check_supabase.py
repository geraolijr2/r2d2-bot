# check_supabase.py
import os
from dotenv import load_dotenv
from supabase import create_client

# carregar variáveis do .env
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY"))

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("⚠️ Variáveis SUPABASE_URL e SUPABASE_KEY não foram carregadas do .env")

client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("🔎 Gravando evento de teste...")
resp = client.table("r2d2_events").insert({
    "ts": 1234567890,
    "event": "test",
    "data": {"msg": "Olá Supabase!"}
}).execute()
print("Insert:", resp)

print("🔎 Lendo eventos...")
rows = client.table("r2d2_events").select("*").order("id", desc=True).limit(5).execute()
for row in rows.data:
    print(row)