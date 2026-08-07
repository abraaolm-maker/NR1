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
# v1.1: corrige os thresholds do COPSOQ Oficial, que estavam gravados na escala 1-5
# (2,33/3,66) e sendo comparados contra um escore 0-100 — quase todo domínio caía em
# "Elevado" (achado em 2026-08-06). CriterioVersao é imutável (CLAUDE.md Seção 7.8),
# por isso é uma versão nova, não uma edição da v1.0 — Aplicacoes/Relatorios já
# calculados sob a v1.0 continuam citando a v1.0 de propósito (rastreabilidade).
python manage.py criar_criterio_versao --codigo v1.1 --descricao "Corrige thresholds do COPSOQ Oficial (escala 1-5 -> 0-100). Demais parametros identicos a v1.0. Aguardando ratificacao formal do profissional responsavel do PGR antes de uso conclusivo." || true

python manage.py criar_admin_do_env

# --timeout 300: o padrão do Gunicorn é 30s, e a geração de parecer/plano de ação
# via IA (relatorios/services/analise_ia.py e plano_acao_ia.py) chama a Anthropic
# com max_tokens=8192 — pode legitimamente passar de 30s em relatórios com muitos
# domínios, o que fazia o Gunicorn matar o worker no meio da requisição (achado em
# produção, 2026-08-03: "Internal Server Error" ao gerar parecer via IA).
exec gunicorn crarp.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --timeout 300
