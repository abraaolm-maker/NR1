"""Testes do COPSOQ Oficial (curta/média/longa) — CLAUDE.md Seção 5.1.1, feature
adicionada em 2026-07-29 a partir do manual COPSOQ Portugal 2013."""

import pytest
from django.contrib.auth import get_user_model

from avaliacoes.forms import AplicacaoForm
from avaliacoes.models import Empresa, GHE, TipoAplicacao, Unidade
from avaliacoes.services.calculo_risco import dominios_da_aplicacao, itens_da_aplicacao
from instrumentos.models import Dominio, Instrumento


@pytest.mark.django_db
def test_profundidade_curta_traz_exatamente_41_itens(aplicacao_copsoq_oficial):
    aplicacao = aplicacao_copsoq_oficial(profundidade="curta")
    dominios = dominios_da_aplicacao(aplicacao)
    total = sum(itens_da_aplicacao(aplicacao, d).count() for d in dominios)
    assert total == 41


@pytest.mark.django_db
def test_profundidade_media_traz_exatamente_76_itens(aplicacao_copsoq_oficial):
    aplicacao = aplicacao_copsoq_oficial(profundidade="media")
    dominios = dominios_da_aplicacao(aplicacao)
    total = sum(itens_da_aplicacao(aplicacao, d).count() for d in dominios)
    assert total == 76


@pytest.mark.django_db
def test_profundidade_longa_traz_todos_os_119_itens(aplicacao_copsoq_oficial):
    aplicacao = aplicacao_copsoq_oficial(profundidade="longa")
    dominios = dominios_da_aplicacao(aplicacao)
    total = sum(itens_da_aplicacao(aplicacao, d).count() for d in dominios)
    assert total == 119


@pytest.mark.django_db
def test_dominio_exclusivo_da_longa_nao_aparece_em_curta(aplicacao_copsoq_oficial):
    """"Variação no trabalho" (VT) só existe na versão longa — não deve nem aparecer
    na lista de domínios de uma Aplicacao curta (não só sem itens, ausente mesmo)."""
    aplicacao = aplicacao_copsoq_oficial(profundidade="curta")
    codigos = {d.codigo for d in dominios_da_aplicacao(aplicacao)}
    assert "VT" not in codigos
    assert "EQ" in codigos  # domínio presente em todas as profundidades


@pytest.mark.django_db
def test_dominio_exclusivo_da_longa_aparece_em_longa(aplicacao_copsoq_oficial):
    aplicacao = aplicacao_copsoq_oficial(profundidade="longa")
    codigos = {d.codigo for d in dominios_da_aplicacao(aplicacao)}
    assert "VT" in codigos


@pytest.mark.django_db
def test_aplicacao_sem_profundidade_nao_filtra_nada(instrumentos_carregados):
    """Instrumentos que não usam profundidade (ex. COPSOQ adaptado) continuam
    trazendo todos os itens, sem exigir nem respeitar o campo."""
    from avaliacoes.models import Aplicacao, CriterioVersao
    from django.core.management import call_command

    call_command("criar_criterio_versao", codigo="v-sem-prof")
    criterio = CriterioVersao.objects.get(codigo="v-sem-prof")
    user = get_user_model().objects.create_user(username="u2", password="x")
    empresa = Empresa.objects.create(nome="E2", cnpj="00.000.000/0009-00")
    unidade = Unidade.objects.create(empresa=empresa, nome="U2")
    ghe = GHE.objects.create(unidade=unidade, nome="G2")
    instrumento = Instrumento.objects.get(codigo="COPSOQ_RR_REVESTIR")
    aplicacao = Aplicacao.objects.create(
        ghe=ghe, instrumento=instrumento, criterio_versao=criterio,
        tipo=TipoAplicacao.ANONIMA, responsavel_aplicador=user,
    )
    dominio = Dominio.objects.get(instrumento=instrumento, codigo="D1")
    assert itens_da_aplicacao(aplicacao, dominio).count() == dominio.itens.count()


@pytest.mark.django_db
def test_form_exige_profundidade_quando_instrumento_usa(criterio_v1):
    user = get_user_model().objects.create_user(username="gestor_form", password="x")
    instrumento = Instrumento.objects.get(codigo="COPSOQ_OFICIAL")

    form = AplicacaoForm(
        data={
            "instrumento": instrumento.pk,
            "criterio_versao": criterio_v1.pk,
            "tipo": "anonima",
            "responsavel_aplicador": user.pk,
            "data_aplicacao": "2026-07-01",
            "profundidade": "",
        },
        usuario_logado=user,
    )

    assert not form.is_valid()
    assert "profundidade" in form.errors


@pytest.mark.django_db
def test_form_aceita_quando_profundidade_preenchida(criterio_v1):
    user = get_user_model().objects.create_user(username="gestor_form2", password="x", is_staff=True)
    instrumento = Instrumento.objects.get(codigo="COPSOQ_OFICIAL")

    form = AplicacaoForm(
        data={
            "instrumento": instrumento.pk,
            "criterio_versao": criterio_v1.pk,
            "tipo": "anonima",
            "responsavel_aplicador": user.pk,
            "data_aplicacao": "2026-07-01",
            "profundidade": "curta",
        },
        usuario_logado=user,
    )

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_form_nao_exige_profundidade_para_instrumento_sem_niveis(criterio_v1):
    user = get_user_model().objects.create_user(username="gestor_form3", password="x", is_staff=True)
    instrumento = Instrumento.objects.get(codigo="COPSOQ_RR_REVESTIR")

    form = AplicacaoForm(
        data={
            "instrumento": instrumento.pk,
            "criterio_versao": criterio_v1.pk,
            "tipo": "anonima",
            "responsavel_aplicador": user.pk,
            "data_aplicacao": "2026-07-01",
            "profundidade": "",
        },
        usuario_logado=user,
    )

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_media_nacional_comparavel_risco_direto(instrumentos_carregados):
    from avaliacoes.services.calculo_risco import media_nacional_comparavel

    dominio = Dominio.objects.get(instrumento__codigo="COPSOQ_OFICIAL", codigo="EQ")
    # bruto 2.48, RISCO (sem inversao), escala 1-5 -> (2.48-1)/4*100
    assert media_nacional_comparavel(dominio) == pytest.approx(37.0, abs=0.05)


@pytest.mark.django_db
def test_media_nacional_comparavel_protetivo_invertido(instrumentos_carregados):
    from avaliacoes.services.calculo_risco import media_nacional_comparavel

    dominio = Dominio.objects.get(instrumento__codigo="COPSOQ_OFICIAL", codigo="AE")
    # bruto 3.90, PROTETIVO -> inverte pra 6-3.90=2.10 -> (2.10-1)/4*100
    assert media_nacional_comparavel(dominio) == pytest.approx(27.5, abs=0.05)


@pytest.mark.django_db
def test_media_nacional_comparavel_none_para_polaridade_mista(instrumentos_carregados):
    from avaliacoes.services.calculo_risco import media_nacional_comparavel

    dominio = Dominio.objects.get(instrumento__codigo="COPSOQ_OFICIAL", codigo="CH")
    assert media_nacional_comparavel(dominio) is None


@pytest.mark.django_db
def test_media_nacional_comparavel_none_sem_referencia_publicada(instrumentos_carregados):
    from avaliacoes.services.calculo_risco import media_nacional_comparavel

    # VT (Variação no trabalho) é exclusiva da longa e o manual nunca a mediu na
    # amostra nacional (Tabela 3 só cobre as 29 subescalas da versão média).
    dominio = Dominio.objects.get(instrumento__codigo="COPSOQ_OFICIAL", codigo="VT")
    assert media_nacional_comparavel(dominio) is None
