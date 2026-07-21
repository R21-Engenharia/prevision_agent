# FVS Dashboard — Web (React)

Frontend do FVS Dashboard em React + TypeScript (Vite), consumindo a API
Python (`api/main.py`) que expõe a lógica já existente (Prevision + InMeta).

Fase atual: **Visão Geral migrada** com dados reais. As demais telas seguem
no Streamlit até serem portadas.

---

## Rodar localmente

São dois processos. A partir de `prevision_agent/`:

**1. API (porta 8001)**

```bash
# desenvolvimento — sem exigir login
FVS_DEV_NO_AUTH=1 python -m uvicorn api.main:app --reload --port 8001

# como roda em produção — exige token Supabase válido
python -m uvicorn api.main:app --port 8001
```

**2. Frontend (porta 5173)**

```bash
cd web
npm install
npm run dev
```

Abrir http://localhost:5173 — o Vite faz proxy de `/api` para a porta 8001
(sem CORS em desenvolvimento).

> **Atenção — Google Drive:** `npm install` falha nesta pasta sincronizada
> (`EBADF`), porque o `node_modules` tem milhares de arquivos. Clone/copie o
> projeto para um caminho local (ex.: `C:\Users\<voce>\dev\r21-fvs-web`) para
> desenvolver, ou rode a instalação fora do Drive.

---

## Estrutura

```
src/
  lib/api.ts              cliente HTTP + tipos da API
  components/Shell.tsx    casca do app (navegação, topbar, seletor de obra, tema)
  components/Donut.tsx    donut de status
  components/EvolucaoChart.tsx   série mensal (recharts)
  components/CountUp.tsx  animação de números
  pages/VisaoGeral.tsx    tela Visão Geral
  index.css               design system (tokens, claro/escuro)
```

## Autenticação (Supabase)

Usa o mesmo Supabase do app Streamlit. Copie `.env.example` para `.env.local` e
preencha com os valores que já estão nos Secrets do Streamlit Cloud:

```
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
VITE_ALLOWED_DOMAINS=r21empreendimentos.com
```

Regras de acesso (espelham `auth/supabase_auth.py`): quem está na tabela
`authorized_emails` entra com o papel cadastrado; quem tem e-mail de um domínio
liberado entra como `viewer`; os demais são recusados após o login.

**A API também é protegida.** Toda rota de dados exige o token Supabase no
header `Authorization`. A API falha fechada: sem `SUPABASE_URL`/`SUPABASE_KEY`
ela responde 503 em vez de servir dados sem autenticação. Para desenvolver
localmente sem login, use `FVS_DEV_NO_AUTH=1` — **nunca em produção**.

Sem as variáveis `VITE_*`, o frontend roda em modo de desenvolvimento (sem tela
de login), indicado na barra lateral como "modo dev · sem login".

## Design system

Tokens CSS em `src/index.css`. Neutros frios + vermelho R21 (`--accent`) como
único acento; dados em fonte monoespaçada com `tabular-nums`. Tema claro/escuro
via `data-theme` no `<html>` (persistido em `localStorage`, padrão = sistema).

## Build

```bash
npm run build     # gera dist/
npm run preview   # serve o build
```

Deploy sugerido: `dist/` em Vercel/Netlify + API Python num serviço próprio
(Render/Railway/Fly), ajustando a URL da API para produção.
