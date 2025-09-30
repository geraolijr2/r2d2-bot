# r2d2/supabase_store.py
import os, time
from typing import Dict, Any, Optional
from supabase import create_client, Client
from r2d2.utils.logger import get_logger

log = get_logger("supabase")

class SupabaseStore:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY"))
        if not url or not key:
            log.warning("Supabase desativado (sem URL/KEY).")
            self.enabled = False
            self.client = None
        else:
            self.client: Client = create_client(url, key)
            self.enabled = True
            log.info("Supabase conectado.")

    def insert_backtest(self, data: Dict[str, Any]) -> Optional[str]:
        if not self.enabled:
            return None
        try:
            res = self.client.table("backtests").insert(data).execute()
            return res.data[0]["id"]
        except Exception as e:
            log.error(f"Erro ao salvar backtest: {e}")
            return None

    def insert_trades(self, trades: list[Dict[str, Any]]):
        if not self.enabled or not trades:
            return
        try:
            self.client.table("backtest_trades").insert(trades).execute()
        except Exception as e:
            log.error(f"Erro ao salvar trades: {e}")

    def log_event(self, event: str, data: Dict[str, Any]):
        if not self.enabled: return
        try:
            self.client.table("r2d2_events").insert({
                "ts": int(time.time() * 1000),
                "event": event,
                "data": data
            }).execute()
        except Exception as e:
            log.error(f"Erro ao salvar evento: {e}")

    def log_order(self, order: Dict[str, Any]):
        if not self.enabled: return
        try:
            self.client.table("r2d2_orders").insert({
                "ts": int(time.time() * 1000),
                "raw": order
            }).execute()
        except Exception as e:
            log.error(f"Erro ao salvar ordem: {e}")

    def log_snapshot(self, snapshot: Dict[str, Any]):
        if not self.enabled: return
        try:
            self.client.table("r2d2_snapshots").insert({
                "ts": int(time.time() * 1000),
                "snapshot": snapshot
            }).execute()
        except Exception as e:
            log.error(f"Erro ao salvar snapshot: {e}")
