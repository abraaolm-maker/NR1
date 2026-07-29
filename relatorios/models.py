from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from avaliacoes.models import Aplicacao, CriterioVersao, Unidade


class PerfilProfissional(models.Model):
    """Registro profissional (CRP/CREA/CRM/etc.) de quem pode assinar um Relatorio —
    CLAUDE.md Seção 8.3, item 8: o bloco de assinatura do PDF precisa de nome, registro
    profissional e data. `nome` e `data` já vêm de `Relatorio.assinado_por`/`assinado_em`;
    este model só guarda o dado que faltava. Decisão de 2026-07-17: perfil ligado ao User
    (não campos soltos em Relatorio) pra não redigitar o registro a cada assinatura."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil_profissional"
    )
    titulo_profissional = models.CharField(
        max_length=150, help_text='Ex.: "Psicólogo do Trabalho", "Engenheiro de Segurança do Trabalho".'
    )
    conselho = models.CharField(max_length=50, help_text='Ex.: "CRP", "CREA".')
    numero_registro = models.CharField(max_length=50, help_text='Ex.: "06/123456".')
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.user} ({self.conselho} {self.numero_registro})"


class ChaveApiClaude(models.Model):
    """Metadados de uma chave de API da Anthropic cadastrada pelo painel — o VALOR
    COMPLETO da chave nunca é persistido aqui, só em `.env.local` (fora do controle de
    versão — ver `.gitignore`), sob a variável `nome_variavel_ambiente`. O que fica
    neste model é só o suficiente pra identificar a chave visualmente (nome, prefixo,
    sufixo) e escolher qual está ativa. Ninguém com acesso ao banco, ao Admin ou a um
    dump consegue reconstruir a chave completa a partir daqui — só o arquivo local
    tem o valor, e nenhuma tela do painel o exibe de volta depois de salvo
    (`relatorios/services/chaves_api.py`)."""

    nome = models.CharField(max_length=100, help_text='Ex.: "Produção", "Testes".')
    prefixo = models.CharField(max_length=16, editable=False)
    sufixo = models.CharField(max_length=8, editable=False)
    ativa = models.BooleanField(default=False)
    valida = models.BooleanField(
        null=True, blank=True, editable=False,
        help_text="Resultado da última verificação contra a API da Anthropic. Null = ainda não verificada.",
    )
    verificada_em = models.DateTimeField(null=True, blank=True, editable=False)
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criada_em"]

    def __str__(self) -> str:
        return f"{self.nome} ({self.prefixo}…{self.sufixo})"

    @property
    def nome_variavel_ambiente(self) -> str:
        return f"CLAUDE_API_KEY_{self.pk}"


class StatusRelatorio(models.TextChoices):
    """Espelha a semântica minuta/aguardando_revisão/assinado da Seção 8.1 do
    CLAUDE.md. Valor inicial (default) deve ser exatamente "aguardando_revisão"."""
    AGUARDANDO_REVISAO = "aguardando_revisão", "Minuta (aguardando revisão)"
    APROVADO = "aprovado", "Aprovado (pendente de assinatura)"
    ASSINADO = "assinado", "Assinado"


class Relatorio(models.Model):
    """Um Inventário de Risco Psicossocial em PDF pode cobrir mais de um GHE/Aplicacao
    do mesmo ciclo de avaliação (CLAUDE.md Seção 8.3, item 4: "Resultados por GHE e por
    domínio" no plural) — por isso `aplicacoes` é M2M, escopado a uma Unidade e a um
    período. A IA (Claude) só redige o parecer a partir de números já calculados; nunca
    decide classificação (Seção 8.1)."""

    unidade = models.ForeignKey(Unidade, on_delete=models.PROTECT, related_name="relatorios")
    aplicacoes = models.ManyToManyField(Aplicacao, related_name="relatorios", verbose_name="Aplicações")
    criterio_versao = models.ForeignKey(
        CriterioVersao, on_delete=models.PROTECT, related_name="relatorios", verbose_name="Critério de cálculo"
    )
    periodo_inicio = models.DateField(verbose_name="Início do período")
    periodo_fim = models.DateField(verbose_name="Fim do período")

    parecer_ia = models.JSONField(
        null=True,
        blank=True,
        help_text="Saída estruturada da API de análise: parecer por domínio, síntese "
        "executiva, riscos prioritários, recomendações.",
    )
    status = models.CharField(
        max_length=20, choices=StatusRelatorio.choices, default=StatusRelatorio.AGUARDANDO_REVISAO
    )
    pdf_path = models.FileField(upload_to="relatorios/%Y/%m/", null=True, blank=True)

    assinado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    assinado_em = models.DateTimeField(null=True, blank=True)

    gerado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Relatório {self.unidade} [{self.periodo_inicio} – {self.periodo_fim}] ({self.status})"


@receiver(m2m_changed, sender=Relatorio.aplicacoes.through)
def validar_aplicacoes_mesma_unidade_e_criterio(sender, instance, action, pk_set, **kwargs):
    """Trava de rastreabilidade (CLAUDE.md Seção 7.8): um Relatorio não pode misturar
    Aplicacoes de unidades diferentes nem calculadas sob CriterioVersao diferentes —
    isso quebraria a auditoria que a NR-01 exige. Roda no add via ORM, Admin ou
    serializer futuro, não só numa camada específica."""
    if action != "pre_add" or not pk_set:
        return

    aplicacoes = Aplicacao.objects.filter(pk__in=pk_set).select_related("ghe__unidade", "criterio_versao")
    for aplicacao in aplicacoes:
        if aplicacao.ghe.unidade_id != instance.unidade_id:
            raise ValidationError(
                f"Aplicacao #{aplicacao.pk} pertence à unidade '{aplicacao.ghe.unidade}', "
                f"diferente da unidade do Relatorio ('{instance.unidade}')."
            )
        if aplicacao.criterio_versao_id != instance.criterio_versao_id:
            raise ValidationError(
                f"Aplicacao #{aplicacao.pk} foi calculada sob o critério "
                f"'{aplicacao.criterio_versao}', diferente do critério do Relatorio "
                f"('{instance.criterio_versao}')."
            )
