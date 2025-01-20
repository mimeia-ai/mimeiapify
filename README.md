"""
# SNCL - Sasha Nicolai's Library (Version 1.0.2, 2025-01-20)

SNCL is a Python library designed to host several API integrations and utility functions. Currently, it provides support for Airtable API interactions, with plans to expand to other APIs in the future.

---

## Current APIs

### Airtable
The library currently supports operations for Airtable API. For detailed documentation on the Airtable API itself, visit: [Airtable API Documentation](https://airtable.com/developers/web/api/introduction).

Supported Airtable operations include:
- Fetching base schemas
- Extracting table IDs
- Creating fields in Airtable tables
- Fetching and filtering records
- Creating, updating, and deleting records
- Uploading attachments to Airtable fields
- Managing Airtable fields and configurations

The library provides two interfaces:
- **Airtable**: A synchronous interface for Airtable API interactions.
- **AirtableAsync**: An asynchronous interface for Airtable API interactions.

## Future Plans

- Add integrations for additional APIs (Notion, WhatsApp, Gmail).
- Expand utility functions for data processing and manipulation.
- Provide improved error handling and logging for all operations.

---

## Installation

### Pip Install
```bash
pip install sncl
```

This will make the library available for use across your projects.

---

## Usage (Synchronous)

To start using the `sncl` library in synchronous code, import the `Airtable` class:

```python
from sncl import Airtable

# Initialize
airtable = Airtable(base_id="your_base_id", api_key="your_api_key")

# Fetch Schema
schema = airtable.get_schema()
print(schema)
```

---

## Usage (Asynchronous)

To use the async interface, import the `AirtableAsync` class:

```python
from sncl.airtable_async import AirtableAsync
import asyncio

async def main():
    # Initialize
    airtable_async = AirtableAsync(base_id="your_base_id", api_key="your_api_key")

    # Example: Fetch schema asynchronously
    schema = await airtable_async.get_schema()
    print(schema)

# Run the async entry point
asyncio.run(main())
```

---

## Example with FastAPI

Below is a minimal FastAPI example demonstrating how to integrate `AirtableAsync`:

```python
from fastapi import FastAPI
from sncl.airtable_async import AirtableAsync

app = FastAPI()

@app.get("/records")
async def get_records():
    airtable_async = AirtableAsync(base_id="your_base_id", api_key="your_api_key")
    records = await airtable_async.fetch_records(table_id="your_table_id")
    return {"records": records}
```

### Using concurrency in FastAPI

Within FastAPI, calling multiple Airtable operations in parallel is as simple as using `asyncio.gather`. For instance:

```python
@app.get("/parallel")
async def parallel_requests():
    airtable_async = AirtableAsync(base_id="your_base_id", api_key="your_api_key")

    # Suppose you want to fetch records from two different tables concurrently:
    task1 = airtable_async.fetch_records(table_id="Table1")
    task2 = airtable_async.fetch_records(table_id="Table2")

    results = await asyncio.gather(task1, task2)
    return {"table1": results[0], "table2": results[1]}
```

### Class Manager pattern (reusing the ClientSession)

If you prefer to manage the `AirtableAsync` instance yourself (for example, to reuse the underlying HTTP session), you might do:

```python
class AirtableManager:
    def __init__(self, base_id: str, api_key: str):
        self.airtable = AirtableAsync(base_id, api_key)

    async def fetch_two_tables(self):
        table1, table2 = await asyncio.gather(
            self.airtable.fetch_records("Table1"),
            self.airtable.fetch_records("Table2")
        )
        return table1, table2

@app.get("/manager-example")
async def manager_example():
    manager = AirtableManager(base_id="your_base_id", api_key="your_api_key")
    table1, table2 = await manager.fetch_two_tables()
    return {"table1": table1, "table2": table2}
```
#### The Goal
The purpose of the Class Manager pattern is to encapsulate the setup of your AirtableAsync client (or any other resource) into a single Python class. This lets you:
1. Reuse the same instance of AirtableAsync across multiple methods or endpoints.
2. Potentially reuse the underlying HTTP session (if you modify AirtableAsync to store a single session, rather than creating it anew in each call).
3. Keep related Airtable logic in one place, making your codebase more organized and testable.

#### Example Code

```python
import asyncio
Edit
import asyncio
from fastapi import FastAPI
from sncl.airtable_async import AirtableAsync

# 1) Create a Manager class that holds a single AirtableAsync instance
class AirtableManager:
    def __init__(self, base_id: str, api_key: str):
        # Here we initialize exactly one AirtableAsync client
        self.airtable = AirtableAsync(base_id, api_key)

    async def fetch_two_tables(self):
        """
        Example method that fetches data from two separate tables in parallel (asynchronously).
        """
        # asyncio.gather will run these two coroutines concurrently
        table1, table2 = await asyncio.gather(
            self.airtable.fetch_records("Table1"),
            self.airtable.fetch_records("Table2")
        )
        return table1, table2

# 2) Create a FastAPI app
app = FastAPI()

@app.get("/manager-example")
async def manager_example():
    """
    Example FastAPI endpoint that uses the AirtableManager to fetch data from two tables.
    """
    # Instantiate the manager (in real code, you might do this once at startup)
    manager = AirtableManager(base_id="your_base_id", api_key="your_api_key")
    
    # Call the manager method which performs concurrent Airtable calls
    table1, table2 = await manager.fetch_two_tables()

    return {"table1": table1, "table2": table2}
```

#### Key Points

1. Single Instantiation: By creating the AirtableAsync client in the AirtableManager.`__init__`, all subsequent methods in that manager can reuse the same instance.
2. Encapsulation: Any additional logic (e.g., error handling, caching, logging) can live inside methods of AirtableManager.

If you want to go even further, you could hold a single `aiohttp.ClientSession` inside `AirtableAsync`, manually open it at manager initialization, and close it gracefully on shutdown. This helps reuse TCP connections and reduce overhead.

---

## Rate-Limiting Examples

Airtable imposes rate limits, and you may want to **throttle** or **delay** your requests to avoid hitting them. Below are three illustrative methods:

1. **Explicit Delay in Your Code**  
   Simply call `await asyncio.sleep(...)` after your Airtable call:
   ```python
   from sncl.airtable_async import AirtableAsync
   import asyncio

   async def create_records_with_sleep():
       airtable = AirtableAsync(base_id="your_base_id", api_key="your_api_key")
       await airtable.create_records("your_table_id", [{"fields": {"Name": "Test"}}])
       await asyncio.sleep(1.0)  # Sleep for 1 second before next request
   ```

2. **Decorator-Based Approach**  
   Define a decorator that injects a delay before or after the function call:
   ```python
   import asyncio
   import functools
   from sncl.airtable_async import AirtableAsync

   def rate_limit(delay: float = 1.0):
       def decorator(func):
           @functools.wraps(func)
           async def wrapper(*args, **kwargs):
               result = await func(*args, **kwargs)
               await asyncio.sleep(delay)
               return result
           return wrapper
       return decorator

   @rate_limit(delay=2.0)
   async def create_record_decorated():
       airtable = AirtableAsync("base_id", "api_key")
       return await airtable.create_records("table_id", [{"fields": {"Name": "Decorated"}}])

   # Usage
   # records = await create_record_decorated()  # This will always wait 2 seconds after finishing
   ```

3. **Token Bucket or Semaphore**  
   A more advanced pattern involves a semaphore to limit concurrent requests. For instance:
   ```python
   import asyncio
   from sncl.airtable_async import AirtableAsync

   # Global semaphore (e.g., allow 5 concurrent Airtable calls)
   airtable_semaphore = asyncio.Semaphore(5)

   async def fetch_with_semaphore():
       async with airtable_semaphore:
           # Your code here
           airtable = AirtableAsync("base_id", "api_key")
           return await airtable.fetch_records("table_id")

   async def main():
       # Launch many tasks, each must acquire the semaphore first
       tasks = [fetch_with_semaphore() for _ in range(20)]
       return await asyncio.gather(*tasks)

   # results = asyncio.run(main())
   ```

Each approach can be fine-tuned to your project’s needs. The token bucket or semaphore pattern is often the most flexible and powerful for controlling concurrency in a production environment.

---

## Getting Help

To get help on any function in the `Airtable` or `AirtableAsync` classes, you can use Python’s built-in `help()` function. For example:

```python
help(AirtableAsync.fetch_records)
```

This will display the function’s docstring, including its purpose, arguments, and return values.

---

## Dependencies

The following libraries are required to use `sncl`:

- **requests**: For making HTTP requests in the synchronous API.
- **aiohttp**: For making HTTP requests in the asynchronous API.
- **pandas**: For processing and managing Airtable records as DataFrames.

You can install these dependencies using:

```bash
pip install requests aiohttp pandas
```

---

## License

This library is licensed under the [MIT License](LICENSE).

---

For questions, feedback, or contributions, contact [Sasha Nicolai](mailto:sasha@candyflip.co).
"""
