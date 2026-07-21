from __future__ import annotations

import logging
from typing import Any, Dict, List

from rich.console import Console

from collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)
console = Console()

# ── Queries (templates) ───────────────────────────────────────────────────────
# Nomes de queries e campos são estimados com base no modelo Prevision.
# Devem ser validados contra o schema real via: python main.py explore --queries

PROJECTS_QUERY = """
query GetProjects($first: Int, $after: String) {
  projects(first: $first, after: $after) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        name
        code
        status
        startDate
        endDate
        progress
        createdAt
        updatedAt
      }
    }
  }
}
"""

WBS_QUERY = """
query GetWBS($projectId: ID, $first: Int, $after: String) {
  wbs(projectId: $projectId, first: $first, after: $after) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        name
        code
        parentId
        level
        type
        progress
        physicalProgress
        startDate
        endDate
        status
        projectId
      }
    }
  }
}
"""

LOTS_QUERY = """
query GetLots($projectId: ID, $first: Int, $after: String) {
  lots(projectId: $projectId, first: $first, after: $after) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        name
        code
        packageId
        progress
        status
        startDate
        endDate
        projectId
      }
    }
  }
}
"""

ACTIVITIES_QUERY = """
query GetActivities($projectId: ID, $first: Int, $after: String) {
  activities(projectId: $projectId, first: $first, after: $after) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        name
        code
        parentId
        progress
        physicalProgress
        type
        status
        startDate
        endDate
        projectId
        wbsId
      }
    }
  }
}
"""

MEASUREMENTS_QUERY = """
query GetMeasurements($projectId: ID, $first: Int, $after: String) {
  measurements(projectId: $projectId, first: $first, after: $after) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        itemId
        value
        percentage
        periodDate
        status
        projectId
        createdAt
      }
    }
  }
}
"""


class ScheduleCollector(BaseCollector):
    def name(self) -> str:
        return "schedule"

    def collect(self) -> List[Dict[str, Any]]:
        return self.collect_wbs()

    def collect_projects(self) -> List[Dict]:
        console.print("[blue]  → projects...[/]")
        items, total = self._paginate(PROJECTS_QUERY, {}, "projects")
        console.print(f"    {len(items)}/{total}")
        return items

    def collect_wbs(self) -> List[Dict]:
        console.print("[blue]  → wbs...[/]")
        items, total = self._paginate(WBS_QUERY, {"projectId": self.project_id}, "wbs")
        console.print(f"    {len(items)}/{total}")
        return items

    def collect_lots(self) -> List[Dict]:
        console.print("[blue]  → lots...[/]")
        items, total = self._paginate(LOTS_QUERY, {"projectId": self.project_id}, "lots")
        console.print(f"    {len(items)}/{total}")
        return items

    def collect_activities(self) -> List[Dict]:
        console.print("[blue]  → activities...[/]")
        items, total = self._paginate(ACTIVITIES_QUERY, {"projectId": self.project_id}, "activities")
        console.print(f"    {len(items)}/{total}")
        return items

    def collect_measurements(self) -> List[Dict]:
        console.print("[blue]  → measurements...[/]")
        items, total = self._paginate(MEASUREMENTS_QUERY, {"projectId": self.project_id}, "measurements")
        console.print(f"    {len(items)}/{total}")
        return items

    def collect_all(self) -> Dict[str, List[Dict]]:
        console.print("[bold]Coletando cronograma e execução...[/]")
        wbs = self.collect_wbs()
        lots = self.collect_lots()
        activities = self.collect_activities()
        measurements = self.collect_measurements()

        console.print(
            f"[green]✓ Cronograma:[/] {len(wbs)} WBS | {len(lots)} lotes | "
            f"{len(activities)} atividades | {len(measurements)} medições"
        )
        return {
            "wbs": wbs,
            "lots": lots,
            "activities": activities,
            "measurements": measurements,
        }
