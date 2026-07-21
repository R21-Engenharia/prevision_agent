from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from config.settings import PrevisionConfig

logger = logging.getLogger(__name__)

# Introspection completa — captura tudo necessário para o catálogo
INTROSPECTION_QUERY = """
query FullIntrospection {
  __schema {
    queryType    { name }
    mutationType { name }
    subscriptionType { name }
    types {
      kind
      name
      description
      fields(includeDeprecated: true) {
        name
        description
        isDeprecated
        deprecationReason
        args {
          name
          description
          defaultValue
          type { ...TypeRef }
        }
        type { ...TypeRef }
      }
      inputFields {
        name
        description
        defaultValue
        type { ...TypeRef }
      }
      interfaces { name }
      enumValues(includeDeprecated: true) {
        name
        description
        isDeprecated
      }
      possibleTypes { name kind }
    }
    directives {
      name
      description
      locations
    }
  }
}
fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
        ofType { kind name }
      }
    }
  }
}
"""


class GraphQLError(Exception):
    def __init__(self, errors: list):
        self.errors = errors
        messages = "; ".join(e.get("message", str(e)) for e in errors)
        super().__init__(f"GraphQL errors: {messages}")


class GraphQLClient:
    """
    Cliente GraphQL para a API do Prevision.

    Autenticação: UserAuthorization: token {TOKEN}
    Paginação: Relay cursor (after/first/pageInfo/edges/nodes/totalCount)
    """

    def __init__(self, config: PrevisionConfig):
        self.config = config
        self._client = httpx.Client(
            timeout=config.timeout,
            headers=config.build_headers(),
            follow_redirects=True,
        )

    def execute(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        operation_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.config.token:
            raise ValueError(
                "PREVISION_TOKEN não configurado.\n"
                "  Copie .env.example → .env e preencha PREVISION_TOKEN."
            )

        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name

        logger.debug("→ GraphQL %s %s", operation_name or "query", variables or "")

        response = self._client.post(self.config.endpoint, json=payload)
        response.raise_for_status()

        body = response.json()

        if "errors" in body and body["errors"]:
            raise GraphQLError(body["errors"])

        return body.get("data", {})

    def paginate_relay(
        self,
        query: str,
        variables: Dict[str, Any],
        connection_key: str,
        page_size: Optional[int] = None,
    ) -> Tuple[List[Dict], int]:
        """
        Paginação Relay cursor.
        Retorna (lista_de_itens, total_count).

        A query deve aceitar $first: Int e $after: String.
        O campo `connection_key` deve retornar um objeto com:
          { totalCount, pageInfo { hasNextPage endCursor }, edges { node { ... } } }
          ou { totalCount, pageInfo { ... }, nodes { ... } }
        """
        size = page_size or self.config.page_size
        results: List[Dict] = []
        after: Optional[str] = None
        total_count: int = 0
        page = 0

        while True:
            page += 1
            vars_page = {**variables, "first": size}
            if after:
                vars_page["after"] = after

            data = self.execute(query, vars_page)
            connection = data.get(connection_key)

            if connection is None:
                logger.warning("Chave '%s' não encontrada na resposta", connection_key)
                break

            if isinstance(connection, list):
                results.extend(connection)
                break

            total_count = connection.get("totalCount", total_count)

            edges = connection.get("edges", [])
            nodes = connection.get("nodes", [])

            if edges:
                items = [e["node"] for e in edges if "node" in e]
            elif nodes:
                items = nodes
            else:
                items = []

            results.extend(items)
            logger.debug("Relay pág %d: +%d itens (total=%d)", page, len(items), len(results))

            page_info = connection.get("pageInfo", {})
            has_next = page_info.get("hasNextPage", False)
            end_cursor = page_info.get("endCursor")

            if not has_next or not end_cursor or not items:
                break

            after = end_cursor

        return results, total_count

    def introspect(self) -> Dict[str, Any]:
        return self.execute(INTROSPECTION_QUERY, operation_name="FullIntrospection")

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
