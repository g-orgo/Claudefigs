"""Answering, from the office box, the questions (AskUserQuestion) a dispatched session is waiting on."""
import textwrap

from .composer import BORDER_PX, FADED, GOLD_FOCUSED, INK_BROWN, PAD_CELLS, PARCHMENT, Composer
from .model import Worker
from .term import Frame

TEXT_LINES = 2  # wrapped lines of the current question's text; the rest is clipped.


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[:max(0, width - 3)] + "..."


class Asking:
    """The questions of one worker shown in the box: current question, highlighted and chosen options, answers."""

    def __init__(self, worker: Worker):
        self.worker = worker
        self.questions = list(worker.questions)
        self.asks = tuple(dict.fromkeys(q.ask for q in self.questions))
        self.current = 0
        self.highlight = [0] * len(self.questions)
        self.chosen: list[set[int]] = [set() for _ in self.questions]
        self.answers: list[str | None] = [None] * len(self.questions)
        self.composer = Composer()  # free text: "other" answer of the current question.
        self._rows: list[tuple[int, int, int]] = []  # (terminal row, question, option or -1) of the last draw.
        self._cols = (0, 0)

    @property
    def key(self) -> tuple:
        return (self.worker.id, self.asks)

    def _options(self) -> tuple:
        return self.questions[self.current].options

    def move(self, delta: int) -> None:
        count = len(self._options())
        if count:
            self.highlight[self.current] = (self.highlight[self.current] + delta) % count

    def toggle(self) -> None:
        """Space: marks the highlighted option; a single choice keeps only it."""
        if not self._options():
            return
        index, chosen = self.highlight[self.current], self.chosen[self.current]
        if self.questions[self.current].multi:
            chosen ^= {index}
        else:
            chosen.clear()
            chosen.add(index)

    def next(self, delta: int = 1) -> None:
        self.current = (self.current + delta) % len(self.questions)

    def confirm(self) -> bool | None:
        """Enter: answers the current question; True when every question has an answer, None when nothing was taken."""
        question = self.questions[self.current]
        text = self.composer.prompt_text().strip()
        if text:
            answer = text
        elif question.options:
            picked = sorted(self.chosen[self.current]) if question.multi else []
            picked = picked or [self.highlight[self.current]]
            answer = ", ".join(question.options[i][0] for i in picked)
        else:
            return None
        self.answers[self.current] = answer
        self.composer.clear()
        pending = [i for i, a in enumerate(self.answers) if a is None]
        if not pending:
            return True
        self.current = next((i for i in pending if i > self.current), pending[0])
        return False

    def pick(self, question: int, option: int) -> bool | None:
        """A click: on another question it only brings it forward; on an option it marks it, and a single choice confirms."""
        if question != self.current:
            self.current = question
            return False
        if option < 0:
            return False
        self.highlight[question] = option
        self.toggle()
        return False if self.questions[question].multi else self.confirm()

    def message(self) -> str:
        lines = ["Respostas do usuario as suas perguntas (enviadas pelo escritorio):"]
        lines += [f'- "{q.text}" = "{a}"' for q, a in zip(self.questions, self.answers)]
        return "\n".join(lines)

    def _head(self, index: int) -> str:
        question = self.questions[index]
        number = f"{index + 1}. " if len(self.questions) > 1 else ""
        return number + (f"[{question.header}] " if question.header else "") + question.text

    def layout(self, width: int, current: int | None = None) -> list[tuple[str, str, int, int]]:
        """Rows of the block as (text, kind, question, option); kind is "text", "option", "summary" or "answered"."""
        current = self.current if current is None else current
        width = max(width, 12)  # a box this narrow is not drawn; the layout only has to stay valid.
        rows: list[tuple[str, str, int, int]] = []
        for qi, question in enumerate(self.questions):
            answer = self.answers[qi]
            if qi != current:
                tail = f"  -> {answer}" if answer is not None else ""
                rows.append((_clip(self._head(qi), width - len(tail)) + tail, "answered" if tail else "summary", qi, -1))
                continue
            wrapped = textwrap.wrap(self._head(qi), width) or [""]
            if len(wrapped) > TEXT_LINES:
                wrapped = wrapped[:TEXT_LINES - 1] + [_clip(" ".join(wrapped[TEXT_LINES - 1:]), width)]
            rows += [(line, "text", qi, -1) for line in wrapped]
            for oi, (label, description) in enumerate(question.options):
                marked = oi in self.chosen[qi]
                mark = ("[x]" if marked else "[ ]") if question.multi else ("(o)" if marked else "( )")
                rows.append((_clip(f"{mark} {label}" + (f"  {description}" if description else ""), width), "option", qi, oi))
        return rows

    def block_rows(self, width: int) -> int:
        """Rows the block needs at its tallest, so the box keeps one height while the current question changes."""
        inner = width - 2 * PAD_CELLS
        return max(len(self.layout(inner, qi)) for qi in range(len(self.questions)))

    def draw(self, frame: Frame, col: int, top: int, width: int, rows: int) -> None:
        """Draws the block in `rows` rows from `top`, scrolled so the current question stays in view."""
        inner = width - 2 * PAD_CELLS
        layout = self.layout(inner)
        focus = [i for i, row in enumerate(layout) if row[2] == self.current]
        start = max(0, min(focus[0], len(layout) - rows)) if len(layout) > rows else 0
        if focus and focus[-1] >= start + rows:
            start = focus[-1] - rows + 1
        left, right = col + BORDER_PX + 1, min(col + width - BORDER_PX - 1, frame.cols)
        self._rows, self._cols = [], (left, right)
        for offset, (text, kind, qi, oi) in enumerate(layout[start:start + rows]):
            row = top + offset
            if not 0 <= row < frame.nrows:
                continue
            self._rows.append((row, qi, oi))
            lit = kind == "option" and oi == self.highlight[qi] and self.composer.focused
            bg = GOLD_FOCUSED if lit else PARCHMENT
            cells = frame.cells[row]
            for x in range(left, right):
                cells[x] = (" ", None, bg, False)
            fg = FADED if kind == "summary" else INK_BROWN
            label_end = len(self.questions[qi].options[oi][0]) + 4 if kind == "option" else len(text)
            for k, ch in enumerate(text):
                x = col + PAD_CELLS + k
                if x < right - 2:
                    dim = kind == "option" and k >= label_end and not lit
                    cells[x] = (ch, FADED if dim else fg, bg, kind == "text" or (lit and k < label_end))

    def row_at(self, col: int, row: int) -> tuple[int, int] | None:
        """(question, option) under a click in the last drawn block; option is -1 off the options."""
        if not self._cols[0] <= col < self._cols[1]:
            return None
        return next(((qi, oi) for r, qi, oi in self._rows if r == row), None)
