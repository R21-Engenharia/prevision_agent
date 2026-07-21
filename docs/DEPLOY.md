# Deploy do FVS Dashboard

Três peças, cada uma no seu lugar:

| Peça | Onde | Custo |
|---|---|---|
| Frontend React | Vercel | free (Hobby) |
| API Python | Google Cloud Run | free até 2M req/mês |
| Streamlit (legado) | Streamlit Cloud | free |

Os dados vêm do Supabase e dos arquivos em `data/raw/`, atualizados
diariamente pelos workflows do GitHub Actions.

---

## 1. API no Cloud Run

Pré-requisito: [gcloud CLI](https://cloud.google.com/sdk/docs/install) instalado
e autenticado (`gcloud auth login`).

```bash
# a partir de prevision_agent/
gcloud run deploy fvs-api \
  --source . \
  --region southamerica-east1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --set-env-vars "SUPABASE_URL=...,SUPABASE_KEY=...,FVS_ORIGENS=https://SEU-APP.vercel.app"
```

`--allow-unauthenticated` libera o *endpoint*, não os dados: a própria API exige
token Supabase em toda rota de dados (ver `api/auth.py`).

A região `southamerica-east1` (São Paulo) reduz a latência para as obras.

### Variáveis obrigatórias

| Variável | Efeito se faltar |
|---|---|
| `SUPABASE_URL` | API responde 503 em tudo (falha fechada) |
| `SUPABASE_KEY` | idem — use a chave **anon**, nunca a `service_role` |
| `FVS_ORIGENS` | o navegador bloqueia o frontend por CORS |

### Atualização dos dados

Os arquivos de `data/raw/` são **embarcados na imagem**. A coleta diária commita
dados novos no repositório, mas o container só enxerga isso após um novo deploy.
Configure um trigger de build a cada push em `master`, ou rode o comando acima
periodicamente. Sem isso, a API serve o dado da data do deploy.

---

## 2. Frontend na Vercel

1. Importar o repositório
2. **Root Directory: `web`**
3. Variáveis de ambiente:

```
VITE_SUPABASE_URL=https://xxxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
VITE_ALLOWED_DOMAINS=r21empreendimentos.com
```

4. Editar `web/vercel.json` trocando o placeholder pela URL do Cloud Run:

```json
"destination": "https://fvs-api-xxxxx.a.run.app/api/:caminho*"
```

O rewrite faz o navegador enxergar tudo na mesma origem — não há CORS em
produção, e o `FVS_ORIGENS` cobre chamadas diretas.

Depois do primeiro deploy, volte ao Cloud Run e ajuste `FVS_ORIGENS` com a URL
real da Vercel.

---

## 3. Workflows (GitHub Actions)

| Workflow | Quando | Secrets |
|---|---|---|
| `snapshot_diario.yml` | 06:10 BRT, diário | `INMETA_EMAIL`, `INMETA_SENHA`, `SUPABASE_URL`, `SUPABASE_KEY` |
| `update_prevision.yml` | 06:00 BRT, dias úteis | `PREVISION_TOKEN` |
| `build_api.yml` | a cada push na API | nenhum |

O snapshot diário tem um efeito colateral útil: como escreve no Supabase todo
dia, ele impede que o projeto free entre em pausa por inatividade — que foi o
que derrubou o app em 21/07/2026.

---

## Verificação pós-deploy

```bash
curl https://SUA-API/api/health                    # {"ok":true}
curl https://SUA-API/api/overview?obra=Cape%20Town%20Residence   # 401 sem token — correto
```

Um 401 aqui é sinal de que a proteção está ativa. Se vier dado, a API está
aberta: confira `FVS_DEV_NO_AUTH`, que **nunca** deve estar definida em produção.
