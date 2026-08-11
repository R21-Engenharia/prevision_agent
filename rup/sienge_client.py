"""
rup/sienge_client.py
====================
Cliente REST da API pública do Sienge (autenticação HTTP Basic).

A API do Sienge vive em:
    https://api.sienge.com.br/{subdominio}/public/api/v1
com um usuário/senha de integração (Configurações → Integrações → API).
A base "bulk-data" (grandes volumes) fica em:
    https://api.sienge.com.br/{subdominio}/public/api/bulk-data/v1

Credenciais SÓ por ambiente — nunca hardcoded:
    SIENGE_SUBDOMAIN, SIENGE_API_USER, SIENGE_API_PASSWORD
"""
from __future__ import annotations

import os

import httpx


class SiengeClient:
    def __init__(self, subdominio: str | None = None,
                 usuario: str | None = None, senha: str | None = None) -> None:
        self.subdominio = subdominio or os.getenv("SIENGE_SUBDOMAIN", "")
        self.usuario = usuario or os.getenv("SIENGE_API_USER", "")
        self.senha = senha or os.getenv("SIENGE_API_PASSWORD", "")

    # ── URLs base ────────────────────────────────────────────────────────────
    @property
    def base(self) -> str:
        return f"https://api.sienge.com.br/{self.subdominio}/public/api/v1"

    @property
    def base_bulk(self) -> str:
        return f"https://api.sienge.com.br/{self.subdominio}/public/api/bulk-data/v1"

    @property
    def configurado(self) -> bool:
        return bool(self.subdominio and self.usuario and self.senha)

    def _check(self) -> None:
        if not self.configurado:
            raise RuntimeError(
                "Sienge não configurado. Defina SIENGE_SUBDOMAIN, SIENGE_API_USER "
                "e SIENGE_API_PASSWORD no ambiente (.env / Render).")

    # ── GET genérico ─────────────────────────────────────────────────────────
    def get(self, path: str, params: dict | None = None, bulk: bool = False,
            timeout: float = 60) -> httpx.Response:
        """GET cru (devolve a Response, para o chamador inspecionar status/corpo)."""
        self._check()
        url = f"{self.base_bulk if bulk else self.base}/{path.lstrip('/')}"
        return httpx.get(url, params=params, auth=(self.usuario, self.senha),
                         headers={"Accept": "application/json"}, timeout=timeout)

    def get_json(self, path: str, params: dict | None = None, bulk: bool = False):
        r = self.get(path, params=params, bulk=bulk)
        r.raise_for_status()
        return r.json()

    def fetch_orcamento_items(self, building_id: int, sheet_id: int) -> list[dict]:
        """
        Todos os itens da planilha de orçamento (paginado, limit=200).
        Cada item: id, wbsCode, workItemId, description, unitOfMeasure,
        quantity, unitPrice, totalPrice. O `id` casa com o reference_id do
        de-para (== reference_id do Prevision).
        """
        self._check()
        path = f"building-cost-estimations/{building_id}/sheets/{sheet_id}/items"
        itens: list[dict] = []
        offset = 0
        while True:
            body = self.get_json(path, params={"limit": 200, "offset": offset})
            res = body.get("results", []) if isinstance(body, dict) else []
            itens.extend(res)
            total = body.get("resultSetMetadata", {}).get("count", 0) if isinstance(body, dict) else 0
            offset += 200
            if not res or offset >= total:
                break
        return itens

    def ping(self) -> tuple[bool, str]:
        """Testa a autenticação num endpoint leve. Retorna (ok, detalhe)."""
        try:
            r = self.get("enterprises", params={"limit": 1})
        except Exception as exc:  # noqa: BLE001
            return False, f"erro de conexão: {exc}"
        if r.status_code == 200:
            return True, "autenticado"
        if r.status_code in (401, 403):
            return False, f"credencial rejeitada ({r.status_code})"
        return False, f"HTTP {r.status_code}: {r.text[:160]}"
