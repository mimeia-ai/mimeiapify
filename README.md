# SNCL - Sasha Nicolai's Library

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

## Future Plans

- Add integrations for additional APIs (Notion, WhatsApp, Gmail).
- Expand utility functions for data processing and manipulation.
- Provide improved error handling and logging for all operations.
---

## Installation

### Pip Install
Install the library directly using pip:

```bash
pip install sncl
```

This will make the library available for use across your projects.

---

## Usage

To start using the `sncl` library, you can import its modules like this:

```python
from sncl import airtable as at
```

### Example Usage

#### Fetching an Airtable Base Schema
```python
base_id = "your_airtable_base_id"
airtable_token = "your_airtable_token"

schema = at.get_schema(base_id, airtable_token)
print(schema)
```

#### Extracting Table IDs from a Schema
```python
table_ids = at.extract_table_ids(schema)
print(table_ids)
```

#### Fetching Records
```python
base_id = "your_airtable_base_id"
table_id = "your_table_id"
airtable_token = "your_airtable_token"

records = at.fetch_airtable_records(base_id, table_id, airtable_token)
print(records)
```

#### Creating a Field in Airtable
```python
base_id = "your_airtable_base_id"
table_id = "your_table_id"
api_key = "your_airtable_api_key"

fields = [
    {
        "name": "New Field",
        "type": "singleLineText",
        "description": "This is a new field for testing."
    }
]

at.create_airtable_fields(base_id, table_id, api_key, fields)
```

---

## Getting Help

To get help on any function in the `sncl.airtable` module, you can use the Python `help()` function. For example:

```python
help(at.get_schema)
```

This will display the function's docstring, including its purpose, arguments, and return values.

---

## Dependencies

The following libraries are required to use `sncl`:

- **requests**: For making HTTP requests to the Airtable API.
- **pandas**: For processing and managing Airtable records as DataFrames.

You can install these dependencies using:

```bash
pip install requests pandas
```

---

## License

This library is licensed under the [MIT License](LICENSE).

---

For questions, feedback, or contributions, contact [Sasha Nicolai](mailto:sasha@candyflip.co).
