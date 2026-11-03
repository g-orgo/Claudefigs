#!/usr/bin/env python3
"""Record of common-sense examples: built-in seeds plus the user's private entries.

User data lives in ~/.claude/state/bom-senso/, outside the plugin, so that it survives plugin
updates and never reaches the public config repository.
"""
import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEEDS = ROOT / "data" / "seed_examples.json"
MUTE_TTL = 7 * 86400
CATEGORIES = ("contexto-existente", "consistencia", "cobertura", "verificacao", "leitura-literal",
              "estados-obvios", "regressao", "referencia", "autonomia", "pipeline")


def state_dir():
    return Path(os.environ.get("BOM_SENSO_STATE") or Path.home() / ".claude/state/bom-senso")


def seeds():
    return json.loads(SEEDS.read_text(encoding="utf-8"))


def user_examples():
    path = state_dir() / "examples.jsonl"
    if not path.exists():
        return []
    rows = (line for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return [json.loads(row) for row in rows]


def _save(rows):
    path = state_dir() / "examples.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def add(category, situation, expected, rule, keywords=()):
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    entry = {"id": uuid.uuid4().hex[:8], "category": category, "situation": situation,
             "expected": expected, "rule": rule, "keywords": list(keywords),
             "count": 1, "created": time.strftime("%Y-%m-%d")}
    _save(user_examples() + [entry])
    return entry


def _update(example_id, change):
    rows = user_examples()
    kept = [r for r in rows if not (r["id"] == example_id and change(r))]
    if not any(r["id"] == example_id for r in rows):
        raise KeyError(example_id)
    _save(kept)


def bump(example_id):
    """Counts one more occurrence of a recorded situation."""
    def increment(row):
        row["count"] = row.get("count", 1) + 1
        return False
    _update(example_id, increment)


def remove(example_id):
    _update(example_id, lambda row: True)


def relevant_user_rules(limit):
    """The user's rules, the recurring ones first. Every example applies to every project."""
    return sorted(user_examples(), key=lambda r: -r.get("count", 1))[:limit]


def _muted():
    path = state_dir() / "muted.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def mute(session_id):
    now = time.time()
    entries = {k: v for k, v in _muted().items() if now - v < MUTE_TTL}
    entries[session_id] = now
    path = state_dir() / "muted.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")


def is_muted(session_id):
    return session_id in _muted()


def _print_list(category):
    rows = [dict(r, id=f"seed:{r['id']}") for r in seeds()] + user_examples()
    for row in rows:
        if category and row["category"] != category:
            continue
        print(f"[{row['id']}] {row['category']} ({row.get('count', 1)}x)\n"
              f"  Situacao: {row['situation']}\n  Esperado: {row['expected']}\n  Regra: {row['rule']}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bom-senso")
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("add")
    new.add_argument("--category", required=True, choices=CATEGORIES)
    for field in ("situation", "expected", "rule"):
        new.add_argument(f"--{field}", required=True)
    new.add_argument("--keywords", default="", help="comma separated, accent-free, lowercase")
    listing = sub.add_parser("list")
    listing.add_argument("--category", choices=CATEGORIES)
    listing.add_argument("--remove", metavar="ID")
    for name in ("bump", "mute"):
        sub.add_parser(name).add_argument("target")
    sub.add_parser("status")
    args = parser.parse_args(argv)

    if args.command == "add":
        words = [w.strip() for w in args.keywords.split(",") if w.strip()]
        entry = add(args.category, args.situation, args.expected, args.rule, words)
        print(f"Registrado: {entry['id']}")
    elif args.command == "list" and args.remove:
        remove(args.remove)
        print(f"Removido: {args.remove}")
    elif args.command == "list":
        _print_list(args.category)
    elif args.command == "bump":
        bump(args.target)
        print(f"Contado: {args.target}")
    elif args.command == "mute":
        mute(args.target)
        print("Bom senso nao vai mais perguntar nesta sessao.")
    elif args.command == "status":
        print(f"Bom senso ativo. Exemplos: {len(seeds())} de fabrica, {len(user_examples())} seus.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, ValueError) as error:
        sys.exit(f"Erro: {error}")
