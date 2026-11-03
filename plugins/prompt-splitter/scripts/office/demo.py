"""Fake workers for the office viewer when no real split data is wanted."""
import time

from office.model import Line, Worker


def _lines(*pairs) -> list[Line]:
    return [Line(role=role, text=text) for role, text in pairs]


def demo_workers(now_ms: float | None = None) -> list[Worker]:
    """Eleven fake workers covering every state and activity."""
    now = time.time() * 1000.0 if now_ms is None else now_ms
    base = dict(session_id="", cwd="/demo/projeto")
    return [
        Worker(id="demo-1", name="split-ajustar-tela", title="Ajustar a tela de login",
               item_label="1", group="demo", room_title="Reorganizar o modulo de login", index=1, started_ms=now - 600_000,
               state="working", activity="code", after=[],
               lines=_lines(("voce", "Ajuste o espaçamento do formulário"),
                            ("tool", "Agora vou modificar o arquivo login_form.tsx"),
                            ("claude", "Agora vou trabalhar nas margens do cartão, vou modificar o arquivo card.css.")), **base),
        Worker(id="demo-2", name="split-revisar-docs", title="Revisar a documentação da API",
               item_label="2", group="demo", room_title="Reorganizar o modulo de login", index=2, started_ms=now - 590_000,
               state="working", activity="doc", after=[],
               lines=_lines(("voce", "Confira os exemplos de resposta"), ("tool", "Estou lendo o arquivo api.md")), **base),
        Worker(id="demo-3", name="split-cobertura-testes", title="Aumentar a cobertura de testes",
               item_label="3", group="demo", room_title="Reorganizar o modulo de login", index=3, started_ms=now - 580_000,
               state="thinking", activity="none", after=[], subagents=2,
               lines=_lines(("voce", "Cubra os casos de borda do parser"), ("tool", "Estou procurando \"def parse\" no código"),
                            ("claude", "Estou planejando os cenários de borda.")), **base),
        Worker(id="demo-4", name="split-pesquisa-lib", title="Pesquisar bibliotecas de cache",
               item_label="4", group="demo", room_title="Reorganizar o modulo de login", index=4, started_ms=now - 570_000,
               state="working", activity="delegate", after=[],
               lines=_lines(("tool", "Estou delegando a um subagent: pesquisar bibliotecas")), **base),
        Worker(id="demo-5", name="split-migracao", title="Escrever a migração de usuários",
               item_label="5", group="demo", room_title="Reorganizar o modulo de login", index=5, started_ms=now - 560_000,
               state="waiting", activity="none", after=[1],
               lines=_lines(("claude", "Estou aguardando o item 1 terminar.")), **base),
        Worker(id="demo-6", name="split-indices", title="Criar índices da tabela de pedidos",
               item_label="6", group="demo", room_title="Reorganizar o modulo de login", index=6, started_ms=now - 550_000,
               state="waiting", activity="none", after=[5],
               lines=_lines(("claude", "Estou aguardando o item 5 terminar.")), **base),
        Worker(id="demo-7", name="split-tema-escuro", title="Adicionar o tema escuro",
               item_label="7", group="demo", room_title="Reorganizar o modulo de login", index=7, started_ms=now - 540_000,
               state="waiting", activity="none", after=[1],
               lines=_lines(("claude", "Estou aguardando o item 1 terminar.")), **base),
        Worker(id="demo-8", name="split-permissoes", title="Confirmar regras de permissão",
               item_label="1", group="outra", room_title="Integrar pagamentos e permissoes", index=1, started_ms=now - 300_000,
               state="ask", activity="none", after=[],
               lines=_lines(("claude", "Devo manter o acesso de leitura para convidados?")), **base),
        Worker(id="demo-9", name="split-api-pagamento", title="Integrar a API de pagamento",
               item_label="2", group="outra", room_title="Integrar pagamentos e permissoes", index=2, started_ms=now - 290_000,
               state="blocked", activity="none", after=[],
               lines=_lines(("claude", "Terminei a etapa, aguardo você revisar.")), **base),
        Worker(id="demo-10", name="split-limpeza", title="Remover código morto do módulo antigo",
               item_label="1", group="terceira", room_title="Limpar modulos antigos", index=1, started_ms=now - 200_000,
               state="done", activity="none", after=[],
               lines=_lines(("claude", "Terminei a remoção, sem regressões.")), **base),
        Worker(id="demo-11", name="split-exportar-csv", title="Exportar relatório em CSV",
               item_label="1", group="terceira", room_title="Limpar modulos antigos", index=2, started_ms=now - 190_000,
               state="failed", activity="none", after=[],
               lines=_lines(("claude", "Algo falhou ao gerar o arquivo de saída, vou olhar o erro.")), **base),
    ]


def _spread(workers: list[Worker]) -> list[Worker]:
    """Gives the demo a session outside the working directory, so the warehouse differs from the hall."""
    for worker in workers:
        worker.in_cwd = worker.group != "terceira"
    return workers


class DemoSource:
    """Static demo source with the same shape as data.Poller."""

    def __init__(self) -> None:
        self._workers = _spread(demo_workers())

    def start(self) -> None:
        """No-op: the demo data is static."""

    def snapshot(self) -> list[Worker]:
        """Return the demo workers."""
        return list(self._workers)
