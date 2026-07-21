"""
core/inmeta_client.py
=====================
Client InMeta REST API — autenticacao JWT + coleta de inspecoes FVS.
Baseado no codigo validado na Fase 5 (modulo=SERVICO confirmado).
"""

from __future__ import annotations
import time
import httpx


class InMetaClient:
    """
    Client para a API InMeta.

    Uso:
        client = InMetaClient(base_url, email, senha)
        insps  = client.fetch_inspections(alvo_id)
    """

    TOKEN_TTL = 3600  # segundos antes de renovar o JWT

    def __init__(self, base_url: str, email: str, senha: str) -> None:
        self.base_url  = base_url.rstrip("/")
        self.email     = email
        self.senha     = senha
        self._token: str | None = None
        self._token_ts: float = 0.0

    # ── Autenticacao ─────────────────────────────────────────────────────────

    def _ensure_token(self) -> None:
        """Renova o JWT se expirado ou ausente."""
        if self._token and (time.time() - self._token_ts) < self.TOKEN_TTL:
            return
        r = httpx.post(
            f"{self.base_url}/api/v1/token",
            json={"email": self.email, "senha": self.senha},
            timeout=15,
        )
        r.raise_for_status()
        self._token    = r.json()["content"]["token"]
        self._token_ts = time.time()

    @property
    def _headers(self) -> dict[str, str]:
        self._ensure_token()
        return {"Authorization": f"Bearer {self._token}"}

    # ── Endpoints ────────────────────────────────────────────────────────────

    def fetch_inspections(self, alvo_id: str) -> list[dict]:
        """
        Retorna todas as inspecoes FVS atuais do alvo.
        Usa modulo=SERVICO (descoberta Fase 5).
        """
        r = httpx.get(
            f"{self.base_url}/api/v1/alvos/{alvo_id}/inspecoes/atuais",
            headers=self._headers,
            params={"modulo": "SERVICO"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("content", []) if isinstance(data, dict) else data

    def ping(self) -> bool:
        """Verifica conectividade (sem autenticacao)."""
        try:
            r = httpx.get(f"{self.base_url}/api/ping", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def fetch_diario_obra(self, alvo_id: str) -> list[dict]:
        """
        Retorna os RDOs do Diario de Obra da obra informada.

        Endpoint: GET /api/inspecoes?modulo=DIARIO_OBRA&alvoId={alvo_id}
        Campos uteis: dataInspecao, classificacaoTempo, condicaoTrabalho,
                      alvo.nome, modelo.nome, codigo, _id

        ATENCAO: o endpoint IGNORA o parametro alvoId e devolve os RDOs de
        TODAS as obras da conta (verificado em 21/07/2026: as duas obras
        retornaram os mesmos 1102 registros, contendo ainda uma terceira obra
        que nem faz parte deste app). Por isso o filtro por alvo e refeito
        aqui, sobre a resposta — sem ele, a Condicao do Tempo mistura obras.
        """
        r = httpx.get(
            f"{self.base_url}/api/inspecoes",
            headers=self._headers,
            params={"modulo": "DIARIO_OBRA", "alvoId": alvo_id},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()

        if isinstance(data, dict) and "content" in data:
            content = data["content"]
            registros = content.get("list", []) if isinstance(content, dict) else content
        else:
            registros = data
        if not isinstance(registros, list):
            return []

        return [r_ for r_ in registros if self._e_da_obra(r_, alvo_id)]

    @staticmethod
    def _e_da_obra(rdo: dict, alvo_id: str) -> bool:
        """True se o RDO pertence ao alvo informado."""
        alvo = rdo.get("alvo")
        if isinstance(alvo, dict):
            return str(alvo.get("_id") or alvo.get("id") or "") == str(alvo_id)
        return str(alvo or "") == str(alvo_id)

    def whoami(self) -> dict:
        """Retorna contexto do usuario autenticado."""
        r = httpx.get(
            f"{self.base_url}/api/context",
            headers=self._headers,
            params={"modulo": "SERVICO"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
