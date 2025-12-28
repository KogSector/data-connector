"""
ConHub Data Connector - Connectors Package

Exports connector classes and registry.
"""

from connectors.base import BaseConnector, ChangeEvent, Item, ItemContent
from connectors.github import GitHubConnector
from connectors.local_file import LocalFileConnector
from connectors.registry import get_connector, get_source_kind

__all__ = [
    # Base classes
    "BaseConnector",
    "Item",
    "ItemContent",
    "ChangeEvent",
    # Connectors
    "GitHubConnector",
    "LocalFileConnector",
    # Registry
    "get_connector",
    "get_source_kind",
]
