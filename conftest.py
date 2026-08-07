"""Fixtures compartilhadas entre avaliacoes/tests.py e relatorios/tests.py."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from avaliacoes.models import (
    GHE,
    Aplicacao,
    CriterioVersao,
    Empresa,
    Respondente,
    Resposta,
    TipoAplicacao,
    Unidade,
)
from instrumentos.models import Dominio, Instrumento


@pytest.fixture
def instrumentos_carregados(db):
    call_command("load_instrumentos", "seeds/copsoq_rr_revestir.json")
    call_command("load_instrumentos", "seeds/copsoq_oficial.json")
    call_command("load_instrumentos", "seeds/itra.json")
    call_command("load_catalogo_acoes", "seeds/catalogo_acoes.json")
    call_command("load_catalogo_acoes", "seeds/catalogo_acoes_copsoq_oficial.json")
    call_command("load_checklist_triangulacao", "seeds/checklist_triangulacao.json")


@pytest.fixture
def criterio_v1(instrumentos_carregados):
    call_command("criar_criterio_versao", codigo="v1.0-test")
    return CriterioVersao.objects.get(codigo="v1.0-test")


@pytest.fixture
def aplicacao_copsoq(criterio_v1):
    user = get_user_model().objects.create_user(username="tecnico", password="x")
    empresa = Empresa.objects.create(nome="Empresa Teste", cnpj="00.000.000/0001-00")
    unidade = Unidade.objects.create(empresa=empresa, nome="Unidade Teste")
    ghe = GHE.objects.create(unidade=unidade, nome="Equipe Teste")
    instrumento = Instrumento.objects.get(codigo="COPSOQ_RR_REVESTIR")
    return Aplicacao.objects.create(
        ghe=ghe,
        instrumento=instrumento,
        criterio_versao=criterio_v1,
        tipo=TipoAplicacao.ANONIMA,
        responsavel_aplicador=user,
    )


@pytest.fixture
def aplicacao_copsoq_oficial(criterio_v1):
    user = get_user_model().objects.create_user(username="tecnico_oficial", password="x")
    empresa = Empresa.objects.create(nome="Empresa Oficial", cnpj="00.000.000/0002-00")
    unidade = Unidade.objects.create(empresa=empresa, nome="Unidade Oficial")
    ghe = GHE.objects.create(unidade=unidade, nome="Equipe Oficial")
    instrumento = Instrumento.objects.get(codigo="COPSOQ_OFICIAL")

    def _criar(profundidade=""):
        return Aplicacao.objects.create(
            ghe=ghe,
            instrumento=instrumento,
            criterio_versao=criterio_v1,
            tipo=TipoAplicacao.ANONIMA,
            responsavel_aplicador=user,
            profundidade=profundidade,
        )

    return _criar


@pytest.fixture
def responder_dominio():
    def _responder(aplicacao, dominio_codigo, valores_por_item, n_respondentes):
        dominio = Dominio.objects.get(instrumento=aplicacao.instrumento, codigo=dominio_codigo)
        for i in range(n_respondentes):
            # `concluido_em` precisa estar preenchido pra contar em calcular_dominio()
            # desde 2026-08-06 (item 9 de SOLICITACOES_PENDENTES.md — respostas de
            # quem não terminou o questionário inteiro nunca entram em nenhum
            # cálculo). Este helper simula "respondeu e terminou", não uma resposta
            # parcial — testes que precisam simular abandono devem criar o
            # Respondente manualmente, sem concluido_em.
            respondente = Respondente.objects.create(
                aplicacao=aplicacao, alias_anonimo=f"Respondente {i}", concluido_em=timezone.now()
            )
            for item in dominio.itens.all():
                Resposta.objects.create(
                    respondente=respondente, item=item, valor_bruto=valores_por_item[item.item_id]
                )
        return dominio

    return _responder
