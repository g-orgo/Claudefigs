#!/usr/bin/env python3
"""Syncs the Claude configs into this repository, commits everything and pushes to origin main.

Single command, from any directory: python3 /var/home/Orgo/Claudefigs/scripts/publish.py

The scan from sync.py runs on the published tree and then on every file git would track, so a stray
file in the clone cannot reach the public repository either. There is no flag to skip it, and the
push is never forced.
"""
import subprocess
import sys
from collections import Counter
from pathlib import Path

import sync

REPO = sync.REPO
REMOTE = "origin"
BRANCH = "main"
UPSTREAM = f"{REMOTE}/{BRANCH}"
TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
SUBJECT_AREAS = 3


class PublishError(Exception):
    """A stop condition, with the message to show the user."""


def run(*args, stdin=None):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, input=stdin)


def git(*args, stdin=None):
    result = run(*args, stdin=stdin)
    if result.returncode:
        raise PublishError(f"`git {args[0]}` falhou:\n{(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def check_clone():
    if Path(git("rev-parse", "--show-toplevel")).resolve() != REPO.resolve():
        raise PublishError(f"{REPO} nao e a raiz de um repositorio git.")
    branch = run("symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    if branch != BRANCH:
        raise PublishError(f"O clone precisa estar em {BRANCH} e sem rebase pendente (atual: {branch or 'HEAD solto'}).")


def scan_repo():
    """Scans every file git would track. Runs before staging, so an abort leaves the index alone."""
    listed = git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    hits = sync.scan(REPO, [REPO / name for name in listed.split("\0") if name])
    if hits:
        raise PublishError("Publicacao abortada, conteudo proibido no clone:\n" + "\n".join(hits))


def area(path):
    parts = Path(path).parts
    return "/".join(parts[:2]) if parts[0] in ("claude", "plugins") and len(parts) > 1 else parts[0]


def commit_message(paths):
    areas = Counter(area(path) for path in paths)
    names = sorted(areas)
    subject = "chore: atualiza " + ", ".join(names[:SUBJECT_AREAS])
    if len(names) > SUBJECT_AREAS:
        subject += f" e mais {len(names) - SUBJECT_AREAS}"
    body = "\n".join(f"- {name}: {areas[name]} arquivo(s)" for name in names)
    return f"{subject}\n\n{body}\n\n{TRAILER}\n"


def commit_all():
    """Stages everything and commits. Returns False when there was nothing to commit."""
    git("add", "-A")
    paths = [name for name in git("diff", "--cached", "--name-only", "--no-renames", "-z").split("\0") if name]
    if not paths:
        return False
    git("commit", "-F", "-", stdin=commit_message(paths))
    return True


def divergence():
    """Returns (commits only on the remote, commits only here)."""
    behind, ahead = git("rev-list", "--left-right", "--count", f"{UPSTREAM}...HEAD").split()
    return int(behind), int(ahead)


def rebase_on_remote():
    result = run("pull", "--rebase", REMOTE, BRANCH)
    if result.returncode == 0:
        return
    conflicts = run("diff", "--name-only", "--diff-filter=U").stdout.split()
    run("rebase", "--abort")
    if conflicts:
        raise PublishError(
            "Conflito ao fazer rebase sobre o remoto, nada foi enviado:\n" + "\n".join(conflicts)
            + f"\nO commit local continua em {BRANCH}. Em {REPO}, rode `git pull --rebase`, resolva e publique de novo."
        )
    raise PublishError(f"`git pull --rebase` falhou, nada foi enviado:\n{(result.stderr or result.stdout).strip()}")


def bring_remote_commits():
    git("fetch", REMOTE, BRANCH)
    if divergence()[0]:
        rebase_on_remote()
        scan_repo()


def push():
    """Pushes without force. If the remote moved in the meantime, rebases once and tries again."""
    if run("push", REMOTE, BRANCH).returncode:
        bring_remote_commits()
        git("push", REMOTE, BRANCH)


def publish():
    check_clone()
    git("fetch", REMOTE, BRANCH)
    if sync.main():
        raise PublishError("Sync abortado. Corrija a origem do achado em ~/.claude e publique de novo.")
    scan_repo()
    commit_all()
    bring_remote_commits()
    pending = divergence()[1]
    if not pending:
        print(f"Nada mudou: {UPSTREAM} ja esta atualizado em {git('rev-parse', '--short', 'HEAD')}.")
        return
    push()
    print(f"Publicado em {UPSTREAM}: {git('rev-parse', '--short', 'HEAD')} ({pending} commit(s)).")
    print(git("log", "-1", "--format=%s"))


def main():
    try:
        publish()
    except PublishError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
