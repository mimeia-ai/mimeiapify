"""
Symphony Concurrency Module

Provides the GlobalSymphony singleton for managing thread pools, 
event loops, and shared resources like Redis connections.
"""

from .globals import GlobalSymphony, GlobalSymphonyConfig

__all__ = ["GlobalSymphony", "GlobalSymphonyConfig"] 