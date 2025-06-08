"""
Integration test demonstrating the complete TTL-driven workflow.

This test shows how the three components work together:
1. RedisTrigger schedules deferred work
2. ExpirationHandlerRegistry maps actions to handlers  
3. run_expiry_listener dispatches handlers when keys expire

Run with: uv run mimeiapify/symphony_ai/redis/listeners/test_integration.py
"""

import asyncio
import logging

# Configure logging for testing
logging.basicConfig(level=logging.DEBUG)

# Mock GlobalSymphony for testing
class MockGlobalSymphony:
    def __init__(self):
        self.loop = asyncio.get_event_loop()

# Setup test handlers BEFORE importing the system
test_results = {}

def setup_test_handlers():
    """Register test handlers before starting the system"""
    from mimeiapify.symphony_ai.redis.listeners import expiration_registry
    
    @expiration_registry.on_expire_action("test_batch_processing")
    async def handle_test_batch(identifier: str, full_key: str):
        tenant = full_key.split(":", 1)[0]
        test_results[f"batch_{identifier}"] = {
            "tenant": tenant,
            "identifier": identifier,
            "full_key": full_key,
            "action": "test_batch_processing"
        }
        print(f"✅ Batch handler executed for {identifier}")

    @expiration_registry.on_expire_action("test_reminder")
    async def handle_test_reminder(user_id: str, full_key: str):
        tenant = full_key.split(":", 1)[0]
        test_results[f"reminder_{user_id}"] = {
            "tenant": tenant,
            "identifier": user_id,
            "full_key": full_key,
            "action": "test_reminder"
        }
        print(f"✅ Reminder handler executed for {user_id}")


async def test_complete_workflow():
    """Test the complete TTL-driven workflow end-to-end"""
    
    # This test would require a real Redis instance
    # For now, it demonstrates the intended usage pattern
    
    print("🔧 Setting up test handlers...")
    setup_test_handlers()
    
    print("📝 This test demonstrates the complete workflow:")
    print("1. Register handlers with @expiration_registry.on_expire_action")
    print("2. Start the expiry listener with run_expiry_listener()")
    print("3. Schedule deferred work with RedisTrigger.set()")
    print("4. Handlers execute automatically when TTL expires")
    
    # Mock the workflow components
    print("\n🏗️ Workflow Components:")
    print("├── ExpirationHandlerRegistry: ✅ Handlers registered")
    print("├── run_expiry_listener: 🔄 Would start background task")
    print("└── RedisTrigger: 📅 Would schedule TTL keys")
    
    print("\n🎯 Expected Flow:")
    print("1. RedisTrigger.set('test_batch_processing', 'wa_123', ttl=5)")
    print("2. Redis key: tenant:EXPTRIGGER:test_batch_processing:wa_123")
    print("3. After 5 seconds: Redis publishes expiry event")
    print("4. Listener receives: __keyevent@8__:expired")
    print("5. Parsed: tenant='test', action='test_batch_processing', id='wa_123'")
    print("6. Handler: handle_test_batch('wa_123', full_key)")
    
    # Simulate handler execution
    print("\n🧪 Simulating handler execution...")
    await asyncio.sleep(0.1)  # Small delay for realism
    
    # Manually trigger handlers to show they work
    from mimeiapify.symphony_ai.redis.listeners.handler_registry import expiration_registry
    from mimeiapify.symphony_ai.redis.redis_handler.utils.key_factory import KeyFactory
    
    # Create KeyFactory instance (following Factory pattern)
    keys = KeyFactory()
    
    # Test the registry resolution
    test_key = "test_tenant:EXPTRIGGER:test_batch_processing:wa_123"
    
    # Simulate KeyFactory parsing
    if ":EXPTRIGGER:" in test_key:
        parts = test_key.split(":", 3)
        if len(parts) == 4:
            tenant, _, action, identifier = parts
            parsed = (tenant, action, identifier)
    
    # Better: use the actual KeyFactory parsing
    parsed = keys.parse_trigger(test_key)
    
    if parsed:
        tenant, action, identifier = parsed
        prefix = f"{keys.trigger_prefix}:{action}:"
        handler = expiration_registry._handlers.get(prefix)
        
        if handler:
            print(f"✅ Found handler for prefix: {prefix}")
            await handler(identifier, test_key)
        else:
            print(f"❌ No handler found for prefix: {prefix}")
    
    print(f"\n📊 Test Results: {test_results}")
    
    assert len(test_results) > 0, "At least one handler should have executed"
    assert "batch_wa_123" in test_results, "Batch handler should have executed"
    
    batch_result = test_results["batch_wa_123"]
    assert batch_result["tenant"] == "test_tenant"
    assert batch_result["identifier"] == "wa_123"
    assert batch_result["action"] == "test_batch_processing"
    
    print("✅ Integration test completed successfully!")


def test_key_factory_integration():
    """Test KeyFactory integration with the trigger system"""
    from mimeiapify.symphony_ai.redis.redis_handler.utils.key_factory import KeyFactory
    
    # Create KeyFactory instance (following Factory pattern)
    keys = KeyFactory()
    
    # Test trigger key building
    key = keys.trigger("test_tenant", "process_batch", "wa_123")
    expected = "test_tenant:EXPTRIGGER:process_batch:wa_123"
    assert key == expected, f"Expected {expected}, got {key}"
    
    # Test key parsing
    parsed = keys.parse_trigger(key)
    assert parsed is not None, "Should parse valid trigger key"
    
    tenant, action, identifier = parsed
    assert tenant == "test_tenant"
    assert action == "process_batch"
    assert identifier == "wa_123"
    
    # Test non-trigger key
    non_trigger = "test_tenant:user:user123"
    parsed_non = keys.parse_trigger(non_trigger)
    assert parsed_non is None, "Should not parse non-trigger key"
    
    # Test prefix constant
    assert keys.trigger_prefix == "EXPTRIGGER", f"Expected EXPTRIGGER, got {keys.trigger_prefix}"
    
    print("✅ KeyFactory integration test passed!")


def test_registry_functionality():
    """Test the expiration handler registry"""
    from mimeiapify.symphony_ai.redis.listeners.handler_registry import ExpirationHandlerRegistry
    from mimeiapify.symphony_ai.redis.redis_handler.utils.key_factory import KeyFactory
    
    # Create instances following Factory pattern
    keys = KeyFactory()
    registry = ExpirationHandlerRegistry()
    
    # Test handler registration
    @registry.on_expire_action("test_action")
    async def test_handler(identifier: str, full_key: str):
        return f"handled_{identifier}"
    
    # Check handler was registered
    expected_prefix = "EXPTRIGGER:test_action:"
    assert expected_prefix in registry._handlers
    registered_handler = registry._handlers[expected_prefix]
    assert callable(registered_handler), "Registered handler should be callable"
    
    print(f"🔍 Registered handlers: {list(registry._handlers.keys())}")
    
    # Test the actual flow used by the listener
    test_key = "tenant:EXPTRIGGER:test_action:item123"
    print(f"🔍 Testing key: {test_key}")
    
    # 1. Parse with KeyFactory (like the listener does)
    parsed = keys.parse_trigger(test_key)
    assert parsed is not None, f"KeyFactory should parse {test_key}"
    
    tenant, action, identifier = parsed
    print(f"🔍 Parsed: tenant={tenant}, action={action}, identifier={identifier}")
    
    # 2. Build prefix and lookup handler (like the listener does)
    prefix = f"{keys.trigger_prefix}:{action}:"
    handler = registry._handlers.get(prefix)
    print(f"🔍 Looking up prefix: {prefix}")
    print(f"🔍 Found handler: {handler is not None}")
    
    assert handler is not None, f"Should find handler for prefix {prefix}"
    assert callable(handler), "Found handler should be callable"
    assert identifier == "item123"
    
    print("✅ Registry functionality test passed!")


if __name__ == "__main__":
    print("🧪 Running Redis Listeners Integration Tests")
    print("=" * 50)
    
    # Run synchronous tests
    test_key_factory_integration()
    test_registry_functionality()
    
    # Run async test
    asyncio.run(test_complete_workflow())
    
    print("\n🎉 All tests completed!")
    print("\n📖 Next Steps:")
    print("1. Configure Redis with notify-keyspace-events Ex")
    print("2. Add your business logic handlers")
    print("3. Start run_expiry_listener() in your FastAPI lifespan")
    print("4. Use RedisTrigger.set() to schedule deferred work") 