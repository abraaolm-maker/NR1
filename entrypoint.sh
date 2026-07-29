#!/bin/sh
# Entrada do container em produção (Render). Roda tudo que precisa acontecer antes de
# aceitar tráfego: migrations, seeds (idempotentes) e o admin inicial — depois sobe o
# Gunicorn. Cada passo de seed usa "|| true" quando o comando original não é idempotente
# (ex.: criar_criterio_versao recusa sobrescrever um código já existente de propósito,
# CLAUDE.md Seção 7.8 — aqui isso só significa "já existe, seguir em frente").
set -e

python manage.py migrate --noinput

python manage.py load_instrumentos seeds/copsoq_rr_revestir.json
python manage.py load_instrumentos seeds/copsoq_oficial.json
python manage.py load_instrumentos seeds/itra.json
python manage.py load_catalogo_acoes seeds/catalogo_acoes.json
python manage.py load_catalogo_acoes seeds/catalogo_acoes_copsoq_oficial.json
python manage.py load_checklist_triangulacao seeds/checklist_triangulacao.json
python manage.py criar_criterio_versao || true

python manage.py criar_admin_do_env

exec gunicorn crarp.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3
