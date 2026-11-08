"""Turns the `add_user_message` response into a display answer.

Approximate footnotes: the model receives an instruction to put the document name in
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

from core.markdown import render_markdown
from markdown_it import MarkdownIt

_md = MarkdownIt(
    "commonmark", {"html": False, "linkify": False, "typographer": False}
).enable("table")

CITATION_RE = re.compile(r"\s?\[([^\[\]\n]{1,240})\]")
PLACEHOLDER = "⁣FN{}⁣"
PLACEHOLDER_RE = re.compile(r"⁣FN(\d+)(?::(\d+))?⁣")


@dataclass
class Fragment:
    document_name: str
    page: int | None
    text: str
    left: str
    right: str
    score: float
    citation_number: int | None = None
    chunk: int | None = None
    result_id: int | None = None


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
            "fragments_count": len(self.fragments),
            "fragments": [
                {
                    "index": idx,
                    "page": f.page,
                    "chunk": f.chunk,
                    "result_id": f.result_id,
                    "text": f.text,
                    "left": f.left,
                    "right": f.right,
                    "score": f.score,
                    "citation_number": f.citation_number,
                }
                for idx, f in enumerate(self.fragments)
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


def extract_state_results(state: Any) -> tuple[list[Fragment], int | None, bool]:
    """Extract fragments, `sse_answer.id` (for rating), and whether RAG ran from a `MessageState` dict."""
    if isinstance(state, list):
        state = state[0] if state else {}
    if not isinstance(state, dict):
        return [], None, False
    rag = state.get("rag_message_state") or None
    if not isinstance(rag, dict) or not rag:
        return [], None, False
    response = rag.get("sse_response") or {}
    detailed = (
        response.get("detailed_results_json")
        or response.get("detailed_results")
        or {}
    )
    # The backend stores a dict {index: result}; after JSON the keys are strings. We also support a list.
    items = (
        list(detailed.values())
        if isinstance(detailed, dict)
        else list(detailed or [])
    )
    citations = (
        rag.get("citations") if isinstance(rag.get("citations"), list) else []
    )
    citation_by_text: dict[tuple[str, str], int] = {}
    for c in citations:
        if (
            isinstance(c, dict)
            and c.get("document_name")
            and isinstance(c.get("n"), int)
        ):
            citation_by_text[
                (str(c["document_name"]), str(c.get("text_str") or ""))
            ] = c["n"]
    if not items and citations:
        items = list(citations)
    fragments = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not item.get("document_name"):
            continue
        doc_name = str(item["document_name"])
        text_val = str(item.get("text_str") or item.get("text") or "")
        score = item.get("score_normalized")
        if score is None:
            score = item.get("score") or 0
        cit_n = (
            item.get("n")
            if isinstance(item.get("n"), int)
            else citation_by_text.get((doc_name, text_val), idx)
        )
        raw_chunk = (
            item.get("text_number")
            if item.get("text_number") is not None
            else item.get("chunk_number")
        )
        try:
            chunk_num = int(raw_chunk) if raw_chunk is not None else None
        except (TypeError, ValueError):
            chunk_num = None
        raw_rid = item.get("result_id")
        try:
            rid = int(raw_rid) if raw_rid is not None else None
        except (TypeError, ValueError):
            rid = None
        fragments.append(
            Fragment(
                document_name=doc_name,
                page=item.get("page_number") or item.get("page"),
                text=text_val,
                left=str(item.get("left_context") or ""),
                right=str(item.get("right_context") or ""),
                score=float(score or 0),
                citation_number=cit_n,
                chunk=chunk_num,
                result_id=rid,
            )
        )
    answer = rag.get("sse_answer") or {}
    answer_id = answer.get("id") if isinstance(answer, dict) else None
    return fragments, answer_id, True


def extract_results(
    add_message_body: dict[str, Any],
) -> tuple[list[Fragment], int | None, bool]:
    """Fragments, `sse_answer.id` (for rating) and whether RAG ran at all."""
    states = (
        add_message_body.get("last_state")
        if isinstance(add_message_body, dict)
        else None
    )
    return extract_state_results(states)


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
    """Answer text + fragments -> HTML with footnotes, source groups, text for the clipboard."""
    by_doc: dict[str, list[Fragment]] = {}
    for f in sorted(fragments, key=lambda x: x.score, reverse=True):
        by_doc.setdefault(f.document_name, []).append(f)
    names = list(by_doc)

    order: list[str] = []

    def number_for(name: str) -> int:
        if name not in order:
            order.append(name)
        return order.index(name) + 1

    def resolve_part(part: str) -> tuple[str, int | None] | None:
        matched = _match(part, names)
        if matched:
            return matched, None
        stripped = part.strip()
        if stripped.isdigit():
            num = int(stripped)
            for f in fragments:
                if f.citation_number == num and f.document_name in by_doc:
                    doc_frags = by_doc[f.document_name]
                    frag_idx = doc_frags.index(f) if f in doc_frags else 0
                    return f.document_name, frag_idx
            idx = num - 1
            if 0 <= idx < len(names):
                return names[idx], None
        return None

    def replace(m: re.Match[str]) -> str:
        parts = [p for p in re.split(r";|\]\s*\[", m.group(1)) if p.strip()]
        found = [resolve_part(p) for p in parts]
        valid = [r for r in found if r is not None]
        if not valid:
            return m.group(0)
        seen: dict[int, int | None] = {}
        for doc_name, frag_idx in valid:
            n = number_for(doc_name)
            if n not in seen or (seen[n] is None and frag_idx is not None):
                seen[n] = frag_idx
        tokens = []
        for n in sorted(seen):
            f_idx = seen[n]
            tokens.append(
                f"⁣FN{n}:{f_idx}⁣" if f_idx is not None else PLACEHOLDER.format(n)
            )
        return "".join(tokens)

    cited = CITATION_RE.sub(replace, text or "")
    for name in names:
        number_for(name)
    groups = [
        SourceGroup(n=order.index(name) + 1, name=name, fragments=by_doc[name])
        for name in order
    ]
    group_by_n = {g.n: g for g in groups}

    rendered = render_markdown(cited)

    def to_button(m: re.Match[str]) -> str:
        n = int(m.group(1))
        frag_str = m.group(2)
        frag_idx = int(frag_str) if frag_str is not None else None
        g = group_by_n.get(n)
        if g:
            frag = (
                g.fragments[frag_idx]
                if (frag_idx is not None and 0 <= frag_idx < len(g.fragments))
                else g.best
            )
            page_info = f", s. {frag.page}" if frag.page else ""
            chunk_info = (
                f" (fragment {frag_idx + 1}/{len(g.fragments)})"
                if (len(g.fragments) > 1 and frag_idx is not None)
                else (
                    f" ({len(g.fragments)} fragm.)" if len(g.fragments) > 1 else ""
                )
            )
            label = html.escape(f"{g.n}: {stem(g.name)}{page_info}{chunk_info}")
        else:
            label = str(n)
        frag_attr = f' data-fn-frag="{frag_idx}"' if frag_idx is not None else ""
        return f'<button type="button" class="fn-badge" data-fn="{n}"{frag_attr} aria-label="Przypis {label}" title="{label}">{n}</button>'

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
    return render_markdown(text or "")
