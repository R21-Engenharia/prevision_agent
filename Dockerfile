# API FVS — imagem para Cloud Run / qualquer runtime de container.
#
# Os dados (data/raw, ~18 MB) sao embarcados na imagem. Como a coleta diaria
# commita dados novos no repositorio, o deploy deve ser refeito a cada push
# para o container nao servir dado congelado — ver docs/DEPLOY.md.

FROM python:3.11-slim

# libexpat1 e libgomp1: exigidos pelo chromium embutido no kaleido, usado para
# renderizar os graficos do PDF executivo. Sem eles a exportacao em PDF falha
# em runtime — o resto da API funciona, o que tornaria o defeito dificil de notar.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libexpat1 \
        libgomp1 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencias primeiro: essa camada so e reconstruida quando requirements muda
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Codigo e dados
COPY api/ ./api/
COPY fvs_dashboard/ ./fvs_dashboard/
COPY data/raw/ ./data/raw/

# Cloud Run injeta PORT; 8080 e o padrao quando roda local
ENV PORT=8080
EXPOSE 8080

# Verifica na build que o kaleido carrega — falha aqui, e nao no primeiro PDF
RUN python -c "import kaleido, plotly, pandas, fastapi; print('deps ok')"

CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT}
