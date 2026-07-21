import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
SCHEMA_DIR = DATA_DIR / "schema"


@dataclass
class PrevisionConfig:
    endpoint: str = "https://api.prevision.com.br/graphql"
    token: Optional[str] = None
    project_id: Optional[str] = None
    timeout: int = 60
    page_size: int = 100

    def build_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["UserAuthorization"] = f"token {self.token}"
        return headers


def load_config() -> PrevisionConfig:
    return PrevisionConfig(
        endpoint=os.getenv("PREVISION_ENDPOINT", "https://api.prevision.com.br/graphql"),
        token=os.getenv("PREVISION_TOKEN"),
        project_id=os.getenv("PREVISION_PROJECT_ID"),
        timeout=int(os.getenv("PREVISION_TIMEOUT", "60")),
        page_size=int(os.getenv("PREVISION_PAGE_SIZE", "100")),
    )
