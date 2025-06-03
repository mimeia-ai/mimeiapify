from __future__ import annotations
import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel
import logging

logger = logging.getLogger("RedisSerde")


def _convert_bools_to_redis(obj: Any) -> Any:
    """Recursively convert boolean values to Redis-optimized "1"/"0" strings"""
    if isinstance(obj, bool):
        return "1" if obj else "0"
    elif isinstance(obj, dict):
        return {k: _convert_bools_to_redis(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_bools_to_redis(item) for item in obj]
    else:
        return obj


def _convert_redis_to_bools(obj: Any) -> Any:
    """Recursively convert Redis "1"/"0" strings back to boolean values"""
    if obj == "1":
        return True
    elif obj == "0":
        return False
    elif isinstance(obj, dict):
        return {k: _convert_redis_to_bools(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_redis_to_bools(item) for item in obj]
    else:
        return obj


def dumps(obj: Any) -> str:
    """Serialize Python object to Redis-compatible string"""
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return str(int(obj))
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, str):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return str(obj.value)
    if isinstance(obj, BaseModel):
        # Convert to dict first, then convert bools to "1"/"0", then to JSON
        model_dict = obj.model_dump()
        redis_dict = _convert_bools_to_redis(model_dict)
        return json.dumps(redis_dict, ensure_ascii=False)
    try:
        return json.dumps(obj, ensure_ascii=False)
    except TypeError as e:
        logger.warning(f"Could not JSON serialize value of type {type(obj)}. Falling back to str(). Error: {e}. Value: {obj!r}")
        return str(obj)


def loads(raw: Optional[str], model: Optional[type[BaseModel]] = None) -> Any:
    """Deserialize Redis string back to Python object"""
    if raw in (None, "null"):
        return None
    if raw == "1":
        return True
    if raw == "0":
        return False
    try:
        data = json.loads(raw)
        if model is not None:
            # Convert Redis "1"/"0" back to bools before BaseModel validation
            bool_converted_data = _convert_redis_to_bools(data)
            return model.model_validate(bool_converted_data)
        return data
    except (json.JSONDecodeError, TypeError):
        return raw


def dumps_hash(data: Dict[str, Any]) -> Dict[str, str]:
    """Serialize dictionary values for Redis hash storage"""
    return {field: dumps(value) for field, value in data.items()}


def loads_hash(raw_data: Optional[Dict[str, str]], models: Optional[Dict[str, type[BaseModel]]] = None) -> Dict[str, Any]:
    """
    Deserialize Redis hash back to Python dictionary
    
    Args:
        raw_data: Raw string data from Redis hash
        models: Optional mapping of field names to BaseModel classes for typed deserialization
                e.g., {"user_profile": UserProfile, "settings": UserSettings}
    """
    if not raw_data:
        return {}
    
    if models:
        result = {}
        for field, value_str in raw_data.items():
            model_class = models.get(field)
            result[field] = loads(value_str, model=model_class)
        return result
    else:
        return {field: loads(value_str) for field, value_str in raw_data.items()}