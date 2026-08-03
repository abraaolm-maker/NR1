"""Armazenamento seguro de chaves de API da Anthropic (Claude) usadas pra gerar o
parecer técnico dos relatórios.

Regra inegociável: o valor completo de uma chave NUNCA é persistido no banco de dados
nem reexibido em nenhuma tela depois de salvo. Ele só existe em memória durante a
requisição de cadastro e num arquivo local (`settings.CHAVES_API_ENV_PATH`, fora do
controle de versão), sob uma variável nomeada por `ChaveApiClaude.nome_variavel_ambiente`.
O que fica no banco (`ChaveApiClaude`) é só metadado de identificação: nome, prefixo,
sufixo e qual está ativa.

Esse arquivo é lido DIRETO DO DISCO a cada chamada (nunca de `os.environ`, que só
reflete o que foi carregado quando o processo do servidor subiu) — assim uma chave
nova ou trocada fica disponível na hora, sem precisar reiniciar o servidor.

Em produção com Docker, `CHAVES_API_ENV_PATH` PRECISA apontar pro mesmo disco
persistente do banco (ex.: `/var/data/.env.local`) — se ficar no filesystem efêmero
do container (o default `BASE_DIR/.env.local`, usado em desenvolvimento local),
recriar o container apaga esse arquivo enquanto o metadado no banco continua
existindo, e o sistema passa a achar que tem uma chave ativa que na verdade sumiu
(achado em produção, 2026-08-03)."""

from __future__ import annotations

import re

import dotenv
from django.conf import settings
from django.utils import timezone

from relatorios.models import ChaveApiClaude

ENV_PATH = settings.CHAVES_API_ENV_PATH

INTERVALO_REVERIFICACAO = timezone.timedelta(days=1)

_PADRAO_CHAVE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")


def validar_formato(valor: str) -> None:
    if not _PADRAO_CHAVE.fullmatch(valor.strip()):
        raise ValueError('Formato de chave inválido — chaves da Anthropic começam com "sk-ant-".')


def _mascarar(valor: str) -> tuple[str, str]:
    valor = valor.strip()
    return valor[:10], valor[-4:]


def salvar_chave(nome: str, valor_bruto: str, usuario) -> ChaveApiClaude:
    """Valida o formato, cria o registro de metadados e grava o valor completo só no
    `.env.local`. `valor_bruto` nunca é salvo em nenhum campo do model nem logado."""
    nome = nome.strip()
    if not nome:
        raise ValueError("Informe um nome para identificar a chave.")
    validar_formato(valor_bruto)

    prefixo, sufixo = _mascarar(valor_bruto)
    chave = ChaveApiClaude.objects.create(nome=nome, prefixo=prefixo, sufixo=sufixo, criada_por=usuario)

    ENV_PATH.touch(exist_ok=True)
    dotenv.set_key(str(ENV_PATH), chave.nome_variavel_ambiente, valor_bruto.strip(), quote_mode="always")
    return chave


def definir_chave_ativa(chave_id: int) -> None:
    """Só uma chave pode estar ativa por vez — a próxima geração de parecer via IA
    usa exatamente essa."""
    ChaveApiClaude.objects.exclude(pk=chave_id).filter(ativa=True).update(ativa=False)
    ChaveApiClaude.objects.filter(pk=chave_id).update(ativa=True)


def remover_chave(chave: ChaveApiClaude) -> None:
    if ENV_PATH.exists():
        dotenv.unset_key(str(ENV_PATH), chave.nome_variavel_ambiente)
    chave.delete()


def obter_valor_chave(chave_id: int) -> str | None:
    """Valor completo de UMA chave específica, lido na hora do `.env.local`. Único
    ponto do sistema que lê o valor bruto; usado só pra construir o client da
    Anthropic em memória (geração de parecer ou verificação de validade), nunca
    passado adiante pra template/log/resposta HTTP."""
    if not ENV_PATH.exists():
        return None
    valores = dotenv.dotenv_values(str(ENV_PATH))
    return valores.get(f"CLAUDE_API_KEY_{chave_id}")


def obter_valor_chave_ativa() -> str | None:
    """Valor completo da chave ativa — ou None se não houver chave ativa."""
    chave = ChaveApiClaude.objects.filter(ativa=True).first()
    if chave is None:
        return None
    return obter_valor_chave(chave.pk)


def verificar_chave(chave: ChaveApiClaude) -> ChaveApiClaude:
    """Confirma que a chave é aceita pela Anthropic chamando `client.models.list()`
    — não gera tokens nem tem custo de uso, só autentica. Resultado (`valida`) e o
    instante da checagem (`verificada_em`) ficam salvos pra não precisar reverificar
    a cada carregamento de tela (`chave_precisa_reverificacao` decide quando repetir)."""
    valor = obter_valor_chave(chave.pk)
    valida = False
    if valor:
        try:
            import anthropic

            anthropic.Anthropic(api_key=valor).models.list(limit=1)
            valida = True
        except Exception:
            valida = False

    chave.valida = valida
    chave.verificada_em = timezone.now()
    chave.save(update_fields=["valida", "verificada_em"])
    return chave


def chave_precisa_reverificacao(chave: ChaveApiClaude) -> bool:
    if chave.verificada_em is None:
        return True
    return timezone.now() - chave.verificada_em > INTERVALO_REVERIFICACAO
