"""
Markdown rendering for the answers produced by the engine.

The generative models answer with Markdown, so the text is rendered instead of
being printed as-is. `markdown-it-py` is used with `html=False`, which escapes
any raw HTML coming from a model response, and with its link validator, which
drops dangerous schemes such as `javascript:` or `data:`.

On top of the library defaults:

* heading levels are shifted down (an answer lives inside a card that already
  owns the `<h2>` of the page),
* links open in a new tab with `rel="noopener noreferrer nofollow"`,
* table column alignment is expressed with CSS classes instead of the inline
  `style="text-align: ..."` emitted by the parser.
"""

import re

from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

__all__ = ["render_markdown"]

_ALIGNMENT_CLASSES = {
    "left": "cell-left",
    "center": "cell-center",
    "right": "cell-right",
}
_HEADING_SHIFT = 2
_INLINE_ALIGNMENT_RE = re.compile(r"^\s*text-align:\s*(left|center|right);?\s*$")


def _parser() -> MarkdownIt:
    parser = MarkdownIt(
        "commonmark",
        {
            "html": False,  # never interpret HTML coming from the model
            "linkify": True,
            "breaks": True,
            "langPrefix": "lang-",
            "typographer": False,
        },
    )
    parser.enable(["table", "strikethrough"])
    parser.use(tasklists_plugin)
    return parser


_PARSER = _parser()


def render_markdown(text) -> str:
    """Convert a Markdown answer into an HTML fragment (safe by escaping)."""
    if text is None:
        return ""
    source = str(text)
    if not source.strip():
        return ""

    tokens = _PARSER.parse(source, {})
    for token in _walk(tokens):
        if token.type in ("heading_open", "heading_close"):
            level = min(int(token.tag[1:]) + _HEADING_SHIFT, 6)
            token.tag = f"h{level}"
        elif token.type == "link_open":
            token.attrSet("rel", "noopener noreferrer nofollow")
            token.attrSet("target", "_blank")
        elif token.type in ("th_open", "td_open"):
            _replace_alignment_with_class(token)

    return _PARSER.renderer.render(tokens, _PARSER.options, {})


def _walk(tokens):
    """Inline tokens (and with them the links) live in `children`, not at the
    top level of the parsed stream."""
    for token in tokens:
        yield token
        if token.children:
            yield from _walk(token.children)


def _replace_alignment_with_class(token) -> None:
    style = token.attrGet("style")
    if not style:
        return
    match = _INLINE_ALIGNMENT_RE.match(style)
    if not match:
        return
    token.attrSet("class", _ALIGNMENT_CLASSES[match.group(1)])
    token.attrs.pop("style", None)
