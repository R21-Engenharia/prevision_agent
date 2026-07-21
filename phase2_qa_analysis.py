"""
Análise rápida das QualityAssociations — sem Activities.
Coleta os dois projetos e gera análise estrutural das FVS esperadas.
"""
import io, os, sys, json, pathlib
from collections import Counter, defaultdict
from datetime import datetime

os.environ.setdefault("PYTHONUTF8", "1")
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from config.settings import load_config
from client.graphql_client import GraphQLClient
from collectors.operational_collector import OperationalCollector

PROJECTS = [
    {"id": "10223", "name": "CAPE TOWN RESIDENCE"},
    {"id": "18992", "name": "HOLMES RESIDENCE"},
]

RAW_DIR = pathlib.Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)


def parse_reference(name: str):
    """
    Extrai modelo FVS e local de partnerReferenceName.
    'FVS 02.04.01 - Execução de Concretagem  | Torre única - 06º Pavimento'
    -> ('FVS 02.04.01 - Execução de Concretagem', 'Torre única - 06º Pavimento')
    """
    parts = name.split(" | ", 1)
    model = parts[0].strip()
    local = parts[1].strip() if len(parts) > 1 else ""
    return model, local


def analyze_qa(project_id: str, project_name: str,
               floors: list, qa_list: list, services: list):
    print(f"\n{'='*65}")
    print(f"  ANALISE QA: {project_name}")
    print(f"{'='*65}")

    # ── Floors ──────────────────────────────────────────────────────────────
    floors_with_qa = [f for f in floors if f.get("hasQualityLocalsAssociations")]
    total_acts = sum(
        f.get("activitiesPage", {}).get("totalCount", 0) for f in floors
    )

    print(f"\n[Lotes (Floors)]")
    print(f"  Total: {len(floors)}")
    print(f"  Com locais de qualidade: {len(floors_with_qa)}/{len(floors)}")
    print(f"  Total atividades (estimado): {total_acts}")

    # ── QualityAssociations ──────────────────────────────────────────────────
    print(f"\n[QualityAssociations]")
    print(f"  Total: {len(qa_list)}")

    unique_activity_ids = {str(a["itemId"]) for a in qa_list}
    print(f"  Activities unicas cobertas: {len(unique_activity_ids)}")
    print(f"  Coverage estimada: {len(unique_activity_ids)}/{total_acts} "
          f"= {len(unique_activity_ids)/total_acts*100:.1f}%" if total_acts else "  N/A")

    # eapTypes
    eap_types = Counter(a.get("eapType") for a in qa_list)
    print(f"  eapType: {dict(eap_types)}")

    # ── Parse dos modelos FVS e locais ───────────────────────────────────────
    fvs_models = Counter()
    fvs_locals = Counter()
    acts_per_model = defaultdict(set)
    model_per_act = defaultdict(set)

    for a in qa_list:
        name = a.get("partnerReferenceName", "")
        act_id = str(a["itemId"])
        model, local = parse_reference(name)
        fvs_models[model] += 1
        fvs_locals[local] += 1
        acts_per_model[model].add(act_id)
        model_per_act[act_id].add(model)

    print(f"\n[Modelos FVS]")
    print(f"  Tipos distintos: {len(fvs_models)}")
    print(f"  Top 15 por frequência:")
    for model, cnt in fvs_models.most_common(15):
        n_acts = len(acts_per_model[model])
        print(f"    {cnt:5d}x | {n_acts:4d} atividades | {model[:60]}")

    print(f"\n[Locais / Apartamentos]")
    print(f"  Locais distintos: {len(fvs_locals)}")
    print(f"  Top 10:")
    for local, cnt in fvs_locals.most_common(10):
        print(f"    {cnt:5d}x | {local[:60]}")

    # ── Distribuição de FVS por atividade ───────────────────────────────────
    fvs_per_act = Counter(len(v) for v in model_per_act.values())
    print(f"\n[FVS por Atividade]")
    print(f"  Atividades com apenas 1 tipo de FVS: "
          f"{fvs_per_act.get(1, 0)}")
    print(f"  Atividades com 2 tipos: {fvs_per_act.get(2, 0)}")
    print(f"  Atividades com 3+ tipos: "
          f"{sum(v for k, v in fvs_per_act.items() if k >= 3)}")
    most_fvs = max(fvs_per_act.keys()) if fvs_per_act else 0
    print(f"  Maximo de tipos por atividade: {most_fvs}")

    # ── Services ────────────────────────────────────────────────────────────
    if services:
        svcs_with_qa = [s for s in services if s.get("hasQualityAssociations")]
        svcs_with_models = [s for s in services if s.get("hasQualityModelsAssociations")]
        print(f"\n[Pacotes de Trabalho]")
        print(f"  Total: {len(services)}")
        print(f"  Com quality associations: {len(svcs_with_qa)}")
        print(f"  Com quality models: {len(svcs_with_models)}")

    # ── Consolidado ──────────────────────────────────────────────────────────
    result = {
        "project_id": project_id,
        "project_name": project_name,
        "analyzed_at": datetime.now().isoformat(),
        "floors_total": len(floors),
        "floors_with_quality": len(floors_with_qa),
        "activities_estimated_total": total_acts,
        "quality_associations": len(qa_list),
        "unique_activities_covered": len(unique_activity_ids),
        "coverage_estimated_pct": round(
            len(unique_activity_ids) / total_acts * 100, 2
        ) if total_acts else None,
        "fvs_model_types": len(fvs_models),
        "fvs_local_types": len(fvs_locals),
        "top_fvs_models": dict(fvs_models.most_common(20)),
        "top_fvs_locals": dict(fvs_locals.most_common(20)),
    }
    return result


def main():
    config = load_config()
    all_results = {}

    with GraphQLClient(config) as client:
        col = OperationalCollector(client, company_id=479, page_size=50)

        for proj in PROJECTS:
            pid = proj["id"]
            pname = proj["name"]

            print(f"\nColetando {pname}...", flush=True)
            floors, _, _ = col.collect_floors(pid)
            qa_list, _ = col.collect_quality_associations(pid)
            services, _ = col.collect_services(pid)

            # Salva brutos
            raw = {"project_id": pid, "project_name": pname,
                   "floors": floors, "quality_associations": qa_list,
                   "services": services}
            raw_path = RAW_DIR / f"{pid}_qa_raw.json"
            raw_path.write_text(
                json.dumps(raw, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            print(f"  Salvo: {raw_path}", flush=True)

            result = analyze_qa(pid, pname, floors, qa_list, services)
            all_results[pid] = result

    # ── Resumo final ─────────────────────────────────────────────────────────
    print(f"\n\n{'='*65}")
    print("RESUMO CONSOLIDADO")
    print(f"{'='*65}")
    for pid, r in all_results.items():
        print(f"\n{r['project_name']}:")
        print(f"  QA coletadas: {r['quality_associations']}")
        print(f"  Activities cobertas: {r['unique_activities_covered']}")
        print(f"  Coverage estimada: {r['coverage_estimated_pct']}%")
        print(f"  Modelos FVS distintos: {r['fvs_model_types']}")

    out_path = pathlib.Path("data/FASE2_QA_ANALYSIS.json")
    out_path.write_text(
        json.dumps(all_results, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\nSalvo em: {out_path}")

    print(f"\n{'='*65}")
    print("NOTA: formStatus das FVS indisponivel (InMeta sync quebrado).")
    print("Benchmark (314+68 FVS preenchidas) nao pode ser validado via API.")
    print("Para restaurar: renovar credenciais InMeta no painel Prevision.")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
