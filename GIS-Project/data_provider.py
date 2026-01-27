from __future__ import annotations
from typing import Protocol, Any, Dict, List

import os
from config import AI_READY

class DataProvider(Protocol):
    def get_config(self) -> Dict[str, Any]: ...
    def get_current_snapshot(self) -> Dict[str, Any]: ...
    def get_map_features(self) -> Dict[str, Any]: ...
    def get_forecast(self) -> Dict[str, Any]: ...
    def get_history(self, range_q: str) -> Dict[str, Any]: ...
    def get_demo_raw_logs(self, limit: int) -> List[Dict[str, Any]]: ...
    def get_demo_validation(self, limit: int) -> List[Dict[str, Any]]: ...

def get_provider() -> DataProvider:
    """Select the active provider.

    Phase 5 default: **Supabase-first** (production-like).
    - If Supabase tables are empty, the UI still works (returns graceful placeholders).
    - You can still enable the old mock provider for offline UI work by setting:
        ALLOW_MOCK=true
    """
    allow_mock = os.getenv("ALLOW_MOCK", "false").lower() in ("1", "true", "yes")
    if allow_mock:
        from providers.mock_provider import MockProvider
        return MockProvider()

    from providers.supabase_provider import SupabaseProvider
    return SupabaseProvider(ai_ready=AI_READY)
