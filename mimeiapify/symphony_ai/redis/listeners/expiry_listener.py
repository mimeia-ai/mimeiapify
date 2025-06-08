"""
Redis **key-expiry listener** – subscribe to "__keyevent@<db>__:expired"
and dispatch handlers from `expiration_registry`.

Schedule *once* per worker:

    asyncio.create_task(
        run_listener(alias="expiry"),  # defaults to db of that alias
        name="redis-expiry-listener"
    )
"""

from __future__ import annotations
import asyncio, logging
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as SyncConnectionError, ResponseError
from redis.asyncio.connection import ConnectionError as AsyncConnectionError

from mimeiapify.symphony_ai.redis.redis_client import RedisClient
from mimeiapify.symphony_ai.redis.redis_handler.utils.key_factory import KeyFactory
from .handler_registry import expiration_registry

logger = logging.getLogger("Redis Expiry Listener")


async def _ensure_server_side_notifications(r: Redis) -> None:
    """
    Make sure `notify-keyspace-events` contains 'Ex'.
    Applied **once per Redis server**, not per DB.
    """
    try:
        cfg = await r.config_get("notify-keyspace-events")
        flags: str = cfg.get("notify-keyspace-events", "")
        if "E" not in flags or "x" not in flags:
            await r.config_set("notify-keyspace-events", flags + "Ex")
            logger.info("Enabled 'Ex' keyspace notifications on Redis server")
    except ResponseError:
        logger.warning("Missing CONFIG SET permission; "
                       "ensure 'notify-keyspace-events Ex' is set manually")


async def run_listener(
    *,
    alias: str = "expiry",           # which RedisClient pool alias to use
    reconnect_delay: int = 10,
    key_factory: KeyFactory | None = None  # KeyFactory instance to use
) -> None:
    """
    Long-running coroutine – **do not await directly**,
    instead schedule with `asyncio.create_task`.

    Args
    ----
    alias : str
        Pool alias configured in `GlobalSymphonyConfig.redis_url`.
    reconnect_delay : int
        Seconds to wait before reconnecting after an error.
    key_factory : KeyFactory | None
        KeyFactory instance to use for key parsing. Defaults to new instance.
    """
    keys = key_factory or KeyFactory()
    
    # Get client for this alias → determines DB
    redis = await RedisClient.get(alias)
    # Extract DB index from connection
    db_index = redis.connection_pool.connection_kwargs.get("db", 0)
    channel = f"__keyevent@{db_index}__:expired"
    logger.info("Expiry listener on alias '%s' (db=%s) channel=%s",
                alias, db_index, channel)

    while True:  # reconnect / restart loop
        pubsub = None
        try:
            await _ensure_server_side_notifications(redis)

            pubsub = redis.pubsub(ignore_subscribe_messages=True)
            await pubsub.subscribe(channel)
            logger.info("Subscribed to %s", channel)

            async for msg in pubsub.listen():
                if msg is None or msg.get("type") != "message":
                    continue

                expired_key: str = msg["data"]
                
                # Use KeyFactory to parse the trigger key
                parsed = keys.parse_trigger(expired_key)
                if not parsed:
                    continue  # not a trigger key
                    
                tenant, action, identifier = parsed
                
                # Build the prefix for registry lookup
                prefix = f"{keys.trigger_prefix}:{action}:"
                handler = expiration_registry.handlers.get(prefix)
                if not handler:
                    logger.debug("No handler registered for prefix '%s'", prefix)
                    continue
                
                # Dispatch the handler
                asyncio.create_task(
                    handler(identifier, expired_key),
                    name=f"{handler.__name__}:{identifier}"
                )
                logger.debug("Dispatched %s for %s (tenant=%s, action=%s)", 
                           handler.__name__, identifier, tenant, action)

        except (AsyncConnectionError, SyncConnectionError) as exc:
            logger.warning("Redis connection error: %s – retry in %ss",
                           exc, reconnect_delay)
        except asyncio.CancelledError:
            logger.info("Expiry listener cancelled – shutting down")
            break
        except Exception as exc:                           # pragma: no cover
            logger.exception("Unexpected listener error: %s", exc)
        finally:
            if pubsub:
                try:
                    await pubsub.close()
                except Exception:
                    pass
        await asyncio.sleep(reconnect_delay) 