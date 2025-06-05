from mimeiapify.symphony_ai.redis.redis_handler.serde import dumps, loads
from pydantic import BaseModel

class User(BaseModel):
    name: str
    active: bool
    score: int
    features: list[bool] = [True, False, True]

# Test serialization
user = User(name='Alice', active=True, score=100)
serialized = dumps(user)
print('✅ Serialized:', serialized)

# Test deserialization  
deserialized = loads(serialized, model=User)
print('✅ Deserialized:', deserialized)
print('✅ Boolean type preserved:', type(deserialized.active), deserialized.active)
print('✅ List booleans preserved:', deserialized.features, [type(f) for f in deserialized.features])

# Test that Redis sees "1"/"0" strings, not JSON true/false
import json
parsed = json.loads(serialized)
print('✅ Redis storage format:', parsed)
print('✅ Boolean stored as string:', type(parsed['active']), parsed['active'])
print('✅ List booleans as strings:', parsed['features'], [type(f) for f in parsed['features']]) 