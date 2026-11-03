"""UserPromptSubmit hook: hint the split skill when a prompt, or a file it points to, lists several requests.

Numbered items are counted in the prompt and in the files it points to; the prompt alone is also
checked for several unnumbered requests (separate lines, bullets, sentences or connectors).

Never fails: any error results in silence and exit code 0.
"""

import json
import os
import re
import sys
import unicodedata

OPT_OUT = "[nosplit]"
MAX_FILE_BYTES = 300 * 1024
MAX_FILES = 5
# Numbered item at a line start: "1)", "1.", "1 -", "(1)".
ITEM_RE = re.compile(r"^\s*(?:\(\d+\)|\d+\s*[).]|\d+\s+-)", re.MULTILINE)
TRAILING_PUNCT = ".,;:!?)]}>'\""
LEADING_NOISE = "\"'`([{<"
PATH_SUFFIXES = (".md", ".txt", ".markdown")
NOT_USER_PREFIXES = (
    "Another Claude session sent a message",
    "The split-pane plugin sent a message",
    "Resultados do split",
)

def is_excluded(path: str) -> bool:
    """True when the path lives inside the plugin root or inside ~/.claude/ (never user work files)."""
    real = os.path.realpath(path)
    hooks_dir = os.path.dirname(os.path.realpath(__file__))
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(hooks_dir)
    roots = [os.path.realpath(plugin_root), os.path.realpath(os.path.expanduser("~/.claude/"))]
    return any(real == root or real.startswith(root.rstrip(os.sep) + os.sep) for root in roots)


ASK = (
    "Invoke the prompt-splitter `split` skill right away with these {n} requests, without asking "
    "the user first (the user's standing choice is to always split). Only keep the work in this "
    "session if the user wrote [nosplit] or the requests turn out to be one group."
)
HINT = "prompt-splitter: {source} contains {n} numbered requests. Do NOT start the work yet. " + ASK
HINT_UNNUMBERED = (
    "prompt-splitter: this prompt seems to contain {n} separate unnumbered requests. "
    "Do NOT start the work yet. If it is really a single request with details, ignore this note "
    "and proceed normally. Otherwise " + ASK[0].lower() + ASK[1:]
)

# Unnumbered detection works on lowercase, accent-free text.
# Verbs that open a request: pt-BR imperative and infinitive, English base form. Reading and
# constraint verbs ("leia", "use", "mantenha", "keep", "avoid") are left out on purpose.
REQUEST_VERBS = frozenset("""
adicione adiciona adicionar crie cria criar corrija corrige corrigir conserte conserta consertar
arrume arruma arrumar remova remove remover apague apaga apagar exclua exclui excluir deletar
mude muda mudar altere altera alterar troque troca trocar atualize atualiza atualizar
implemente implementa implementar faca faz fazer coloque coloca colocar ponha bote bota botar
renomeie renomeia renomear mova move mover refatore refatora refatorar ajuste ajusta ajustar
melhore melhora melhorar configure configura configurar instale instala instalar
escreva escreve escrever documente documenta documentar investigue investiga investigar
otimize otimiza otimizar traduza traduz traduzir gere gera gerar migre migra migrar
separe separa separar integre integra integrar substitua substitui substituir inclua inclui incluir
tire tira tirar deixe deixa deixar monte monta montar construa constroi construir
desenvolva desenvolve desenvolver padronize padroniza padronizar limpe limpa limpar
publique publica publicar converta converte converter
reduza reduz reduzir aumente aumenta aumentar diminua diminui diminuir esconda esconde esconder
mostre mostra mostrar exiba exibe exibir centralize centraliza centralizar alinhe alinha alinhar
carregue carrega carregar salve salva salvar ative ativa ativar desative desativa desativar
patcheie patchear revise revisa revisar teste testa testar aplique aplica aplicar
add create fix delete change update implement make put rename refactor adjust improve
install write document investigate optimize translate generate migrate integrate replace
include build bump clean drop convert upgrade rewrite redesign rework
reduce increase decrease hide show move align enable disable load patch remove
""".split())
# Desire phrases may follow a topic ("nos posts eu queria que ..."), so they match anywhere.
DESIRE_RE = re.compile(
    r"\b(?:quero|queria|preciso|precisava|gostaria|seria bom)(?: que)?\b|"
    r"\bi (?:want|need|would like|'d like)\b"
)
# Problem reports ("o botao nao esta no padrao", "parece que nao carrega") are requests to fix.
REPORT_RE = re.compile(
    r"\bparece que\b|\bnao (?:esta|estao|ta|tao|carrega|carregam|funciona|funcionam|aparece|aparecem|"
    r"abre|abrem|salva|salvam|mostra|mostram|rola|segue|seguem)\b|\b(?:esta|ta) (?:quebrad|errad|ruim|bugad)|"
    r"\bdeveria\b|\bdeveriam\b|\bdevem? (?:ficar|ser|estar|aparecer|sair)\b|"
    r"\b(?:doesn't|does not|don't|isn't|is not|aren't) (?:work|load|show|appear|match)|\bis (?:broken|wrong)\b"
)
# A bare "e"/"and" splits two requests only when both sides are requests on their own.
WEAK_AND_RE = re.compile(r"\s+(?:e|and)\s+")
NOT_REQUEST_RE = re.compile(r"^make sure\b")
# "add tests" style follow-ups belong to the request before them.
FOLLOWUP_VERBS = frozenset("adicione adicionar add crie criar create escreva escrever write rode rodar run cubra cover".split())
TESTS_RE = re.compile(r"\b(?:tests?|testes?|specs?)\b")
LEADING_FILLER_RE = re.compile(
    r"^(?:e|and|entao|depois|then|agora|now|ok|por favor|please|pls|can you|could you|would you|"
    r"voce pode|voce poderia|voce consegue|pode|poderia|consegue|vamos|let's|lets)\b[\s,:]*"
)
# Connectors that start another request; the "new topic" ones count even without a verb after them.
CONNECTOR_RE = re.compile(
    r"(?:^|[\s,;.]+)(?:(?:e|and)\s+)?(tambem|alem disso|e ainda|aproveitando|also|in addition|"
    r"additionally|besides that|on top of that|outra coisa|mais uma coisa|another thing|one more thing)"
    r"\b[\s,:;.-]*"
)
NEW_TOPIC = frozenset(("outra coisa", "mais uma coisa", "another thing", "one more thing"))
# A lead line ending in ":" before bullets lists separate requests only when it names a collection.
COLLECTION_RE = re.compile(
    r"\b(?:coisas|pedidos|tarefas|itens|ajustes|correcoes|mudancas|alteracoes|melhorias|pontos|"
    r"things|tasks|items|changes|fixes|requests|issues|todos)\b"
)
BULLET_RE = re.compile(r"^\s*[-*+\u2022]\s+(?:\[[ x]\]\s+)?")
FENCE_RE = re.compile(r"```.*?(?:```|$)", re.DOTALL)
SENTENCE_RE = re.compile(r"(?<=[.!?;])\s+")
MIN_REQUEST_WORDS = 3


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def is_request(segment: str, after_connector: str | None) -> bool:
    text = segment.strip(" ,:;.-")
    while True:
        stripped = LEADING_FILLER_RE.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    words = re.findall(r"[a-z']+", text)
    if len(words) < MIN_REQUEST_WORDS or NOT_REQUEST_RE.match(text):
        return False
    if words[0] in FOLLOWUP_VERBS and TESTS_RE.search(text) and len(words) <= 10:
        return False
    if words[0] in REQUEST_VERBS or DESIRE_RE.search(text) or REPORT_RE.search(text):
        return True
    return after_connector in NEW_TOPIC


def clause_requests(segment: str, connector: str | None) -> tuple[int, int]:
    """Return (requests, requests joined by a bare "e"/"and") in one connector-delimited segment."""
    head, *rest = WEAK_AND_RE.split(segment)
    joined = sum(is_request(part, None) for part in rest)
    return int(is_request(head, connector)) + joined, joined


def line_requests(line: str) -> tuple[int, int]:
    """Return (requests, requests opened by a connector) found in one line."""
    count = joined = 0
    for sentence in SENTENCE_RE.split(line):
        pieces = CONNECTOR_RE.split(sentence)
        # split() alternates text and captured connector: [text, connector, text, ...].
        found, weak = clause_requests(pieces[0], None)
        count += found
        joined += weak
        for i in range(1, len(pieces) - 1, 2):
            found, weak = clause_requests(pieces[i + 1], pieces[i])
            count += found
            joined += (found > 0) + weak
    return count, joined


def count_unnumbered(prompt: str) -> int:
    """Count separate unnumbered requests; 0 unless the prompt clearly holds several."""
    text = FENCE_RE.sub("\n", normalize(prompt))
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith(">")]
    total = lines_with_requests = connectors = 0
    details_of_lead = False
    for line in lines:
        bullet = BULLET_RE.match(line)
        if bullet:
            if details_of_lead:
                continue
            line = line[bullet.end():]
        else:
            stripped = line.strip()
            details_of_lead = False
            if stripped.endswith(":"):
                if COLLECTION_RE.search(stripped):
                    continue
                details_of_lead = line_requests(stripped)[0] > 0
        found, joined = line_requests(line)
        if found:
            total += found
            lines_with_requests += 1
            connectors += joined
    # Two requests are enough: the split skill still asks before splitting anything.
    if total >= 2:
        return total
    return 0


def clean_token(token: str) -> str:
    token = token.strip()
    while token and token[0] in LEADING_NOISE:
        token = token[1:]
    while token and token[-1] in TRAILING_PUNCT:
        token = token[:-1]
    return token


def file_candidates(prompt: str) -> list[str]:
    found = []
    for raw in prompt.split():
        token = clean_token(raw)
        if token.startswith("@"):
            token = token[1:]
        elif "/" not in token and not token.lower().endswith(PATH_SUFFIXES):
            continue
        if token and token not in found:
            found.append(token)
    return found[:MAX_FILES]


def count_in_file(token: str, cwd: str) -> tuple[str, int] | None:
    path = os.path.expanduser(token)
    if not os.path.isabs(path):
        path = os.path.join(cwd or os.getcwd(), path)
    if not os.path.isfile(path) or os.path.getsize(path) > MAX_FILE_BYTES:
        return None
    with open(path, encoding="utf-8", errors="ignore") as fh:
        return path, len(ITEM_RE.findall(fh.read()))


def main() -> int:
    try:
        if os.environ.get("CLAUDE_SPLIT_CHILD") == "1":
            return 0
        data = json.loads(sys.stdin.read() or "{}")
        prompt = data.get("prompt") or ""
        if not isinstance(prompt, str) or not prompt.strip():
            return 0
        if prompt.lstrip().startswith("/") or OPT_OUT in prompt:
            return 0
        if prompt.lstrip().startswith(NOT_USER_PREFIXES):
            return 0
        count = len(ITEM_RE.findall(prompt))
        if count >= 2:
            print(HINT.format(source="this prompt", n=count))
            return 0
        unnumbered = count_unnumbered(prompt)
        if unnumbered:
            print(HINT_UNNUMBERED.format(n=unnumbered))
            return 0
        cwd = data.get("cwd") or os.getcwd()
        for token in file_candidates(prompt):
            candidate = os.path.join(cwd, os.path.expanduser(token))
            if is_excluded(candidate):
                continue
            result = count_in_file(token, cwd)
            if result and result[1] >= 2:
                print(HINT.format(source=f"the file {result[0]}", n=result[1]))
                break
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
