# sncl/__init__.py

from .airtable import (
    get_schema,
    extract_table_ids,
    create_airtable_fields,
    fetch_airtable_records,
    fetch_filtered_airtable_records,
    create_airtable_records,
    update_single_airtable_record,
    update_multiple_airtable_records,
    delete_single_airtable_record,
    delete_multiple_airtable_records,
    upload_airtable_attachment,
    update_airtable_field
)

__all__ = [
    "get_schema",
    "extract_table_ids",
    "create_airtable_fields",
    "fetch_airtable_records",
    "fetch_filtered_airtable_records",
    "create_airtable_records",
    "update_single_airtable_record",
    "update_multiple_airtable_records",
    "delete_single_airtable_record",
    "delete_multiple_airtable_records",
    "upload_airtable_attachment",
    "update_airtable_field"
]