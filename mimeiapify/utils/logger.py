"""
utils.logger

Opinionated Rich-based logger for colour-rich, flexible logging in Python projects.

Provides a setup_logging() function to configure console and file logging with rich formatting.

Usage:
    from mimeiapify.utils.logger import setup_logging
    setup_logging(level="DEBUG", mode="DEV", log_dir="./logs")

Call once at application start-up (FastAPI lifespan or if __name__ == "__main__":).

Usage
-----
from symphony_concurrency.utils.logger import setup_logging

setup_logging(
    level="INFO",
    mode="DEV",
    log_dir="./logs",
    console_fmt="[%(levelname)s] %(name)s • %(message)s",
    file_fmt="%(asctime)s — %(levelname)s — %(name)s — %(message)s",
)
"""

from __future__ import annotations
import logging, os, warnings
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

# silence numpy/numexpr warnings that clutter Rich output
warnings.filterwarnings("ignore", message="NumExpr defaulting to.*")

# --------------------------------------------------------------------------- #
#  THEME & CONSOLE
# --------------------------------------------------------------------------- #
_theme = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "debug": "dim white",
    }
)
_console = Console(theme=_theme)


# --------------------------------------------------------------------------- #
#  SET-UP FUNCTION
# --------------------------------------------------------------------------- #
def setup_logging(
    *,
    level: str = "INFO",
    mode: str = "PROD",
    log_dir: Optional[str] = None,
    console_fmt: str | None = None,
    file_fmt: str | None = None,
) -> None:
    """
    Initialise the root logger.  Call **once** at app start-up.

    Parameters
    ----------
    level       Logging level string.  One of "DEBUG" | "INFO" | "WARNING" | "ERROR".
    mode        "DEV" creates a daily log-file as well as console; anything else → console only.
    log_dir     Folder where log-files live (DEV mode only).
    console_fmt Rich console format-string.  Defaults to "[%(levelname)s] %(name)s • %(message)s".
    file_fmt    File-log format-string.  Defaults to ISO timestamp + level + message.
    """
    lvl = level.upper()
    lvl = lvl if lvl in ("DEBUG", "INFO", "WARNING", "ERROR") else "INFO"

    # defaults
    console_fmt = console_fmt or "[%(levelname)s] [%(name)s] • %(message)s"
    file_fmt = file_fmt or "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    # 1) Rich console handler
    rich_handler = RichHandler(
        console=_console,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        show_time=True,
        show_level=True,
        markup=False,
    )
    rich_handler.setFormatter(logging.Formatter(console_fmt))

    handlers: list[logging.Handler] = [rich_handler]

    # 2) Optional file handler
    if mode.upper() == "DEV" and log_dir:
        os.makedirs(log_dir, exist_ok=True)
        logfile = os.path.join(
            log_dir, f"app_logs_{datetime.now():%Y%m%d}.log"
        )
        fh = logging.FileHandler(logfile, encoding="utf-8")
        fh.setFormatter(logging.Formatter(file_fmt))
        handlers.append(fh)
        _console.print(f"[green]DEV mode:[/] console + file → {logfile}")
        logging.getLogger("LoggerSetup").info(f"File logging enabled at {logfile}")
    else:
        _console.print(f"Logging configured for mode '{mode}'. Console only.")
        logging.getLogger("LoggerSetup").info(f"Console-only logging for mode '{mode}'")

    logging.basicConfig(level=lvl, handlers=handlers, force=True)

    # announce
    logging.getLogger("LoggerSetup").info("Logging initialised (%s)", lvl)


"""
# utils.logger

Opinionated Rich-based logger.

```python
from symphony_concurrency.utils.logger import setup_logging

# console only
setup_logging(level="DEBUG")

# console + rolling file
setup_logging(
    level="INFO",
    mode="DEV",
    log_dir="./logs",
    console_fmt="[%(levelname)s] [%(name)s] %(message)s",
)
```
Call once at application start-up (FastAPI lifespan or if __name__ == "__main__":).

Pass your own console_fmt/file_fmt to inject tenant IDs, request IDs, etc.

"""