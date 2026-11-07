"""Desktop clipboard access for the composer: reads and writes text, saves images, and recognizes pasted image paths."""
import os
import re
import subprocess
import time
from urllib.parse import unquote, urlparse

IMAGE_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/gif": "gif", "image/webp": "webp"}
IMAGE_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif", "webp"})
IMAGE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", "prompt-splitter-images")
TIMEOUT = 2.0  # seconds per clipboard tool call; a stuck tool must never freeze the view.
UNAVAILABLE = "unavailable"
_TOKEN = re.compile(r"""'[^']*'|"[^"]*"|(?:\\.|\S)+""")


def _run(argv: list[str]) -> bytes | None:
    """Stdout of a clipboard tool, or None when it is missing, fails or times out."""
    try:
        done = subprocess.run(argv, capture_output=True, timeout=TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _save_image(data: bytes, mime: str) -> str | None:
    """Writes the image bytes under the state folder and returns the file path, or None on failure."""
    try:
        os.makedirs(IMAGE_DIR, exist_ok=True)
        path = os.path.join(IMAGE_DIR, f"{int(time.time() * 1000)}.{IMAGE_TYPES[mime]}")
        with open(path, "wb") as handle:
            handle.write(data)
        return path
    except OSError:
        return None


def _read_with(list_types: list[str], image_argv, text_argv) -> tuple[str, str] | None:
    """Shared Wayland/X11 logic: an offered image type wins, otherwise the text is read."""
    offered = _run(list_types)
    if offered is None:
        return None
    mime = next((t for t in offered.decode("utf-8", "replace").split() if t in IMAGE_TYPES), None)
    if mime:
        data = _run(image_argv(mime))
        path = _save_image(data, mime) if data else None
        return ("image", path) if path else None
    text = _run(text_argv)
    return ("text", text.decode("utf-8", "replace")) if text is not None else None


def _read_wayland() -> tuple[str, str] | None:
    return _read_with(
        ["wl-paste", "--list-types"],
        lambda mime: ["wl-paste", "--type", mime],
        ["wl-paste", "--no-newline"],
    )


def _read_x11() -> tuple[str, str] | None:
    # Unverified here: xclip is not installed on the development machine, so this path is a best-effort fallback.
    return _read_with(
        ["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"],
        lambda mime: ["xclip", "-selection", "clipboard", "-t", mime, "-o"],
        ["xclip", "-selection", "clipboard", "-o"],
    )


def read_clipboard() -> tuple[str, str]:
    """Returns ("image", saved path), ("text", text) or (UNAVAILABLE, ""); Wayland is tried before X11."""
    for reader in (_read_wayland, _read_x11):
        result = reader()
        if result is not None:
            return result
    return (UNAVAILABLE, "")


def write_clipboard(text: str) -> bool:
    """Puts text on the desktop clipboard without waiting; False when the tool is missing or fails to start."""
    argv = ["wl-copy"] if os.environ.get("WAYLAND_DISPLAY") else ["xclip", "-selection", "clipboard", "-i"]
    try:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, FileNotFoundError):
        return False
    try:
        process.stdin.write(text.encode("utf-8"))
        process.stdin.close()
    except (OSError, ValueError):
        return False
    return True


def _clean_path(token: str) -> str | None:
    """The absolute path of one pasted token when it is an existing image file, else None."""
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"":
        token = token[1:-1]
    if token.startswith("file://"):
        path = unquote(urlparse(token).path)
    else:
        path = re.sub(r"\\(.)", r"\1", token)
    if os.path.splitext(path)[1][1:].lower() not in IMAGE_EXTENSIONS or not os.path.isfile(path):
        return None
    return os.path.abspath(path)


def image_paths_from_paste(text: str) -> list[str] | None:
    """The image files named by a paste (paths, quoted paths, file:// URIs or escaped spaces), or None if any token is not one."""
    tokens = _TOKEN.findall(text.strip())
    if not tokens:
        return None
    paths = []
    for token in tokens:
        path = _clean_path(token)
        if path is None:
            return None
        paths.append(path)
    return paths
