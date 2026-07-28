import json
import re

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from instrumentos.models import Instrumento
from .models import (
    GHE,
    Aplicacao,
    CatalogoAcao,
    CriterioVersao,
    Empresa,
    Funcao,
    IndicadorIndireto,
    PlanoDeAcao,
    StatusCriterioVersao,
    TipoAplicacao,
    Unidade,
)


def _formatar_cnpj(valor: str) -> str:
    """Exige 14 dígitos e formata pra 00.000.000/0000-00 — sem isso, um CNPJ digitado
    de qualquer jeito era aceito sem aviso nenhum (achado no teste de UX, 2026-07-17)."""
    digitos = re.sub(r"\D", "", valor)
    if len(digitos) != 14:
        raise forms.ValidationError("CNPJ deve ter 14 dígitos (ex.: 12.345.678/0001-90).")
    return f"{digitos[0:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:14]}"


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ["nome", "cnpj"]

    def clean_cnpj(self):
        return _formatar_cnpj(self.cleaned_data["cnpj"])


class CatalogoAcaoForm(forms.ModelForm):
    """Edição de uma ação pré-definida do catálogo (prompts/07_catalogo_acoes.md) — o
    seed carrega os defaults, mas o profissional responsável pode personalizar pra
    realidade de cada empresa."""

    class Meta:
        model = CatalogoAcao
        fields = ["acao_sugerida", "hierarquia", "indicador"]


class PlanoDeAcaoForm(forms.ModelForm):
    """Edição dos 15 campos do Plano de Ação (planilha `Plano_de_Acao` do Excel de
    referência, prompts/08). `classificacao_risco` nunca é editável aqui — o vínculo
    com o domínio/GHE é definido pelo cálculo, não pelo formulário."""

    class Meta:
        model = PlanoDeAcao
        fields = [
            "codigo",
            "medida",
            "hierarquia",
            "evidencia_diagnostico",
            "indicador",
            "meta",
            "responsavel",
            "prazo",
            "status",
            "evidencia_execucao",
            "verificacao_eficacia",
            "data_revisao",
            "observacoes",
        ]
        widgets = {
            "prazo": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "data_revisao": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


class IndicadorIndiretoForm(forms.ModelForm):
    """Cadastro de evidência complementar (Seção 7.5) — antes só existia no Django
    Admin, que ninguém usando o painel achava (achado no diagnóstico de UX de
    2026-07-28). `ghe` é fixado pela view, nunca escolhido aqui."""

    class Meta:
        model = IndicadorIndireto
        fields = ["tipo", "periodo_referencia", "descricao", "dominio_relacionado", "convergente"]
        widgets = {"periodo_referencia": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, ghe=None, **kwargs):
        super().__init__(*args, **kwargs)
        if ghe is not None:
            from instrumentos.models import Dominio

            self.fields["dominio_relacionado"].queryset = Dominio.objects.filter(
                instrumento__aplicacoes__ghe=ghe
            ).distinct()
        self.fields["dominio_relacionado"].required = False
        self.fields["dominio_relacionado"].help_text = "Deixe em branco se o indicador vale pro GHE inteiro."


class CriarGestorForm(forms.Form):
    """Cria o único usuário-gestor de uma Empresa (CLAUDE.md Seção 6.8: 1 gestor por
    empresa no MVP) — ação exclusiva do admin, feita a partir do detalhe da Empresa."""

    username = forms.CharField(max_length=150, label="Usuário")
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, label="Senha")

    def clean_username(self):
        username = self.cleaned_data["username"]
        if get_user_model().objects.filter(username=username).exists():
            raise forms.ValidationError("Já existe um usuário com esse nome.")
        return username


class UnidadeForm(forms.ModelForm):
    class Meta:
        model = Unidade
        fields = ["nome", "cnpj", "endereco"]

    def clean_cnpj(self):
        valor = self.cleaned_data.get("cnpj", "")
        if not valor:
            return valor  # opcional — unidade pode não ter CNPJ próprio
        return _formatar_cnpj(valor)


class FuncaoForm(forms.ModelForm):
    class Meta:
        model = Funcao
        fields = ["nome", "descricao"]


class GHEForm(forms.ModelForm):
    class Meta:
        model = GHE
        fields = ["nome", "setor", "funcoes"]
        widgets = {"funcoes": forms.CheckboxSelectMultiple}

    def __init__(self, *args, unidade=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._unidade = unidade
        if unidade is not None:
            self.fields["funcoes"].queryset = Funcao.objects.filter(unidade=unidade)


class AplicacaoForm(forms.ModelForm):
    """Instrumento e Tipo são as únicas decisões reais nesta tela — os demais campos
    têm resposta óbvia na esmagadora maioria dos casos, então nascem preenchidos e
    escondidos atrás de um "usar outro/editar" (achado do teste de UX, 2026-07-18: com
    só uma versão de critério e um usuário no sistema, os dropdowns de
    `criterio_versao`/`responsavel_aplicador` eram clique vazio):

    - `criterio_versao`: pré-selecionado (ratificado mais recente; sem nenhum
      ratificado, o mais recente mesmo assim) e mostrado como texto — só vira dropdown
      quando existe mais de um `CriterioVersao` no banco (`total_criterios`).
    - `responsavel_aplicador`: pré-selecionado com o usuário logado (`usuario_logado`)
      e mostrado como texto — só vira dropdown quando existe mais de um usuário staff
      (`total_aplicadores`).
    - `data_aplicacao`: pré-preenchida com hoje, continua editável (campo de data
      comum) — só o valor inicial muda.
    - `justificativa_instrumento`: continua com formulário próprio (é opcional e sai do
      caminho visual das decisões reais) — `aplicacao_form.html` a renderiza atrás de
      um "+ Adicionar justificativa" recolhido, exceto quando já tem conteúdo (edição).
    - `tipo`: pré-selecionado "Anônima" (CLAUDE.md Seção 3, princípio 3: anônima é o
      padrão), continua sempre visível/decisão explícita.

    Instrumento mantém a explicação dinâmica por seleção já existente
    (`instrumentos_ajuda_json`, lido por `aplicacao_form.html`). Até 2026-07-18 havia
    também um campo "Variante do instrumento (GHE)" — removido (CLAUDE.md Seção 6.5)."""

    class Meta:
        model = Aplicacao
        fields = [
            "instrumento",
            "criterio_versao",
            "tipo",
            "responsavel_aplicador",
            "justificativa_instrumento",
            "data_aplicacao",
        ]
        widgets = {"data_aplicacao": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
        help_texts = {
            "instrumento": "Selecione um instrumento para ver, abaixo, o que ele é e quando usá-lo.",
            "criterio_versao": (
                "Define os parâmetros técnicos (limiares de risco, matriz de severidade × "
                "probabilidade) usados no cálculo. Normalmente existe apenas uma versão — "
                "escolha a mais recente, a menos que precise reabrir uma aplicação com o "
                "mesmo critério de um relatório já existente."
            ),
        }

    def __init__(self, *args, usuario_logado=None, **kwargs):
        super().__init__(*args, **kwargs)
        criando = not self.instance.pk

        self.fields["instrumento"].label_from_instance = lambda obj: obj.nome
        self.fields["instrumento"].widget.attrs["id"] = "id_instrumento"
        self.instrumentos_ajuda_json = json.dumps(
            {
                str(instrumento.pk): instrumento.descricao
                for instrumento in Instrumento.objects.all()
            }
        )

        self.fields["criterio_versao"].label_from_instance = (
            lambda obj: f"{obj.codigo} ({obj.get_status_display()})"
        )
        criterios = list(CriterioVersao.objects.order_by("-criado_em"))
        self.total_criterios = len(criterios)
        self.criterio_padrao = next(
            (c for c in criterios if c.status == StatusCriterioVersao.RATIFICADO), criterios[0] if criterios else None
        )
        if criando and self.criterio_padrao:
            self.fields["criterio_versao"].initial = self.criterio_padrao.pk

        aplicadores = get_user_model().objects.filter(is_staff=True).order_by("username")
        self.fields["responsavel_aplicador"].queryset = aplicadores
        self.total_aplicadores = aplicadores.count()
        self.aplicador_padrao = usuario_logado
        if criando and usuario_logado:
            self.fields["responsavel_aplicador"].initial = usuario_logado.pk

        if criando:
            self.fields["tipo"].initial = TipoAplicacao.ANONIMA
            self.fields["data_aplicacao"].initial = timezone.now().date()
