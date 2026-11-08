"""Turns the `add_user_message` response into a display answer.

Approximate footnotes (until CR-01): the model receives an instruction to put the document name in
square brackets after a sentence (`citation_instruction` in the configuration). Here we match those
names against `detailed_results_json`, number the documents in order of first citation, and use the
highest-scoring page of a fragment from that document as the footnote page.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from markdown_it import MarkdownIt

_md = MarkdownIt(
    "commonmark", {"html": False, "linkify": False, "typographer": False}
).enable("table")

CITATION_RE = re.compile(r"\s?\[([^\[\]\n]{3,240})\]")
PLACEHOLDER = "⁣FN{}⁣"
PLACEHOLDER_RE = re.compile("⁣FN(\\d+)⁣")


@dataclass
class Fragment:
    document_name: str
    page: int | None
    text: str
    left: str
    right: str
    score: float


@dataclass
class SourceGroup:
    n: int
    name: str
    fragments: list[Fragment] = field(default_factory=list)

    @property
    def best(self) -> Fragment:
        return self.fragments[0]

    @property
    def pages(self) -> list[int]:
        return sorted({f.page for f in self.fragments if f.page is not None})

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "name": self.name,
            "stem": stem(self.name),
            "filetype": filetype(self.name),
            "pages": self.pages,
            "page": self.best.page,
            "quote": self.best.text,
            "fragments": [
                {"page": f.page, "text": f.text, "left": f.left, "right": f.right}
                for f in self.fragments
            ],
        }


def stem(name: str) -> str:
    return re.sub(r"\.[A-Za-z0-9]{1,5}$", "", name)


def filetype(name: str) -> str:
    m = re.search(r"\.([A-Za-z0-9]{1,5})$", name)
    return m.group(1).upper() if m else ""


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = stem(text.strip().strip("\"„”'«»").strip())
    return re.sub(r"[\s_\-–—]+", " ", text).strip()


def extract_results(
    add_message_body: dict[str, Any],
) -> tuple[list[Fragment], int | None, bool]:
    """Fragments, `sse_answer.id` (for rating) and whether RAG ran at all."""
    states = add_message_body.get("last_state") or []
    state = states[0] if isinstance(states, list) and states else {}
    rag = (state or {}).get("rag_message_state") or None
    if not rag:
        return [], None, False
    response = rag.get("sse_response") or {}
    detailed = response.get("detailed_results_json") or {}
    # The backend stores a dict {index: result}; after JSON the keys are strings. We also support a list.
    items = (
        list(detailed.values())
        if isinstance(detailed, dict)
        else list(detailed or [])
    )
    fragments = []
    for item in items:
        if not isinstance(item, dict) or not item.get("document_name"):
            continue
        score = item.get("score_normalized")
        if score is None:
            score = item.get("score") or 0
        fragments.append(
            Fragment(
                document_name=str(item["document_name"]),
                page=item.get("page_number"),
                text=str(item.get("text_str") or ""),
                left=str(item.get("left_context") or ""),
                right=str(item.get("right_context") or ""),
                score=float(score or 0),
            )
        )
    answer = rag.get("sse_answer") or {}
    answer_id = answer.get("id") if isinstance(answer, dict) else None
    return fragments, answer_id, True


def _match(candidate: str, names: list[str]) -> str | None:
    c = _norm(candidate)
    if len(c) < 3:
        return None
    for name in names:
        if _norm(name) == c:
            return name
    for name in names:
        n = _norm(name)
        if len(c) >= 8 and (c in n or n in c):
            return name
    return None


def build_answer(text: str, fragments: list[Fragment]) -> dict[str, Any]:
    """Answer text + fragments → HTML with footnotes, source groups, text for the clipboard."""
    by_doc: dict[str, list[Fragment]] = {}
    for f in sorted(fragments, key=lambda x: x.score, reverse=True):
        by_doc.setdefault(f.document_name, []).append(f)
    names = list(by_doc)

    order: list[str] = []

    def number_for(name: str) -> int:
        if name not in order:
            order.append(name)
        return order.index(name) + 1

    def replace(m: re.Match[str]) -> str:
        # One bracket may contain several names separated by semicolons.
        parts = [p for p in re.split(r";|\]\s*\[", m.group(1)) if p.strip()]
        found = [_match(p, names) for p in parts]
        if not any(found):
            return m.group(0)
        nums = sorted({number_for(n) for n in found if n})
        return "".join(PLACEHOLDER.format(n) for n in nums)

    cited = CITATION_RE.sub(replace, text or "")
    # Documents not cited in the text get the next numbers in relevance order.
    for name in names:
        number_for(name)
    groups = [
        SourceGroup(n=order.index(name) + 1, name=name, fragments=by_doc[name])
        for name in order
    ]
    group_by_n = {g.n: g for g in groups}

    rendered = _md.render(cited)

    def to_button(m: re.Match[str]) -> str:
        g = group_by_n[int(m.group(1))]
        label = html.escape(
            f"{g.n}: {stem(g.name)}" + (f", s. {g.best.page}" if g.best.page else "")
        )
        return f'<button type="button" class="fn approx" data-fn="{g.n}" aria-label="Przypis {label}">{g.n}</button>'

    html_out = PLACEHOLDER_RE.sub(to_button, rendered)
    plain = PLACEHOLDER_RE.sub(lambda m: f"[{m.group(1)}]", cited).strip()
    return {
        "html": html_out,
        "plain": plain,
        "groups": [g.as_dict() for g in groups],
        "documents_used": len(groups),
        "fragments": len(fragments),
        "cited": bool(PLACEHOLDER_RE.search(cited)),
    }


def render_plain(text: str) -> str:
    """An answer without sources or a message from history: plain Markdown, no footnotes."""
    return _md.render(text or "")
