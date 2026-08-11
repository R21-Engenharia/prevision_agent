"""
scripts/coletar_rdo_efetivo.py
==============================
Camada 1 da RUP real — NUMERADOR (Hh por FVS), so com InMeta.

Fluxo:
  1. Lista os RDOs de cada obra (GET /api/inspecoes?modulo=DIARIO_OBRA).
  2. Para cada RDO, puxa o detalhe preenchido e faz cache em disco
     (data/raw/rdo_detalhe/{id}.json) — rerun fica barato.
  3. Extrai os registros de efetivo por servico (rup.parser_rdo) e agrega
     por codigo FVS (rup.agregador).
  4. Salva data/rup_camada1.json e imprime uma prova com um servico real.

Executar (a partir de prevision_agent/):
    python scripts/coletar_rdo_efetivo.py                    # tudo, com cache
    python scripts/coletar_rdo_efetivo.py --limit 40         # amostra p/ testar
    python scripts/coletar_rdo_efetivo.py --obra "Cape Town Residence"
    python scripts/coletar_rdo_efetivo.py --refresh          # ignora o cache
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

sys.stdout.reconfigure(encoding="utf-8")

from fvs_dashboard.core.data_manager import OBRAS
from fvs_dashboard.core.inmeta_client import InMetaClient
from rup.parser_rdo import registros_do_rdo
from rup.agregador import agregar_por_fvs

CACHE_DIR = _ROOT / "data" / "raw" / "rdo_detalhe"
SAIDA     = _ROOT / "data" / "rup_camada1.json"


def _client() -> InMetaClient:
    return InMetaClient(
        base_url=os.getenv("INMETA_BASE_URL", "https://api.inmeta.com.br"),
        email=os.getenv("INMETA_EMAIL", ""),
        senha=os.getenv("INMETA_SENHA", ""),
    )


def detalhe_cacheado(cli: InMetaClient, rid: str, refresh: bool) -> dict | None:
    """
    Detalhe do RDO com cache em disco. Resiliente a instabilidade do InMeta:
    tenta ate 4 vezes em erro de servidor (5xx) com backoff; se persistir,
    retorna None (RDO pulado) em vez de abortar a varredura toda.
    """
    f = CACHE_DIR / f"{rid}.json"
    if f.exists() and not refresh:
        return json.loads(f.read_text(encoding="utf-8"))
    for tentativa in range(4):
        try:
            det = cli.fetch_diario_detalhe(rid)
            f.write_text(json.dumps(det, ensure_ascii=False), encoding="utf-8")
            return det
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise
            time.sleep(2 * (tentativa + 1))
        except (httpx.TransportError, httpx.TimeoutException):
            time.sleep(2 * (tentativa + 1))
    print(f"    (RDO {rid} pulado — InMeta instavel apos 4 tentativas)", flush=True)
    return None


def coletar(obras: list[str], limit: int | None, refresh: bool) -> list[dict]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cli = _client()
    registros: list[dict] = []

    for obra in obras:
        alvo = OBRAS[obra]["inmeta_id"]
        rdos = cli.fetch_diario_obra(alvo)
        if limit:
            rdos = rdos[:limit]
        print(f"\n{obra}: {len(rdos)} RDOs")
        vazios = 0
        for i, rdo in enumerate(rdos, 1):
            det = detalhe_cacheado(cli, rdo["_id"], refresh)
            if det is None:
                continue
            regs = registros_do_rdo(det, obra)
            if not regs:
                vazios += 1
            registros.extend(regs)
            if i % 25 == 0 or i == len(rdos):
                print(f"  {i}/{len(rdos)} RDOs · {len(registros)} registros", flush=True)
        print(f"  ({vazios} RDOs sem servico controlado com FVS)")
    return registros


def prova(agregado: list[dict]) -> None:
    if not agregado:
        print("\n(sem dados agregados)")
        return
    print("\n" + "=" * 68)
    print("  CAMADA 1 — Hh por FVS (numerador da RUP)")
    print("=" * 68)
    print(f"{'FVS':>10}  {'Hh':>8}  {'dias':>4}  {'efet':>4}  {'pav':>3}  serviço")
    for a in agregado[:12]:
        print(f"{a['fvs_codigo']:>10}  {a['hh_total']:>8.1f}  "
              f"{a['dias_trabalhados']:>4}  {a['efetivo_medio_dia']:>4.1f}  "
              f"{a['n_pavimentos']:>3}  {a['fvs_nome'][:44]}")

    top = agregado[0]
    print("\n" + "-" * 68)
    print(f"DETALHE — {top['fvs_codigo']} · {top['fvs_nome']}")
    print(f"  obra ................ {top['obra']}")
    print(f"  Hh acumulado ........ {top['hh_total']} h")
    print(f"  dias trabalhados .... {top['dias_trabalhados']}")
    print(f"  efetivo medio/dia ... {top['efetivo_medio_dia']}")
    print(f"  pavimentos .......... {top['n_pavimentos']}")
    print(f"  % compartilhado ..... {top['pct_compartilhado']}%")
    print(f"  Hh por funcao:")
    for f, h in top["hh_por_funcao"].items():
        print(f"      {f:<28} {h:>8.1f} h")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--obra", help="uma obra especifica")
    ap.add_argument("--limit", type=int, help="max RDOs por obra (teste)")
    ap.add_argument("--refresh", action="store_true", help="ignora cache")
    ap.add_argument("--supabase", action="store_true",
                    help="grava a Camada 1 no Supabase (tabela rup_hh_fvs)")
    args = ap.parse_args()

    obras = [args.obra] if args.obra else list(OBRAS)
    registros = coletar(obras, args.limit, args.refresh)
    agregado = agregar_por_fvs(registros)

    SAIDA.write_text(json.dumps({
        "registros": len(registros),
        "fvs": agregado,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {len(registros)} registros · {len(agregado)} FVS · salvo em {SAIDA.name}")

    if args.supabase:
        from rup.persistencia import salvar_camada1
        n = salvar_camada1(agregado)
        print(f"→ {n} linhas gravadas no Supabase (rup_hh_fvs)")

    prova(agregado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
