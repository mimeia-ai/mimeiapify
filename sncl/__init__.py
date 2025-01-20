# sncl/__init__.py

from .airtable import Airtable  # Import synchronous Airtable
from .airtable_async import AirtableAsync  # Import asynchronous Airtable

__all__ = ["Airtable", "AirtableAsync"]
