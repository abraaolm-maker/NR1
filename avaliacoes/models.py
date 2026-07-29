import uuid

from django.conf import settings
from django.db import models

from instrumentos.models import Dominio, Instrumento, Item

# Fonte única (CLAUDE.md Seção 7.8): os defaults de CriterioVersao vêm literalmente das
# constantes do risk_engine.py, nunca de um valor duplicado à mão aqui.
from .risk_engine_lib.risk_engine import (
    LIMIAR_EVENTO_GRAVE,
    LIMITE_BAIXO_DEFAULT,
    LIMITE_ELEVADO_DEFAULT,
    N_MINIMO_RESPONDENTES,
    PREVALENCIA_P1,
    PREVALENCIA_P2,
)


# ---------------------------------------------------------------------------
# Empresa / Unidade / GHE
# ---------------------------------------------------------------------------

class Empresa(models.Model):
    nome = models.CharField(max_length=200)
    cnpj = models.CharField(max_length=18, unique=True, verbose_name="CNPJ")
    gestor = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="empresa_gerenciada",
        verbose_name="Gestor responsável",
        help_text="Usuário que acessa o painel em nome desta empresa — 1 gestor por empresa no "
        "MVP (CLAUDE.md Seção 6.8). Criado pelo admin a partir do detalhe da Empresa.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.nome


class Unidade(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="unidades")
    nome = models.CharField(max_length=200)
    cnpj = models.CharField(
        max_length=18,
        blank=True,
        verbose_name="CNPJ",
        help_text="Preencher se a unidade/filial tiver CNPJ próprio.",
    )
    endereco = models.TextField(blank=True, verbose_name="Endereço")
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.nome} ({self.empresa.nome})"


class Funcao(models.Model):
    unidade = models.ForeignKey(Unidade, on_delete=models.CASCADE, related_name="funcoes")
    nome = models.CharField(max_length=150)
    descricao = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.nome


class GHE(models.Model):
    """Grupo Homogêneo de Exposição."""

    unidade = models.ForeignKey(Unidade, on_delete=models.CASCADE, related_name="ghes")
    nome = models.CharField(max_length=200)
    setor = models.CharField(max_length=150, blank=True)
    funcoes = models.ManyToManyField(Funcao, related_name="ghes", blank=True, verbose_name="Funções")
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.nome} — {self.unidade}"


class TipoRegistroErgonomico(models.TextChoices):
    AEP = "aep", "Avaliação Ergonômica Preliminar"
    AET = "aet", "Análise Ergonômica do Trabalho"


class RegistroErgonomico(models.Model):
    """Referência mínima ao vínculo com a NR-17 exigido antes da coleta (CLAUDE.md
    Seção 6, passo 2). Não implementa o workflow completo de AEP/AET — só guarda a
    referência agora para não exigir uma migration dolorosa depois, quando já existirem
    Aplicacoes de verdade ligadas a GHEs sem esse dado."""

    ghe = models.ForeignKey(GHE, on_delete=models.CASCADE, related_name="registros_ergonomicos")
    tipo = models.CharField(max_length=5, choices=TipoRegistroErgonomico.choices)
    data_registro = models.DateField()
    responsavel_tecnico = models.CharField(max_length=200)
    referencia = models.CharField(
        max_length=200,
        blank=True,
        help_text="Nº do documento, link ou identificador do registro AEP/AET.",
    )
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_registro"]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} @ {self.ghe} ({self.data_registro})"


class Perigo(models.Model):
    """Catálogo de perigos psicossociais (lista oficial do Guia MTE).

    Sem seed JSON entregue para esta lista (diferente de COPSOQ/ITRA) — cadastro é
    manual via Django Admin (CLAUDE.md Etapa 7.1)."""

    nome = models.CharField(max_length=200, unique=True)
    categoria = models.CharField(
        max_length=100, blank=True, help_text="Ex.: organização do trabalho, relações socioprofissionais."
    )
    descricao = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Perigos"

    def __str__(self) -> str:
        return self.nome


class PerigoIdentificado(models.Model):
    """Registro de que um perigo foi identificado num GHE, ANTES da aplicação do
    questionário (CLAUDE.md Seção 3, princípio 5)."""

    ghe = models.ForeignKey(GHE, on_delete=models.CASCADE, related_name="perigos_identificados")
    perigo = models.ForeignKey(Perigo, on_delete=models.PROTECT, related_name="identificacoes")
    identificado_em = models.DateTimeField(auto_now_add=True)
    identificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    observacao = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ghe", "perigo"], name="uniq_perigo_por_ghe")
        ]

    def __str__(self) -> str:
        return f"{self.perigo} @ {self.ghe}"


class TipoIndicadorIndireto(models.TextChoices):
    ABSENTEISMO = "absenteismo", "Absenteísmo acima da média"
    TURNOVER = "turnover", "Turnover acima da média"
    CAT_CID_F = "cat_cid_f", "CAT/CID-F relacionado"
    CHECKLIST_NAO_CONFORME = "checklist_nao_conforme", "Checklist observacional não conforme"
    RELATO_ENTREVISTA = "relato_entrevista", "Relato coerente na entrevista com a liderança"


class IndicadorIndireto(models.Model):
    """Evidência complementar (CLAUDE.md Seção 7.5) que alimenta o cálculo de
    `evidencias_convergentes`. Gap real da Seção 4 original — registrado na Seção 4.2
    do CLAUDE.md. Sem este model não há como calcular a probabilidade de um risco além
    do caso de evento grave, nem montar o payload de "indicadores indiretos" que a
    Seção 8.1 exige mandar pra IA."""

    ghe = models.ForeignKey(GHE, on_delete=models.CASCADE, related_name="indicadores_indiretos")
    tipo = models.CharField(max_length=30, choices=TipoIndicadorIndireto.choices)
    periodo_referencia = models.DateField(help_text="Data de referência do período observado.")
    descricao = models.TextField(help_text="O que foi observado/registrado.")
    dominio_relacionado = models.ForeignKey(
        Dominio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="indicadores_indiretos",
        help_text="Vazio se o indicador vale pro GHE inteiro, sem apontar um domínio específico.",
    )
    convergente = models.BooleanField(
        default=True,
        help_text="Desmarcar permite ao profissional responsável registrar o indicador sem "
        "contá-lo como evidência convergente num cálculo específico.",
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} @ {self.ghe} ({self.periodo_referencia})"


# ---------------------------------------------------------------------------
# Critério de risco versionado (CLAUDE.md Seção 7.8)
# ---------------------------------------------------------------------------

class StatusCriterioVersao(models.TextChoices):
    """CLAUDE.md Seção 7.3, princípio 9: os cortes (exceto EACT) precisam de
    ratificação formal do profissional responsável antes de uso conclusivo. Por
    consistência interna, a mesma exigência vale para o COPSOQ — os dois instrumentos
    convivem no mesmo relatório, então nenhum dos dois nasce "vigente/definitivo"."""

    AGUARDANDO_RATIFICACAO = (
        "aguardando_ratificação_profissional_responsável",
        "Aguardando ratificação do profissional responsável",
    )
    RATIFICADO = "ratificado", "Ratificado pelo profissional responsável"


class CriterioVersao(models.Model):
    """Snapshot IMUTÁVEL de todo parâmetro de cálculo de risco necessário pra Seção 7
    do CLAUDE.md:

    - 7.3 thresholds por domínio/subescala — `thresholds_por_dominio` (vem dos seeds,
      já carregados em instrumentos.Dominio no momento em que esta versão é criada).
    - 7.4 mapeamento de severidade — `severidade_por_classificacao`.
    - 7.5 limiar de evento grave — `limiar_evento_grave`.
    - 7.6 matriz de risco (9 combinações) + prazos por banda — `matriz_risco`.
    - 7.7 N mínimo de confidencialidade — `n_minimo_respondentes`.

    Os campos 7.4/7.5/7.6 devem ser construídos A PARTIR das constantes de
    risk_engine.py (SEVERIDADE_POR_CLASSIFICACAO, LIMIAR_EVENTO_GRAVE, MATRIZ_RISCO,
    PRAZO_DIAS_POR_BANDA, N_MINIMO_RESPONDENTES) — nunca reimplementadas/redigitadas
    aqui. Ver management command `criar_criterio_versao`. Se essas constantes
    mudarem no risk_engine.py, isso deve gerar uma NOVA versão (ex. v1.1), nunca uma
    edição silenciosa de uma versão existente — é isso que garante que um Relatorio
    antigo continue citando exatamente o critério com que foi calculado."""

    codigo = models.CharField(max_length=50, unique=True, help_text='Ex.: "v1.0".')
    descricao = models.TextField(blank=True)
    ativo = models.BooleanField(
        default=True, help_text="Se esta versão está disponível para novas Aplicacoes."
    )

    status = models.CharField(
        max_length=60,
        choices=StatusCriterioVersao.choices,
        default=StatusCriterioVersao.AGUARDANDO_RATIFICACAO,
    )
    ratificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    ratificado_em = models.DateTimeField(null=True, blank=True)

    thresholds_por_dominio = models.JSONField(
        help_text='{"<instrumento_codigo>": {"<dominio_codigo>": {"baixo_max": x, "moderado_max": y}}}'
    )
    severidade_por_classificacao = models.JSONField(
        default=dict,
        help_text='{"Baixo": 1, "Moderado": 2, "Elevado": 3} — espelha '
        "risk_engine.SEVERIDADE_POR_CLASSIFICACAO.",
    )
    matriz_risco = models.JSONField(
        help_text='Lista das 9 combinações {"severidade": s, "probabilidade": p, '
        '"banda": "...", "prazo_dias": n} — espelha risk_engine.MATRIZ_RISCO + '
        "PRAZO_DIAS_POR_BANDA."
    )
    n_minimo_respondentes = models.PositiveSmallIntegerField(default=N_MINIMO_RESPONDENTES)
    limiar_evento_grave = models.PositiveSmallIntegerField(default=LIMIAR_EVENTO_GRAVE)

    limite_baixo = models.DecimalField(
        max_digits=5, decimal_places=2, default=LIMITE_BAIXO_DEFAULT,
        verbose_name="Limite máximo — Baixo",
        help_text="Escore 0–100 até este valor é classificado como Baixo.",
    )
    limite_elevado = models.DecimalField(
        max_digits=5, decimal_places=2, default=LIMITE_ELEVADO_DEFAULT,
        verbose_name="Limite mínimo — Elevado",
        help_text="Escore 0–100 a partir deste valor é classificado como Elevado.",
    )
    prevalencia_p1 = models.DecimalField(
        max_digits=3, decimal_places=2, default=PREVALENCIA_P1,
        verbose_name="Prevalência P1",
        help_text="Percentual mínimo de respondentes na faixa elevada para classificar como P1.",
    )
    prevalencia_p2 = models.DecimalField(
        max_digits=3, decimal_places=2, default=PREVALENCIA_P2,
        verbose_name="Prevalência P2",
        help_text="Percentual mínimo de respondentes na faixa elevada para classificar como P2.",
    )
    periodo_referencia = models.CharField(
        max_length=100, default="Últimos 3 meses", blank=True,
        verbose_name="Período de referência",
    )

    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.codigo


# ---------------------------------------------------------------------------
# Aplicação / Respondente / Resposta
# ---------------------------------------------------------------------------

class TipoAplicacao(models.TextChoices):
    ANONIMA = "anonima", "Anônima"
    IDENTIFICADA = "identificada", "Identificada"


class StatusAplicacao(models.TextChoices):
    RASCUNHO = "rascunho", "Rascunho"
    EM_ANDAMENTO = "em_andamento", "Em andamento"
    CONCLUIDA = "concluida", "Concluída"
    CANCELADA = "cancelada", "Cancelada"


class Aplicacao(models.Model):
    ghe = models.ForeignKey(GHE, on_delete=models.CASCADE, related_name="aplicacoes")
    instrumento = models.ForeignKey(Instrumento, on_delete=models.PROTECT, related_name="aplicacoes")
    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Link público único da Aplicacao inteira (/responder/<token>/), compartilhado "
        "por todos os respondentes — não existe mais um link por pessoa (CLAUDE.md Seção 6.7). "
        "Cada visita cria seu próprio Respondente na hora, identificado pela sessão do navegador.",
    )
    criterio_versao = models.ForeignKey(
        CriterioVersao, on_delete=models.PROTECT, related_name="aplicacoes", verbose_name="Critério de cálculo"
    )
    tipo = models.CharField(max_length=15, choices=TipoAplicacao.choices)
    status = models.CharField(
        max_length=15, choices=StatusAplicacao.choices, default=StatusAplicacao.RASCUNHO
    )
    justificativa_instrumento = models.TextField(
        blank=True,
        verbose_name="Justificativa da escolha do instrumento",
        help_text="Por que este instrumento foi escolhido para este GHE — fica registrado "
        "para consulta futura.",
    )
    data_aplicacao = models.DateField(null=True, blank=True, verbose_name="Data da aplicação")
    responsavel_aplicador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="aplicacoes_conduzidas"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    concluida_em = models.DateTimeField(null=True, blank=True)
    alertas_d9 = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Alertas D9",
        help_text="Nº de respondentes com evento grave confirmado (D9.1/D9.2 >= limiar) — "
        "planilha 'Alertas_agregados' do Excel de referência. Recalculado em "
        "calculo_risco.py::calcular_aplicacao().",
    )
    profundidade = models.CharField(
        max_length=10,
        blank=True,
        default="",
        verbose_name="Profundidade do questionário",
        help_text="Só usado quando o instrumento é o COPSOQ Oficial (curta/média/longa) — "
        "define quais itens (instrumentos.Item.profundidade) entram no questionário. Em "
        "branco para instrumentos que não usam níveis.",
    )

    def __str__(self) -> str:
        return f"{self.instrumento.codigo} @ {self.ghe} ({self.get_status_display()})"


class TempoNaOrganizacao(models.TextChoices):
    """Faixas alinhadas ao Excel de referência (aba "Form Responses 1",
    coluna [META.TEMPO]) — CLAUDE.md Seção 6.7 / prompts/01_form_responses.md."""

    MENOS_DE_1_ANO = "menos_1_ano", "Menos de 1 ano"
    DE_1_A_2_ANOS = "1_a_2_anos", "1 a 2 anos"
    DE_3_A_5_ANOS = "3_a_5_anos", "3 a 5 anos"
    MAIS_DE_5_ANOS = "mais_5_anos", "Mais de 5 anos"


class ModalidadeTrabalho(models.TextChoices):
    PRESENCIAL = "presencial", "Presencial"
    REMOTO = "remoto", "Remoto"
    HIBRIDO = "hibrido", "Híbrido"


class Respondente(models.Model):
    """Nunca expor `nome` fora de telas restritas — relatório agregado e mensagens
    a outras fontes usam sempre `alias_anonimo` (CLAUDE.md Seção 6.3/6.4, adaptado
    deste projeto: confidencialidade por padrão).

    Até 2026-07-19 tinha um `token` próprio — removido (CLAUDE.md Seção 6.7): o link
    público agora é único por Aplicacao (`Aplicacao.token`), e cada Respondente nasce
    sob demanda quando alguém abre esse link, identificado pela sessão do navegador
    (`avaliacoes/views.py`), não mais por um link individual gerado antecipadamente."""

    aplicacao = models.ForeignKey(Aplicacao, on_delete=models.CASCADE, related_name="respondentes")
    funcao = models.ForeignKey(
        Funcao, on_delete=models.SET_NULL, null=True, blank=True, related_name="respondentes"
    )
    nome = models.CharField(
        max_length=200, blank=True, help_text="Só preenchido quando aplicacao.tipo = identificada."
    )
    alias_anonimo = models.CharField(max_length=50, help_text='Ex.: "Respondente A".')
    tempo_na_organizacao = models.CharField(
        max_length=20, choices=TempoNaOrganizacao.choices, blank=True, verbose_name="Tempo na organização"
    )
    modalidade_trabalho = models.CharField(
        max_length=15,
        choices=ModalidadeTrabalho.choices,
        blank=True,
        verbose_name="Modalidade predominante de trabalho",
    )
    resposta_aberta_1 = models.TextField(
        blank=True, verbose_name="Qual mudança na organização do trabalho mais ajudaria a reduzir riscos?"
    )
    resposta_aberta_2 = models.TextField(
        blank=True, verbose_name="Há algum fator importante que não foi abordado?"
    )
    perguntas_abertas_respondidas_em = models.DateTimeField(
        null=True, blank=True, help_text="Marca que o respondente passou pela etapa de perguntas abertas "
        "(mesmo deixando-as em branco — são opcionais)."
    )
    consentimento_aceito_em = models.DateTimeField(
        null=True, blank=True, help_text="Obrigatório antes de registrar qualquer Resposta."
    )
    concluido_em = models.DateTimeField(
        null=True, blank=True, help_text="Preenchido quando o respondente termina todos os domínios aplicáveis."
    )
    indice_geral = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="Índice geral",
        help_text="Média dos EscoreRespondente (D1-D9) deste respondente, escala 0-100 "
        "(planilha Pontuacao_anonima do Excel de referência). Recalculado a cada domínio "
        "respondido, em calculo_risco.py.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.alias_anonimo


class Resposta(models.Model):
    respondente = models.ForeignKey(Respondente, on_delete=models.CASCADE, related_name="respostas")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="respostas")
    valor_bruto = models.PositiveSmallIntegerField()
    respondido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["respondente", "item"], name="uniq_resposta_por_item")
        ]

    def __str__(self) -> str:
        return f"{self.item.item_id}={self.valor_bruto} ({self.respondente})"


# ---------------------------------------------------------------------------
# Resultado do cálculo (risk_engine.py aplicado às Respostas)
# ---------------------------------------------------------------------------

class Classificacao(models.TextChoices):
    """Mesmos valores de string de risk_engine.Classificacao."""
    BAIXO = "Baixo", "Baixo"
    MODERADO = "Moderado", "Moderado"
    ELEVADO = "Elevado", "Elevado"


class BandaRisco(models.TextChoices):
    """Mesmos valores de string de risk_engine.BandaRisco."""
    ACEITAVEL = "Aceitável", "Aceitável"
    MODERADO = "Moderado", "Moderado"
    ALTO = "Alto", "Alto"
    CRITICO = "Crítico", "Crítico"


class PrioridadeChoices(models.TextChoices):
    """Mesmos valores de string de risk_engine.Prioridade. AGRUPAR = domínio suprimido
    por confidencialidade (N < mínimo) — planilha Diagnostico_GHE do Excel de
    referência (prompts/06_diagnostico_ghe.md)."""

    P1 = "P1", "P1"
    P2 = "P2", "P2"
    P3 = "P3", "P3"
    AGRUPAR = "AGRUPAR", "Agrupar (N insuficiente)"


class EscoreRespondente(models.Model):
    """Escore individual de UM respondente em UM domínio, escala 0-100 — corresponde a
    uma célula D1..D9 da planilha `Pontuacao_anonima` do Excel de referência
    (prompts/04_pontuacao_anonima.md). É o dado de onde `EscoreDominio.escore` (média
    agregada) e a prevalência (Seção 7.8 do CLAUDE.md) são derivados — nunca calculado
    ao contrário."""

    respondente = models.ForeignKey(Respondente, on_delete=models.CASCADE, related_name="escores")
    dominio = models.ForeignKey(Dominio, on_delete=models.PROTECT, related_name="escores_respondentes")
    escore = models.DecimalField(max_digits=5, decimal_places=2)
    classificacao = models.CharField(max_length=10, choices=Classificacao.choices)
    calculado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["respondente", "dominio"], name="uniq_escore_respondente_dominio")
        ]

    def __str__(self) -> str:
        return f"{self.respondente} / {self.dominio} = {self.escore} ({self.classificacao})"


class EscoreDominio(models.Model):
    aplicacao = models.ForeignKey(Aplicacao, on_delete=models.CASCADE, related_name="escores_dominio")
    dominio = models.ForeignKey(Dominio, on_delete=models.PROTECT, related_name="escores")
    escore = models.DecimalField(max_digits=5, decimal_places=2)
    classificacao = models.CharField(max_length=10, choices=Classificacao.choices)
    severidade = models.PositiveSmallIntegerField()
    n_respondentes = models.PositiveSmallIntegerField()
    suprimido_por_confidencialidade = models.BooleanField(default=False)
    percentual_elevados = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
        verbose_name="% respondentes na faixa elevada",
    )
    prioridade = models.CharField(
        max_length=10, choices=PrioridadeChoices.choices, blank=True,
        verbose_name="Prioridade (P1/P2/P3/AGRUPAR)",
    )
    calculado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["aplicacao", "dominio"], name="uniq_escore_por_aplicacao_dominio")
        ]

    def __str__(self) -> str:
        return f"{self.dominio} = {self.escore} ({self.classificacao})"


class ClassificacaoRisco(models.Model):
    escore_dominio = models.OneToOneField(
        EscoreDominio, on_delete=models.CASCADE, related_name="classificacao_risco"
    )
    evidencias_convergentes = models.PositiveSmallIntegerField(default=0)
    evento_grave_confirmado = models.BooleanField(default=False)
    probabilidade = models.PositiveSmallIntegerField()
    score = models.PositiveSmallIntegerField()
    banda = models.CharField(max_length=15, choices=BandaRisco.choices)
    prazo_dias_plano_de_acao = models.PositiveSmallIntegerField(null=True, blank=True)
    calculado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.escore_dominio.dominio} → {self.banda}"


class HierarquiaControle(models.TextChoices):
    """Hierarquia de controle da medida preventiva — planilha `Catalogo_Acoes` do Excel
    de referência (prompts/07_catalogo_acoes.md)."""

    ELIMINACAO = "eliminacao", "Eliminação/redução na fonte"
    ORGANIZACAO = "organizacao", "Organização do trabalho"
    GESTAO = "gestao", "Gestão/organização"
    CONTROLE_COLETIVO = "controle_coletivo", "Controle coletivo"
    REDESENHO = "redesenho", "Redesenho do trabalho"
    RESPOSTA_IMEDIATA = "resposta_imediata", "Resposta imediata e eliminação da exposição"


class CatalogoAcao(models.Model):
    """Ação preventiva pré-definida por (domínio, nível) — 18 linhas no seed original
    (9 domínios × Moderado/Elevado), planilha `Catalogo_Acoes` do Excel de referência.
    Pré-definido pelo seed mas editável pelo admin (Django Admin e painel) — o
    profissional responsável pode personalizar pra realidade de cada empresa."""

    dominio = models.ForeignKey(Dominio, on_delete=models.CASCADE, related_name="acoes_catalogo")
    nivel = models.CharField(max_length=10, choices=Classificacao.choices, verbose_name="Nível")
    acao_sugerida = models.TextField(verbose_name="Ação sugerida")
    hierarquia = models.CharField(max_length=30, choices=HierarquiaControle.choices)
    indicador = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["dominio", "nivel"], name="uniq_catalogo_por_dominio_nivel")
        ]
        ordering = ["dominio__ordem", "nivel"]

    def __str__(self) -> str:
        return f"{self.dominio.codigo} / {self.nivel}"


class StatusPlanoDeAcao(models.TextChoices):
    """Ampliado (Prompt 08) com "Planejada" e "Contínua" — vocabulário da planilha
    `Plano_de_Acao` do Excel de referência, que distingue uma ação já formalmente
    definida mas ainda não iniciada ("Planejada") de uma ação recorrente sem data de
    término ("Contínua"), além dos status originais."""

    PENDENTE = "pendente", "Pendente"
    PLANEJADA = "planejada", "Planejada"
    EM_ANDAMENTO = "em_andamento", "Em andamento"
    CONCLUIDO = "concluido", "Concluído"
    CONTINUA = "continua", "Contínua"
    ATRASADO = "atrasado", "Atrasado"


class PlanoDeAcao(models.Model):
    """15 campos — planilha `Plano_de_Acao` do Excel de referência (prompts/08). Os
    campos que já existiam (`medida`, `prazo`, `status`, `evidencia_execucao`,
    `hierarquia`, `indicador`) foram mantidos; os novos cobrem o restante da planilha.

    `responsavel` é texto livre (não FK para User): o Excel usa nomes de área/cargo
    ("Direção de Operações", "Gerência Industrial + SESMT"), não necessariamente um
    usuário cadastrado no sistema."""

    classificacao_risco = models.ForeignKey(
        ClassificacaoRisco, on_delete=models.CASCADE, related_name="planos_de_acao"
    )
    codigo = models.CharField(
        max_length=10, blank=True, verbose_name="ID da ação",
        help_text='Identificador manual (ex.: "A01", "A02"). Gerado automaticamente se vazio.',
    )
    medida = models.TextField(verbose_name="Medida escolhida")
    hierarquia = models.CharField(
        max_length=30, choices=HierarquiaControle.choices, blank=True,
        verbose_name="Hierarquia de controle",
        help_text="Preenchido a partir do CatalogoAcao correspondente, quando existe.",
    )
    evidencia_diagnostico = models.TextField(
        blank=True, verbose_name="Evidência do diagnóstico",
        help_text="O que o diagnóstico mostrou para justificar esta ação.",
    )
    indicador = models.TextField(
        blank=True, verbose_name="Indicador de acompanhamento",
        help_text="Como medir se a ação funcionou — vem do CatalogoAcao, quando existe.",
    )
    meta = models.TextField(blank=True, verbose_name="Meta")
    responsavel = models.CharField(max_length=200, blank=True, default="", verbose_name="Responsável")
    prazo = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=15, choices=StatusPlanoDeAcao.choices, default=StatusPlanoDeAcao.PLANEJADA
    )
    evidencia_execucao = models.TextField(blank=True, verbose_name="Evidência de execução")
    verificacao_eficacia = models.TextField(blank=True, verbose_name="Verificação de eficácia")
    data_revisao = models.DateField(null=True, blank=True, verbose_name="Data da revisão")
    observacoes = models.TextField(blank=True, verbose_name="Observações")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        prefixo = f"{self.codigo} — " if self.codigo else ""
        return f"{prefixo}{self.medida[:60]} ({self.status})"


# ---------------------------------------------------------------------------
# Checklist de triangulação (entrevista + observação) — Seção 7.5, evidências
# complementares (planilha `Entrevista_Observacao` do Excel de referência,
# prompts/09_entrevista_observacao.md). Complementa `IndicadorIndireto` (que
# continua existindo inalterado) com 16 itens pré-definidos e estruturados.
# ---------------------------------------------------------------------------

class TipoChecklist(models.TextChoices):
    ENTREVISTA = "entrevista", "Entrevista com liderança"
    OBSERVACAO = "observacao", "Observação em campo"


class ConformidadeChecklist(models.TextChoices):
    CONFORME = "conforme", "Conforme"
    NAO_CONFORME = "nao_conforme", "Não conforme"
    NAO_AVALIADO = "nao_avaliado", "Não avaliado"


class ItemChecklistTriangulacao(models.Model):
    """Item pré-definido do checklist de triangulação — carregado via seed
    (`seeds/checklist_triangulacao.json`), os 16 itens (6 entrevista + 10 observação)
    valem pra qualquer GHE/Aplicacao, não são customizados por empresa.

    Achado em 2026-07-29: os itens `tipo=entrevista` são perguntas abertas ("Quais são
    os períodos de maior demanda e por quê?"), não afirmações de conformidade — não faz
    sentido pedir Conforme/Não conforme pra elas. Só itens `tipo=observacao` (afirmações
    de checklist de verdade) têm uma resposta de conformidade válida.

    `dominio_codigo_relacionado`: só se aplica a itens de observação. Guarda o código
    literal do domínio COPSOQ que o item representa (ex. "D9"), não uma FK — o catálogo
    é único e compartilhado entre instrumentos (COPSOQ e ITRA têm códigos de domínio
    diferentes), então a comparação em `calculo_risco.py::contar_evidencias_convergentes`
    só "acerta" quando o domínio calculado tem esse mesmo código (COPSOQ). Em branco =
    evidência geral, conta pra qualquer domínio calculado (mesma semântica do
    `IndicadorIndireto.dominio_relacionado` nulo)."""

    tipo = models.CharField(max_length=15, choices=TipoChecklist.choices)
    texto = models.TextField()
    ordem = models.PositiveSmallIntegerField(default=0)
    dominio_codigo_relacionado = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Domínio relacionado (código)",
        help_text="Só usado em itens de observação. Código do domínio COPSOQ (ex. \"D9\"). "
        "Em branco = evidência geral, conta pra qualquer domínio calculado.",
    )

    class Meta:
        ordering = ["tipo", "ordem"]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} #{self.ordem}"


class StatusColetaChecklist(models.TextChoices):
    ABERTA = "aberta", "Aberta"
    ENCERRADA = "encerrada", "Encerrada"


class ColetaChecklistTriangulacao(models.Model):
    """Uma rodada de coleta do checklist de triangulação, respondida via link público
    pelos gestores/liderança da empresa cliente — não mais digitada direto pelo
    profissional responsável (CLAUDE.md Seção 6.11). Mesmo padrão de link único +
    sessão do navegador do questionário do colaborador (Seção 6.7), mas aqui o
    respondente se identifica (nome/cargo), pois é uma entrevista com a liderança,
    não uma coleta anônima. Uma Aplicacao pode ter várias rodadas ao longo do tempo
    (reaplicação periódica, Seção 6 item 11)."""

    aplicacao = models.ForeignKey(Aplicacao, on_delete=models.CASCADE, related_name="coletas_checklist")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(
        max_length=15, choices=StatusColetaChecklist.choices, default=StatusColetaChecklist.ABERTA
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    encerrada_em = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Coleta checklist @ {self.aplicacao} ({self.get_status_display()})"


class RespondenteChecklistTriangulacao(models.Model):
    """Gestor/liderança que responde pelo link — identificado (nome/cargo), diferente
    do `Respondente` anônimo do colaborador."""

    coleta = models.ForeignKey(
        ColetaChecklistTriangulacao, on_delete=models.CASCADE, related_name="respondentes"
    )
    nome = models.CharField(max_length=200)
    cargo = models.CharField(max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    concluido_em = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.nome} ({self.cargo})" if self.cargo else self.nome


class RespostaChecklistTriangulacao(models.Model):
    """Resposta de um respondente (gestor/liderança) a um item do checklist."""

    respondente = models.ForeignKey(
        RespondenteChecklistTriangulacao, on_delete=models.CASCADE, related_name="respostas"
    )
    item = models.ForeignKey(ItemChecklistTriangulacao, on_delete=models.PROTECT)
    conformidade = models.CharField(
        max_length=15, choices=ConformidadeChecklist.choices, default=ConformidadeChecklist.NAO_AVALIADO
    )
    evidencia = models.TextField(blank=True, verbose_name="Evidência/observação")
    respondido_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["respondente", "item"], name="uniq_checklist_por_respondente_item")
        ]

    def __str__(self) -> str:
        return f"{self.item} @ {self.respondente} ({self.conformidade})"
