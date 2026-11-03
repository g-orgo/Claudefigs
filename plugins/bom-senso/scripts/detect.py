"""Spots prompts that look like corrections and finds the examples related to a prompt.

The detector favours recall on purpose: it only asks the model to look closer, and the model
discards new requests. Phrases come from the user's real corrections, in pt-BR.
"""
import re
import unicodedata

# Text that the user did not type as a reaction to the agent's work.
NOT_USER_PREFIXES = ("another claude session sent", "resultados do split", "pedido original", "pedido do usuario",
                     "original request", "this session is being continued")
PLUGIN_MESSAGE = re.compile(r"the [\w-]+ plugin sent a message")
OWN_SLIP = re.compile(r"\b(falei|escrevi|digitei|notei) errado\b|\bperdao\b|\bfoi mal\b|\berro meu\b")
CORRECTION = re.compile("|".join((
    r"\bvoce (nao|esqueceu|ignorou|alucinou|deixou|errou|entendeu errado|esta enganado)\b",
    r"\balucin",
    r"\bnao era\b",
    r"\bera (pra|para) (ser|ter|ficar|estar)\b",
    r"\bnao (foi (feito|aplicado|alterado|atualizado|corrigido|isso)|mudou|resolveu|pegou|ficou bom|funcionou)\b",
    r"\b(continua|continuam) (sem|ruim|na mesma|igual|errad|muito|com|aparecendo|sendo|dando)",
    r"\bainda nao\b",
    r"\b(esqueceu|faltou|ignorad[oa]|ignorou)\b",
    r"\b(como|o que) (eu )?(pedi|mencionei|falei|disse)\b",
    r"\b(eu|ja) (pedi|mencionei|falei|disse)\b",
    r"\bmencionei\b",
    r"\bbom senso\b|\bobvio\b|\bproblema recorrente\b",
    r"\b(esta|ta|veio|vieram|ficou) errad[oa]s?\b",
    r"\bde novo\b|\bnovamente\b",
    r"\bdeveria(m)?\b|\bdevia(m)?\b",
)))


def normalize(text):
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def is_user_text(prompt):
    """False for empty prompts, slash commands and messages sent by plugins or other sessions."""
    text = normalize(prompt).strip()
    return bool(text) and not (text.startswith(("/", "<") + NOT_USER_PREFIXES) or PLUGIN_MESSAGE.match(text))


def correction_signal(prompt):
    """Returns the phrase that looks like a correction, or None."""
    text = normalize(prompt).strip()
    if not is_user_text(prompt) or OWN_SLIP.search(text):
        return None
    match = CORRECTION.search(text)
    return match.group(0) if match else None


def related_examples(prompt, examples, limit=2, min_hits=3):
    """Examples sharing at least min_hits keywords with the prompt, the best matches first."""
    words = set(re.findall(r"[a-z0-9-]+", normalize(prompt)))
    scored = []
    for example in examples:
        hits = sum(1 for keyword in example.get("keywords", []) if keyword in words)
        if hits >= min_hits:
            scored.append((hits, example))
    scored.sort(key=lambda pair: -pair[0])
    return [example for _, example in scored[:limit]]
