"""Suggestions for the composer: slash commands and project files, cached for a short time."""

import json
import os
import time

CACHE_SECONDS = 30.0
MAX_FILES = 5000  # files walked per directory before the listing stops growing.
SKIP_DIRS = {"node_modules", "__pycache__", "venv", "dist", "build"}
DESCRIPTION_CHARS = 60

_commands_cache: dict[str, tuple[float, list[tuple[str, str]]]] = {}
_files_cache: dict[str, tuple[float, list[str]]] = {}


def clear_cache() -> None:
    _commands_cache.clear()
    _files_cache.clear()


def _fresh(cache: dict, key: str):
    hit = cache.get(key)
    if hit is not None and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    return None


def _description(path: str, is_skill: bool) -> str:
    """First meaningful line of a command or skill file; a skill's frontmatter `description:` wins."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            head = handle.read(4000).splitlines()
    except OSError:
        return ""
    described = _frontmatter_value(path, "description")
    if described:
        return described[:DESCRIPTION_CHARS]
    if is_skill:
        for line in head:
            if line.startswith("description:"):
                return line.split(":", 1)[1].strip().strip("\"'")[:DESCRIPTION_CHARS]
    # Without a description, the first body line after any frontmatter block stands in.
    body = head
    if head and head[0].strip() == "---":
        closing = next((i for i, line in enumerate(head[1:], 1) if line.strip() == "---"), 0)
        body = head[closing + 1:]
    for line in body:
        text = line.strip().lstrip("#").strip()
        if text and text != "---" and not text.startswith(("name:", "description:")):
            return text[:DESCRIPTION_CHARS]
    return ""


def _from_commands_dir(root: str) -> list[tuple[str, str]]:
    """Markdown files under `root`; a file in a subfolder is named `folder:file`, as Claude Code does."""
    found = []
    if not os.path.isdir(root):
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        rel = os.path.relpath(dirpath, root)
        prefix = "" if rel == "." else rel.replace(os.sep, ":") + ":"
        for filename in sorted(filenames):
            if filename.endswith(".md"):
                name = prefix + filename[:-3]
                found.append((name, _description(os.path.join(dirpath, filename), False)))
    return found


def _frontmatter_value(path: str, key: str) -> str:
    """Value of `key:` inside the file's leading `---` block, or "" when there is none."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            head = handle.read(4000).splitlines()
    except OSError:
        return ""
    if not head or head[0].strip() != "---":
        return ""
    for line in head[1:]:
        if line.strip() == "---":
            break
        if line.startswith(key + ":"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def _from_skills_dir(root: str, use_frontmatter_name: bool = False) -> list[tuple[str, str]]:
    found = []
    if not os.path.isdir(root):
        return found
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name, "SKILL.md")
        if os.path.isfile(path):
            label = (use_frontmatter_name and _frontmatter_value(path, "name")) or name
            found.append((label, _description(path, True)))
    return found


def _load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _install_path(entries: list, cwd: str) -> str | None:
    """The user-scope install of a plugin, else the project-scope one whose projectPath is cwd or a parent of it."""
    for entry in entries:
        if isinstance(entry, dict) and entry.get("scope") == "user" and entry.get("installPath"):
            return entry["installPath"]
    here = os.path.normpath(cwd) if cwd else ""
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("scope") != "project" or not entry.get("installPath"):
            continue
        project = os.path.normpath(entry.get("projectPath") or "")
        if here and project and (here == project or here.startswith(project.rstrip(os.sep) + os.sep)):
            return entry["installPath"]
    return None


def _from_plugins(cwd: str, home: str) -> list[tuple[str, str]]:
    """Commands and skills of enabled plugins, named `plugin:name`. Disabled plugins and missing installs are skipped."""
    found: list[tuple[str, str]] = []
    enabled = _load_json(os.path.join(home, "settings.json")).get("enabledPlugins")
    if not isinstance(enabled, dict):
        return found
    installed = _load_json(os.path.join(home, "plugins", "installed_plugins.json")).get("plugins")
    installed = installed if isinstance(installed, dict) else {}
    for key in sorted(enabled):
        if enabled[key] is not True:
            continue
        entries = installed.get(key)
        install = _install_path(entries if isinstance(entries, list) else [], cwd)
        if not install or not os.path.isdir(install):
            continue
        plugin = key.split("@", 1)[0]
        for name, desc in _from_commands_dir(os.path.join(install, "commands")):
            found.append((f"{plugin}:{name}", desc))
        for name, desc in _from_skills_dir(os.path.join(install, "skills"), use_frontmatter_name=True):
            found.append((f"{plugin}:{name}", desc))
    return found


def commands(cwd: str) -> list[tuple[str, str]]:
    """Slash commands as (name, description), sorted by name. Sources, first one wins on a name:
    the project's `.claude/commands`, then the user's `~/.claude/commands`, then user skills,
    then the enabled plugins' commands and skills."""
    cached = _fresh(_commands_cache, cwd)
    if cached is not None:
        return cached
    home = os.path.join(os.path.expanduser("~"), ".claude")
    merged: dict[str, str] = {}
    sources = (
        _from_commands_dir(os.path.join(cwd, ".claude", "commands")) if cwd else [],
        _from_commands_dir(os.path.join(home, "commands")),
        _from_skills_dir(os.path.join(home, "skills")),
        _from_plugins(cwd, home),
    )
    for found in sources:
        for name, desc in found:
            merged.setdefault(name, desc)
    result = sorted(merged.items())
    _commands_cache[cwd] = (time.monotonic(), result)
    return result


def _walk(cwd: str) -> list[str]:
    found: list[str] = []
    if not cwd or not os.path.isdir(cwd):
        return found
    for dirpath, dirnames, filenames in os.walk(cwd):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]
        for filename in filenames:
            if filename.startswith("."):
                continue
            found.append(os.path.relpath(os.path.join(dirpath, filename), cwd).replace(os.sep, "/"))
            if len(found) >= MAX_FILES:
                return found
    return found


def files(cwd: str, query: str, limit: int = 8) -> list[str]:
    """Project files under `cwd` whose relative path contains `query` (case-insensitive), best matches first.
    A match on the file name beats one on a folder name; shorter paths come first on ties."""
    listing = _fresh(_files_cache, cwd)
    if listing is None:
        listing = _walk(cwd)
        _files_cache[cwd] = (time.monotonic(), listing)
    q = query.lower()
    hits = [rel for rel in listing if q in rel.lower()]

    def rank(rel: str):
        base = rel.rsplit("/", 1)[-1].lower()
        tier = 0 if base.startswith(q) else 1 if q in base else 2
        return tier, len(rel), rel

    return sorted(hits, key=rank)[:limit]


def matches(all_commands: list[tuple[str, str]], query: str, limit: int = 8) -> list[tuple[str, str]]:
    """Commands whose name contains `query` (case-insensitive); names that start with it come first."""
    q = query.lower()
    hits = [(name, desc) for name, desc in all_commands if q in name.lower()]
    hits.sort(key=lambda item: (0 if item[0].lower().startswith(q) else 1, len(item[0]), item[0]))
    return hits[:limit]
