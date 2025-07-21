# Utils Module

This folder contains helper utilities used across the `mimeiapify` package.

## Logger

`logger.py` exposes `setup_logging`, an opinionated configuration based on
[Rich](https://github.com/Textualize/rich). Call this function once when your
application starts to initialise console logging and, optionally, daily log
files.

```python
from mimeiapify.utils.logger import setup_logging

# console only
setup_logging(level="DEBUG")

# console plus daily file
setup_logging(
    level="INFO",
    mode="DEV",          # enables file logging
    log_dir="./logs",    # folder for log files
)
```

Use the `console_fmt` and `file_fmt` parameters to customise the output format
and add contextual information (tenant IDs, request IDs, etc.).

## Helper Functions

`helper_functions.py` bundles small utilities that are useful across projects:

- `parse_datetime_to_target_tz` – parse a datetime or ISO string and convert it
  to a given timezone.
- `datetime_to_iso_string` – serialise aware datetimes to an ISO string.
- `format_date_friendly` – convert an ISO date string to a human friendly
  Spanish representation.
- `robust_clean_text` – clean and normalise blocks of text (dedent, collapse
  whitespace, remove markdown headings, etc.).

Example usage:

```python
from mimeiapify.utils import helper_functions as hf

parsed = hf.parse_datetime_to_target_tz("2025-01-16T15:04:09Z", "America/Bogota")
clean = hf.robust_clean_text("## Heading\nSome **bold** text")
```
