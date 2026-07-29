import json

from django import forms

from avaliacoes.models import Aplicacao

from .models import PerfilProfissional, Relatorio

class ChaveApiClaudeForm(forms.Form):
    """Formulário de cadastro — não é ModelForm de propósito: o valor bruto da chave
    nunca passa por um campo de `ChaveApiClaude` (que não tem esse campo), só é lido
    aqui em memória e repassado direto pro service que grava no `.env.local`."""

    nome = forms.CharField(max_length=100, label="Nome", help_text='Ex.: "Produção", "Testes".')
    valor = forms.CharField(
        label="Chave de API",
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off", "placeholder": "sk-ant-..."}),
    )


CAMPOS_OBRIGATORIOS_PARECER = {
    "sintese_executiva",
    "pareceres_por_dominio",
    "riscos_prioritarios",
    "recomendacoes",
    "aviso_minuta",
}


class RelatorioForm(forms.ModelForm):
    class Meta:
        model = Relatorio
        fields = ["criterio_versao", "aplicacoes", "periodo_inicio", "periodo_fim"]
        widgets = {
            "aplicacoes": forms.CheckboxSelectMultiple,
            "periodo_inicio": forms.DateInput(attrs={"type": "date"}),
            "periodo_fim": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "aplicacoes": "Só aparecem Aplicações desta Unidade, e todas precisam ter sido "
            "calculadas com o mesmo Critério escolhido acima.",
        }

    def __init__(self, *args, unidade=None, **kwargs):
        super().__init__(*args, **kwargs)
        if unidade is not None:
            self.fields["aplicacoes"].queryset = Aplicacao.objects.filter(ghe__unidade=unidade)
        # Achado do teste de UX (2026-07-18): o __str__ padrão de Aplicacao mostra o
        # codigo tecnico do instrumento (ex. "COPSOQ_RR_REVESTIR") — trocado aqui pelo
        # nome amigavel (ja simplificado pro seed, ex. "COPSOQ").
        #
        # Achado do usuário em 2026-07-29: com mais de uma Aplicacao no mesmo GHE (ex.
        # um teste antigo e uma aplicação nova), o rótulo antigo ("COPSOQ — Pedreiro
        # (Concluída)") não distinguia bem qual é qual — o usuário selecionou a
        # Aplicacao errada sem perceber. Rótulo agora inclui o nº de respondentes e a
        # data de criação, que são os dois dados que realmente diferenciam duas
        # Aplicações do mesmo GHE/instrumento.
        self.fields["aplicacoes"].label_from_instance = (
            lambda obj: (
                f"{obj.instrumento.nome} — {obj.ghe.nome} ({obj.get_status_display()}) — "
                f"{obj.respondentes.count()} respondente(s), criada em "
                f"{obj.criado_em:%d/%m/%Y}"
            )
        )
        self.fields["criterio_versao"].label_from_instance = (
            lambda obj: f"{obj.codigo} ({obj.get_status_display()})"
        )


class ParecerJSONForm(forms.Form):
    parecer_json = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 22}),
        label="Parecer técnico (JSON)",
        help_text="Estrutura: sintese_executiva, pareceres_por_dominio, riscos_prioritarios, "
        "recomendacoes, aviso_minuta.",
    )

    def clean_parecer_json(self):
        texto = self.cleaned_data["parecer_json"]
        try:
            dado = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"JSON inválido: {exc}") from exc
        if not isinstance(dado, dict):
            raise forms.ValidationError("O parecer precisa ser um objeto JSON (dict).")
        faltando = CAMPOS_OBRIGATORIOS_PARECER - dado.keys()
        if faltando:
            raise forms.ValidationError(
                f"Faltam campos obrigatórios no parecer: {', '.join(sorted(faltando))}."
            )
        return dado


class PerfilProfissionalForm(forms.ModelForm):
    class Meta:
        model = PerfilProfissional
        fields = ["titulo_profissional", "conselho", "numero_registro"]
