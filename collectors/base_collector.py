from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

from client.graphql_client import GraphQLClient
from config.settings import PrevisionConfig

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    def __init__(self, client: GraphQLClient, config: PrevisionConfig):
        self.client = client
        self.config = config
        self.project_id = config.project_id

    @abstractmethod
    def collect(self) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def name(self) -> str:
        ...

    def _paginate(
        self,
        query: str,
        variables: Dict[str, Any],
        connection_key: str,
    ) -> Tuple[List[Dict], int]:
        """Paginação Relay cursor. Retorna (itens, total_count)."""
        try:
            items, total = self.client.paginate_relay(query, variables, connection_key)
            logger.info("Coletado '%s': %d/%d itens", connection_key, len(items), total)
            return items, total
        except Exception as e:
            logger.error("Falha na coleta de '%s': %s", connection_key, e)
            raise
