#!/usr/bin/env python3
"""Publishes the Claude configs and local plugins into this repository.

Only allowlisted files are copied, private fields are removed from the copies, and the result is
scanned in a temporary folder. If the scan finds anything, the repository is left untouched.
Commit and push are done by hand after reviewing `git status` and `git diff --stat`.
"""
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAUDE = Path.home() / ".claude"
LOCAL_PLUGINS = CLAUDE / "local-plugins"

# Anything else in settings.json, such as autoMode (it describes private repositories), stays out.
SETTINGS_KEYS = {
    "hooks", "statusLine", "enabledPlugins", "extraKnownMarketplaces", "modelSettings",
    "autoCompactWindow", "autoCompactEnabled", "theme",
}
# Plugin paths left out: working notes (HANDOFF.md holds verbatim requests and ids) and generated files.
PLUGIN_SKIP_NAMES = {"HANDOFF.md", "__pycache__", ".env", ".DS_Store"}
PLUGIN_SKIP_SUFFIXES = {".pyc", ".log", ".jsonl"}
# The design system reference in CLAUDE.md names a private project and its path.
PRIVATE_REFERENCE = re.compile(r"the \w+ design system \(`/media/orgo/HD/[^`]*`\)")
PUBLIC_REFERENCE = "a private project's design system"
# Pieces are joined so that this file does not match its own scan.
FORBIDDEN = [re.compile(p) for p in (
    "sk" + r"-ant-",
    r"\bgh" + r"[pousr]_[A-Za-z0-9]{20,}",
    "github" + r"_pat_",
    r"\bAKIA" + r"[0-9A-Z]{16}\b",
    r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}",
    "BEGIN [A-Z ]*PRIVATE " + "KEY",
    r"(?i)authorization:\s*(?:bearer|token|basic)\s+[A-Za-z0-9._~+/=-]{16,}",
    r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{24,}",
    r"""(?i)(?:api[_-]?key|password|passwd|secret|token)["']?\s*[:=]\s*["'][^"'\s$<{]{8,}["']""",
    r"[\w.+-]+@(?:gmail|hotmail|outlook|yahoo)\.",
    "/media/orgo/" + "HD/",
)]


def without_email(value):
    """Returns a manifest with every `email` field removed, at any depth."""
    if isinstance(value, dict):
        return {k: without_email(v) for k, v in value.items() if k != "email"}
    if isinstance(value, list):
        return [without_email(v) for v in value]
    return value


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def skip_in_plugin(folder, names):
    skipped = {n for n in names if n in PLUGIN_SKIP_NAMES or Path(n).suffix in PLUGIN_SKIP_SUFFIXES}
    if Path(folder).name == ".claude-plugin" and "types" in names:
        skipped.add("types")
    return skipped


def build(out):
    """Writes the published tree into `out`."""
    config = out / "claude"
    (config / "agents").mkdir(parents=True)
    (config / "hooks").mkdir()
    text = (CLAUDE / "CLAUDE.md").read_text(encoding="utf-8")
    (config / "CLAUDE.md").write_text(PRIVATE_REFERENCE.sub(PUBLIC_REFERENCE, text), encoding="utf-8")
    settings = json.loads((CLAUDE / "settings.json").read_text(encoding="utf-8"))
    write_json(config / "settings.json", {k: v for k, v in settings.items() if k in SETTINGS_KEYS})
    shutil.copy2(CLAUDE / "statusline.py", config / "statusline.py")
    for path in (CLAUDE / "agents").glob("*.md"):
        shutil.copy2(path, config / "agents" / path.name)
    for path in (CLAUDE / "hooks").glob("*.py"):
        shutil.copy2(path, config / "hooks" / path.name)

    marketplace = json.loads((LOCAL_PLUGINS / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    write_json(out / ".claude-plugin/marketplace.json", without_email(marketplace))
    for plugin in (LOCAL_PLUGINS / "plugins").iterdir():
        target = out / "plugins" / plugin.name
        shutil.copytree(plugin, target, ignore=skip_in_plugin)
        manifest = target / ".claude-plugin/plugin.json"
        write_json(manifest, without_email(json.loads(manifest.read_text(encoding="utf-8"))))


def scan(out):
    """Returns `path: pattern` for each match in the published tree."""
    hits = []
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        text = path.read_text(encoding="utf-8", errors="replace")
        hits += [f"{path.relative_to(out)}: {p.pattern}" for p in FORBIDDEN if p.search(text)]
    return hits


def main():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        build(out)
        hits = scan(out)
        if hits:
            print("Sync aborted, nothing was changed. Forbidden content found:", file=sys.stderr)
            print("\n".join(hits), file=sys.stderr)
            return 1
        for name in ("claude", "plugins", ".claude-plugin"):
            shutil.rmtree(REPO / name, ignore_errors=True)
            shutil.copytree(out / name, REPO / name)
    print("Sync done. Review with `git status` and `git diff --stat`, then commit and push.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
