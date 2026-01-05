import logging
from typing import Any, Dict

from core.bases import DownloadClient, SearchProvider

logger = logging.getLogger(__name__)


class ProviderFactory:
    """Factory for creating provider instances from config"""

    PROVIDERS = {
        "newsnab": "providers.newsnab:NewsnabProvider",
        "rss": "providers.rss:RSSProvider",
        "crossref": "providers.crossref:CrossRefProvider",
        "wikipedia": "providers.wikipedia:WikipediaProvider",
    }

    @staticmethod
    def create(provider_config: Dict[str, Any]) -> SearchProvider:
        """Create provider instance from config"""
        provider_type = provider_config.get("type")

        if provider_type not in ProviderFactory.PROVIDERS:
            raise ValueError(f"Unknown provider type: {provider_type}")

        module_path, class_name = ProviderFactory.PROVIDERS[provider_type].split(":")
        module = __import__(module_path, fromlist=[class_name])
        provider_class = getattr(module, class_name)

        return provider_class(provider_config)


class ClientFactory:
    """Factory for creating download client instances from config"""

    CLIENTS = {
        "sabnzbd": "clients.sabnzbd:SABnzbdClient",
    }

    @staticmethod
    def create(client_config: Dict[str, Any]) -> DownloadClient:
        """Create client instance from config"""
        client_type = client_config.get("type")

        if client_type not in ClientFactory.CLIENTS:
            raise ValueError(f"Unknown client type: {client_type}")

        module_path, class_name = ClientFactory.CLIENTS[client_type].split(":")
        module = __import__(module_path, fromlist=[class_name])
        client_class = getattr(module, class_name)

        return client_class(client_config)
