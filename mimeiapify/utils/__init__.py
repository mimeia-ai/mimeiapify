"""
Utils Module

Utility functions and logging configuration.
"""

from .logger import setup_logging
from . import helper_functions

# Create a pre-configured logger instance
import logging
logger = logging.getLogger("mimeiapify")

__all__ = ["setup_logging", "logger", "helper_functions"]
