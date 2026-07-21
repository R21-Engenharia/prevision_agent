from __future__ import annotations

import logging
from typing import Any, Dict, List

from rich.console import Console

from collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)
console = Console()

# ── Queries (templates) ───────────────────────────────────────────────────────
# Baseadas nas entidades confirmadas: QualityAssociation, QualityAssociationTask,
# QualityAssociationTaskCompleted.
# Campos exatos serão validados/ajustados após `python main.py explore`.

QUALITY_ASSOCIATIONS_QUERY = """
query GetQualityAssociations($projectId: ID, $first: Int, $after: String) {
  qualityAssociations(projectId: $projectId, first: $first, after: $after) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        itemId
        partnerLocalId
        partnerModelId
        partnerReferenceName
        projectId
        status
        completedAt
        createdAt
        updatedAt
      }
    }
  }
}
"""

QUALITY_TASKS_QUERY = """
query GetQualityAssociationTasks($projectId: ID, $first: Int, $after: String) {
  qualityAssociationTasks(projectId: $projectId, first: $first, after: $after) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        qualityAssociationId
        name
        status
        order
        completedAt
        createdAt
        updatedAt
      }
    }
  }
}
"""

QUALITY_TASKS_COMPLETED_QUERY = """
query GetQualityAssociationTasksCompleted($projectId: ID, $first: Int, $after: String) {
  qualityAssociationTasksCompleted(projectId: $projectId, first: $first, after: $after) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        qualityAssociationId
        taskId
        completedAt
        completedBy
        createdAt
      }
    }
  }
}
"""


class QualityCollector(BaseCollector):
    def name(self) -> str:
        return "quality"

    def collect(self) -> List[Dict[str, Any]]:
        items, _ = self._paginate(
            QUALITY_ASSOCIATIONS_QUERY,
            {"projectId": self.project_id},
            "qualityAssociations",
        )
        return items

    def collect_associations(self) -> List[Dict]:
        console.print("[blue]  → qualityAssociations...[/]")
        items, total = self._paginate(
            QUALITY_ASSOCIATIONS_QUERY,
            {"projectId": self.project_id},
            "qualityAssociations",
        )
        console.print(f"    {len(items)}/{total}")
        return items

    def collect_tasks(self) -> List[Dict]:
        console.print("[blue]  → qualityAssociationTasks...[/]")
        items, total = self._paginate(
            QUALITY_TASKS_QUERY,
            {"projectId": self.project_id},
            "qualityAssociationTasks",
        )
        console.print(f"    {len(items)}/{total}")
        return items

    def collect_tasks_completed(self) -> List[Dict]:
        console.print("[blue]  → qualityAssociationTasksCompleted...[/]")
        items, total = self._paginate(
            QUALITY_TASKS_COMPLETED_QUERY,
            {"projectId": self.project_id},
            "qualityAssociationTasksCompleted",
        )
        console.print(f"    {len(items)}/{total}")
        return items

    def collect_all(self) -> Dict[str, List[Dict]]:
        console.print("[bold]Coletando entidades de qualidade...[/]")
        associations = self.collect_associations()
        tasks = self.collect_tasks()
        tasks_completed = self.collect_tasks_completed()

        console.print(
            f"[green]✓ Qualidade:[/] {len(associations)} assoc. | "
            f"{len(tasks)} tarefas | {len(tasks_completed)} concluídas"
        )
        return {
            "quality_associations": associations,
            "quality_tasks": tasks,
            "quality_tasks_completed": tasks_completed,
        }
