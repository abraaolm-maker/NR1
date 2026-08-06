FROM python:3.13-slim

# Deploy via Docker porque o PDF depende de binario nativo do Chromium
# (Playwright), que buildpacks de PaaS padrao como Render nao instalam
# (CLAUDE.md / PLANO_ACAO_RELATORIO.md Secao 3.7 — migracao de motor de
# renderizacao WeasyPrint -> Chromium+Paged.js em 2026-08-05).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=crarp.settings

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala o binario do Chromium + todas as dependencias de sistema que ele
# precisa (libnss, libatk, fontes etc.) — o --with-deps cobre isso via apt
# automaticamente nesta base Debian.
RUN playwright install --with-deps chromium

COPY . .
RUN chmod +x entrypoint.sh

# collectstatic não precisa de banco nem de env vars secretas — SECRET_KEY tem um
# default de desenvolvimento que serve só pra esse passo de build.
RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["./entrypoint.sh"]
