from __future__ import annotations
from pydantic import BaseModel, Field
import logging
from typing import Optional

logger = logging.getLogger("RedisKeyFactory")


class KeyFactory(BaseModel):
    """Pure stateless helpers that know **nothing** about Redis calls."""
    user_prefix: str = Field(default="user")
    handler_prefix: str = Field(default="state")
    table_prefix: str = Field(default="df")
    trigger_prefix: str = Field(default="EXPTRIGGER")  # Uppercase for consistency with listener
    batch_list_prefix: str = Field(default="batch")
    pending_set_prefix: str = Field(default="pending_batches")
    shared_state_prefix: str = Field(default="SS")
    pk_marker: str = Field(default="pkid")

    # ---- builders ---------------------------------------------------------
    def user(self, tenant: str, user_id: str) -> str:
        return f"{tenant}:{self.user_prefix}:{user_id}"

    def handler(self, tenant: str, name: str, user_id: str) -> str:
        return f"{tenant}:{self.handler_prefix}:{name}:{user_id}"

    def table(self, tenant: str, table: str, pkid: str) -> str:
        safe_tbl = table.replace(":", "_")
        safe_pk = pkid.replace(":", "_")
        return f"{tenant}:{self.table_prefix}:{safe_tbl}:{self.pk_marker}:{safe_pk}"

    def trigger(self, tenant: str, action: str, ident: str) -> str:
        a = action.replace(":", "_"); i = ident.replace(":", "_")
        return f"{tenant}:{self.trigger_prefix}:{a}:{i}"

    def shared_state(self, tenant: str, state_name: str, user_id: str) -> str:
        safe_state = state_name.replace(":", "_")
        safe_user = user_id.replace(":", "_")
        return f"{tenant}:{self.shared_state_prefix}:{safe_state}:{safe_user}"

    def batch_list(self, tenant: str, svc: str, entity: str, action: str) -> str:
        return f"{tenant}:{self.batch_list_prefix}:{svc}:{entity}:{action}"

    def pending_set(self, svc: str) -> str:
        return f"{self.pending_set_prefix}:{svc}"

    # ---- parsers -----------------------------------------------------------
    def parse_trigger(self, key: str) -> Optional[tuple[str, str, str]]:
        """
        Parse a trigger key back into its components.
        
        Args:
            key: Redis key like "tenant:EXPTRIGGER:action:identifier"
            
        Returns:
            (tenant, action, identifier) or None if not a trigger key
        """
        if f":{self.trigger_prefix}:" not in key:
            return None
            
        try:
            parts = key.split(":", 3)  # Split into max 4 parts: tenant, EXPTRIGGER, action, identifier
            if len(parts) != 4 or parts[1] != self.trigger_prefix:
                return None
            tenant, _, action, identifier = parts
            return tenant, action, identifier
        except (ValueError, IndexError):
            return None

    def is_trigger_key(self, key: str) -> bool:
        """Check if a key is a trigger key."""
        return f":{self.trigger_prefix}:" in key


# Default instance for global use
default_key_factory = KeyFactory()
