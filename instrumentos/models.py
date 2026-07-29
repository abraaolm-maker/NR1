from django.db import models


class Polaridade(models.TextChoices):
    """Espelha risk_engine.Polaridade (mesmos valores de string) — ver
    avaliacoes/risk_engine_lib/risk_engine.py."""
    RISCO = "RISCO", "Risco"
    PROTETIVO = "PROTETIVO", "Protetivo"


class Instrumento(models.Model):
    """Um instrumento de coleta plugável (COPSOQ adaptado, ITRA, ou outro futuro).

    Nenhuma lógica do backend deve assumir qual instrumento é este — tudo que varia
    (domínios, itens, polaridade, escala, thresholds) vive em Dominio/Item ou em
    CriterioVersao (avaliacoes app), nunca hardcoded aqui (CLAUDE.md Seção 3, princípio 1).
    """

    codigo = models.CharField(max_length=50, unique=True)
    nome = models.CharField(max_length=200)
    descricao = models.TextField(blank=True)
    fonte = models.TextField(
        blank=True,
        help_text="Origem/autoria do instrumento e ressalvas de uso (ex.: aviso de "
        "validação pendente do ITRA — CLAUDE.md Seção 5.2).",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.nome


class Dominio(models.Model):
    """Domínio (COPSOQ) ou subescala (ITRA) de um instrumento — sempre genérico, o mesmo
    texto de item vale pra qualquer GHE que use o instrumento (CLAUDE.md Seção 3, princípio
    1: nenhuma lógica assume metodologia fixa; nenhum instrumento assume cargo fixo).

    Até 2026-07-18 este model teve um campo `ghe_variante` (texto de item variando por
    cargo-piloto da empresa de referência RR Revestir) — removido porque um dado de
    fixture de UMA empresa tinha virado, na prática, a única opção disponível no sistema
    pra QUALQUER empresa. Ver CLAUDE.md Seção 6.5 (decisão de realinhamento).

    Escala (min/max/labels) e thresholds de referência (baixo_max/moderado_max) vêm do
    JSON semente e servem só de metadado/documentação do instrumento. O critério
    EFETIVAMENTE usado no cálculo de risco vive em avaliacoes.CriterioVersao (Seção 7.8
    do CLAUDE.md exige isso como entidade versionada, não constante solta)."""

    instrumento = models.ForeignKey(Instrumento, on_delete=models.CASCADE, related_name="dominios")
    codigo = models.CharField(max_length=20, help_text='Ex.: "D1", "EACT", "EIPSTN".')
    nome = models.CharField(max_length=200)
    nota = models.TextField(
        blank=True,
        help_text='Ex.: aviso de polaridade mista do D9 do COPSOQ.',
    )
    escala_min = models.PositiveSmallIntegerField()
    escala_max = models.PositiveSmallIntegerField()
    escala_labels = models.JSONField(
        default=dict, blank=True, help_text="Rótulos da escala por valor bruto, ex. {'1': 'Nunca', ...}."
    )
    thresholds_referencia_baixo_max = models.DecimalField(max_digits=6, decimal_places=2)
    thresholds_referencia_moderado_max = models.DecimalField(max_digits=6, decimal_places=2)
    referencia_media_nacional = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Média nacional publicada (valor bruto, sem inversão de polaridade — "
        "ex.: COPSOQ Manual Portugal 2013, N=4162). Só informativo/contexto.",
    )
    referencia_desvio_padrao = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Desvio-padrão da média nacional publicada, mesma fonte/ressalva.",
    )
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["instrumento", "codigo"],
                name="uniq_dominio_por_instrumento_codigo",
            )
        ]
        ordering = ["instrumento", "ordem", "codigo"]

    def __str__(self) -> str:
        return f"{self.instrumento.codigo} / {self.codigo}"


class Profundidade(models.TextChoices):
    """Nível de profundidade do COPSOQ Oficial (CLAUDE.md — instrumento transcrito do
    manual COPSOQ Portugal 2013): cada item pertence ao nível mais raso em que aparece
    no documento oficial (curta ⊆ média ⊆ longa, por conteúdo do item, não por posição
    numérica — alguns itens da versão longa correspondem à média com texto reformulado,
    tratados como itens próprios daquele nível). Em branco = instrumento não usa níveis
    (COPSOQ adaptado, ITRA) — o item aparece sempre, independente de profundidade."""

    CURTA = "curta", "Curta"
    MEDIA = "media", "Média"
    LONGA = "longa", "Longa"


class Item(models.Model):
    item_id = models.CharField(
        max_length=20, help_text='Identificador exato do seed, ex. "D1.1", "EACT.01" — usado como '
        "RespostaItem.item_id / ItemInstrumento.id do risk_engine.",
    )
    dominio = models.ForeignKey(Dominio, on_delete=models.CASCADE, related_name="itens")
    texto = models.TextField()
    polaridade = models.CharField(max_length=10, choices=Polaridade.choices)
    evento_grave = models.BooleanField(
        default=False,
        help_text="Se True, valor_bruto >= limiar (CriterioVersao) força Probabilidade=3 "
        "(CLAUDE.md Seção 7.5).",
    )
    profundidade = models.CharField(
        max_length=10,
        choices=Profundidade.choices,
        blank=True,
        default="",
        help_text="Só usado pelo COPSOQ Oficial — nível mínimo em que o item aparece "
        "(curta/média/longa). Em branco = item sempre incluído (demais instrumentos).",
    )
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["dominio", "item_id"], name="uniq_item_por_dominio")
        ]
        ordering = ["dominio", "ordem", "item_id"]

    def __str__(self) -> str:
        return f"{self.item_id} ({self.dominio})"
