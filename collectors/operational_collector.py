"""
Collector operacional — coleta os dados acessíveis via API Prevision.

Path correto: me(id: 479) { project(id: X) { ... } }
Campos SEGUROS descobertos na Fase 2.

Estratégia para Activities:
  - filter: { id: floorId } CRASHA o servidor (500)
  - Solução: cursor Relay — floorsPage(first: 1, after: prevFloorCursor)
    Para floor[0]: floorsPage(first: 1)  (sem after)
    Para floor[i]: floorsPage(first: 1, after: cursor_of_floor[i-1])
"""
import os, time, logging
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

COMPANY_ID = 479

# ── Queries ───────────────────────────────────────────────────────────────────

# Inclui cursor na edge para permitir navegação por floor específico
FLOORS_QUERY = """
query Floors($companyId: ID!, $projectId: ID!, $first: Int, $after: String) {
  me(id: $companyId) {
    project(id: $projectId) {
      id name
      floorsPage(first: $first, after: $after) {
        totalCount
        pageInfo { hasNextPage endCursor }
        edges {
          cursor
          node {
            id name position
            startAt endAt tag
            hasQualityLocalsAssociations
            activitiesPage { totalCount }
          }
        }
      }
    }
  }
}
"""

# Para floor[0]: after=None  → floorsPage(first: 1) → devolve floor[0]
# Para floor[i>0]: after=cursor[i-1] → floorsPage(first: 1, after=cursor[i-1]) → devolve floor[i]
ACTIVITIES_BY_CURSOR_QUERY = """
query ActivitiesByCursor($companyId: ID!, $projectId: ID!,
                         $prevCursor: String,
                         $first: Int, $actAfter: String) {
  me(id: $companyId) {
    project(id: $projectId) {
      floorsPage(first: 1, after: $prevCursor) {
        edges {
          node {
            id
            activitiesPage(first: $first, after: $actAfter) {
              totalCount
              pageInfo { hasNextPage endCursor }
              edges {
                node {
                  id
                  percentageCompleted
                  expectedPercentageCompleted
                  hasQualityAssociations
                  startAt
                  endAt
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

# Versão sem after (para floor[0])
ACTIVITIES_FIRST_FLOOR_QUERY = """
query ActivitiesFirstFloor($companyId: ID!, $projectId: ID!,
                           $first: Int, $actAfter: String) {
  me(id: $companyId) {
    project(id: $projectId) {
      floorsPage(first: 1) {
        edges {
          node {
            id
            activitiesPage(first: $first, after: $actAfter) {
              totalCount
              pageInfo { hasNextPage endCursor }
              edges {
                node {
                  id
                  percentageCompleted
                  expectedPercentageCompleted
                  hasQualityAssociations
                  startAt
                  endAt
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

QUALITY_ASSOCIATIONS_QUERY = """
query QualityAssociations($companyId: ID!, $projectId: ID!, $first: Int, $after: String) {
  me(id: $companyId) {
    project(id: $projectId) {
      qualityAssociationsPage(first: $first, after: $after) {
        totalCount
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            id
            itemId
            eapType
            partnerLocalId
            partnerModelId
            partnerReferenceName
            projectId
          }
        }
      }
    }
  }
}
"""

SERVICES_QUERY = """
query Services($companyId: ID!, $projectId: ID!, $first: Int, $after: String) {
  me(id: $companyId) {
    project(id: $projectId) {
      servicesPage(first: $first, after: $after) {
        totalCount
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            id name position color
            hasQualityAssociations
            hasQualityModelsAssociations
          }
        }
      }
    }
  }
}
"""


class OperationalCollector:
    """Coleta dados operacionais de progresso e qualidade."""

    def __init__(self, client, company_id: int = COMPANY_ID, page_size: int = 50,
                 activity_page_size: int = 15, max_retries: int = 3):
        self.client = client
        self.company_id = company_id
        self.page_size = page_size
        self.activity_page_size = activity_page_size  # menor para evitar timeout
        self.max_retries = max_retries

    def _relay_all(self, query: str, variables: dict,
                   path: List[str], label: str = "",
                   include_cursors: bool = False,
                   ) -> Tuple[List[Dict], int, List[str]]:
        """
        Pagina uma connection Relay.
        path: caminho de chaves até a connection, ex. ["me", "project", "floorsPage"]
        include_cursors: se True, retorna também lista de cursores das edges.
        Retorna (items, total_count, cursors).
        """
        results: List[Dict] = []
        cursors: List[str] = []
        after: Optional[str] = None
        total_count = 0
        page = 0

        while True:
            page += 1
            vars_ = {**variables, "first": self.page_size}
            if after:
                vars_["after"] = after

            data = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    data = self.client.execute(query, vars_)
                    break
                except Exception as e:
                    if attempt < self.max_retries:
                        wait = 2 ** attempt
                        logger.warning("Tentativa %d/%d pag %d %s: %s (retry %ds)",
                                       attempt, self.max_retries, page, label, e, wait)
                        time.sleep(wait)
                    else:
                        logger.error("Desistindo pag %d %s: %s", page, label, e)
            if data is None:
                break

            node = data
            for key in path:
                if node is None:
                    break
                node = node.get(key)

            if not node:
                logger.warning("Path %s nao encontrado", path)
                break

            if total_count == 0:
                total_count = node.get("totalCount", 0)

            edges = node.get("edges", [])
            for e in edges:
                if "node" in e:
                    results.append(e["node"])
                if include_cursors:
                    cursors.append(e.get("cursor", ""))

            pi = node.get("pageInfo", {})
            if not pi.get("hasNextPage") or not pi.get("endCursor") or not edges:
                break
            after = pi["endCursor"]

            if label and total_count:
                pct = int(len(results) / total_count * 100)
                print(f"  {label}: {len(results)}/{total_count} ({pct}%)", flush=True)

        return results, total_count, cursors

    def collect_floors(self, project_id: str) -> Tuple[List[Dict], int, List[str]]:
        """
        Coleta todos os Floors do projeto.
        Retorna (floors, total, cursors) — cursors usados na navegação de atividades.
        """
        print(f"\nColetando Floors (projeto {project_id})...", flush=True)
        items, total, cursors = self._relay_all(
            FLOORS_QUERY,
            {"companyId": str(self.company_id), "projectId": project_id},
            ["me", "project", "floorsPage"],
            label="Floors",
            include_cursors=True,
        )
        print(f"  -> {len(items)} floors (total={total})", flush=True)
        return items, total, cursors

    def _extract_activities_from_response(self, data: dict,
                                          floor_id: str,
                                          floor_name: str) -> Tuple[List[Dict], dict]:
        """Extrai atividades e pageInfo de um response de activitiesPage."""
        floor_edge = (data.get("me", {})
                          .get("project", {})
                          .get("floorsPage", {})
                          .get("edges", [{}])[0:1])
        if not floor_edge:
            return [], {}
        floor_node = floor_edge[0].get("node", {})
        acts_page = floor_node.get("activitiesPage", {})
        edges = acts_page.get("edges", [])
        items = []
        for e in edges:
            item = dict(e.get("node", {}))
            item["floor_id"] = floor_id
            item["floor_name"] = floor_name
            items.append(item)
        return items, acts_page.get("pageInfo", {})

    def collect_activities_for_floor(self, project_id: str,
                                     floor_id: str,
                                     floor_name: str,
                                     floor_index: int,
                                     prev_floor_cursor: Optional[str]) -> List[Dict]:
        """
        Coleta Activities de um floor via cursor Relay.
        floor_index=0 → sem after; floor_index>0 → after=prev_floor_cursor.
        """
        results: List[Dict] = []
        act_after: Optional[str] = None
        act_page = 0

        while True:
            act_page += 1
            base_vars = {
                "companyId": str(self.company_id),
                "projectId": project_id,
                "first": self.activity_page_size,
            }
            if act_after:
                base_vars["actAfter"] = act_after

            if floor_index == 0:
                query = ACTIVITIES_FIRST_FLOOR_QUERY
                vars_ = base_vars
            else:
                query = ACTIVITIES_BY_CURSOR_QUERY
                vars_ = {**base_vars, "prevCursor": prev_floor_cursor}

            # Retry com backoff
            data = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    data = self.client.execute(query, vars_)
                    break
                except Exception as e:
                    if attempt < self.max_retries:
                        wait = 2 ** attempt
                        logger.warning("Tentativa %d/%d floor %s pag %d: %s (retry em %ds)",
                                       attempt, self.max_retries, floor_id, act_page, e, wait)
                        time.sleep(wait)
                    else:
                        logger.warning("Desistindo floor %s pag %d apos %d tentativas: %s",
                                       floor_id, act_page, self.max_retries, e)

            if data is None:
                break

            items, pi = self._extract_activities_from_response(
                data, floor_id, floor_name
            )
            results.extend(items)

            if not pi.get("hasNextPage") or not pi.get("endCursor") or not items:
                break
            act_after = pi["endCursor"]
            time.sleep(0.2)

        return results

    def collect_all_activities(self, project_id: str,
                               floors: List[Dict],
                               floor_cursors: List[str]) -> List[Dict]:
        """Coleta Activities de todos os Floors usando cursors para navegação."""
        print(f"\nColetando Activities de {len(floors)} floors...", flush=True)
        all_activities: List[Dict] = []

        for i, floor in enumerate(floors):
            fid = floor["id"]
            fname = floor.get("name", fid)
            n_acts = floor.get("activitiesPage", {}).get("totalCount", 0)
            prev_cursor = floor_cursors[i - 1] if i > 0 else None

            print(f"  [{i+1}/{len(floors)}] {fname[:45]} "
                  f"({n_acts} atividades)...", flush=True)

            acts = self.collect_activities_for_floor(
                project_id, fid, fname, i, prev_cursor
            )
            all_activities.extend(acts)
            time.sleep(0.2)

        print(f"  -> {len(all_activities)} atividades coletadas", flush=True)
        return all_activities

    def collect_quality_associations(self, project_id: str) -> Tuple[List[Dict], int]:
        print(f"\nColetando QualityAssociations (projeto {project_id})...", flush=True)
        items, total, _ = self._relay_all(
            QUALITY_ASSOCIATIONS_QUERY,
            {"companyId": str(self.company_id), "projectId": project_id},
            ["me", "project", "qualityAssociationsPage"],
            label="QualityAssoc",
        )
        print(f"  -> {len(items)} associacoes (total={total})", flush=True)
        return items, total

    def collect_services(self, project_id: str) -> Tuple[List[Dict], int]:
        print(f"\nColetando Services (projeto {project_id})...", flush=True)
        items, total, _ = self._relay_all(
            SERVICES_QUERY,
            {"companyId": str(self.company_id), "projectId": project_id},
            ["me", "project", "servicesPage"],
            label="Services",
        )
        print(f"  -> {len(items)} servicos (total={total})", flush=True)
        return items, total

    def collect_all(self, project_id: str, project_name: str = "") -> Dict:
        """Coleta completa para um projeto."""
        label = project_name or project_id
        print(f"\n{'='*60}", flush=True)
        print(f"COLETA COMPLETA: {label}", flush=True)
        print(f"{'='*60}", flush=True)

        floors, n_floors, floor_cursors = self.collect_floors(project_id)
        services, n_services = self.collect_services(project_id)
        qa, n_qa = self.collect_quality_associations(project_id)
        activities = self.collect_all_activities(project_id, floors, floor_cursors)

        return {
            "project_id": project_id,
            "project_name": label,
            "floors": floors,
            "services": services,
            "quality_associations": qa,
            "activities": activities,
            "totals": {
                "floors": n_floors,
                "services": n_services,
                "quality_associations": n_qa,
                "activities": len(activities),
            },
        }
