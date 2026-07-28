FROM python:3.13-slim

# Libs nativas exigidas pelo WeasyPrint (Pango, Cairo, GDK-Pixbuf, fontconfig) — o
# buildpack Python padrão de PaaS como Render não instala isso, por isso o deploy
# precisa ser via Docker (CLAUDE.md — decisão registrada na conversa de deploy).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    fonts-dejavu-core \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=crarp.settings

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

# collectstatic não precisa de banco nem de env vars secretas — SECRET_KEY tem um
# default de desenvolvimento que serve só pra esse passo de build.
RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["./entrypoint.sh"]
