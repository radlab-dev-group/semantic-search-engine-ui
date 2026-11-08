"""Proxy layer for the browser interface (`/ui-api/*`).

Each route calls one or two RadLab backend endpoints with the session token.
The route → endpoint map is in the README (the "Endpoint map" section).
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.answers import (
    build_answer,
    extract_results,
    filetype,
    render_plain,
    stem,
)
from app.core.api_client import ApiError
from app.routes.common import lang_of

router = APIRouter(prefix="/ui-api")

STATUS = {
    "auth": 401,
    "forbidden": 403,
    "not_found": 404,
    "timeout": 504,
    "unavailable": 503,
    "backend": 502,
}


def _error(exc: ApiError) -> JSONResponse:
    return JSONResponse(
        {"error": exc.kind, "code": exc.code, "message": exc.message},
        status_code=STATUS.get(exc.kind, 502),
    )


async def backend(
    request: Request, method: str, endpoint: str, **kwargs: Any
) -> Any:
    """Call with the session token; in SSO mode one token-refresh attempt after a 401."""
    token = request.session.get("token")
    if not token:
        raise ApiError("auth", 401)
    api = request.app.state.api
    lang = lang_of(request)
    try:
        return await api.call(method, endpoint, token=token, lang=lang, **kwargs)
    except ApiError as exc:
        refresh = request.session.get("refresh_token")
        if exc.kind != "auth" or not refresh:
            raise
        try:
            body = await api.call(
                "POST", "refresh_token", lang=lang, json={"refresh_token": refresh}
            )
        except ApiError:
            request.session.pop("token", None)
            raise exc from None
        request.session["token"] = body["token"]
        if body.get("refresh_token"):
            request.session["refresh_token"] = body["refresh_token"]
        return await api.call(
            method, endpoint, token=body["token"], lang=lang, **kwargs
        )


def _sid(request: Request) -> str:
    return request.session.get("sid") or ""


# ---------- Knowledge bases and documents ----------


@router.get("/collections")
async def collections(request: Request):
    """GET collections → knowledge base cards (call name, display name, description, document count)."""
    try:
        body = await backend(request, "GET", "collections")
    except ApiError as exc:
        return _error(exc)
    items = (
        (body or {}).get("collections", []) if isinstance(body, dict) else body or []
    )
    return {
        "collections": [
            {
                "name": c["name"],
                "display_name": c.get("display_name") or c["name"],
                "description": c.get("description") or "",
                "document_count": c.get("document_count"),
                "active_document_count": c.get(
                    "active_document_count", c.get("document_count")
                ),
            }
            for c in items
            if isinstance(c, dict) and c.get("name")
        ]
    }


@router.get("/documents")
async def documents(request: Request, collection: str):
    """GET documents?collection_name → documents enabled for search (the Documents panel)."""
    try:
        body = await backend(
            request, "GET", "documents", params={"collection_name": collection}
        )
    except ApiError as exc:
        return _error(exc)
    raw_docs = [
        d
        for d in (body or {}).get("documents", [])
        if isinstance(d, dict) and d.get("name")
    ]
    raw_docs.sort(
        key=lambda d: (
            str(d["name"]).lower(),
            str(d.get("relative_path") or "").lower(),
            str(d.get("category") or "").lower(),
            d.get("id") or 0,
        )
    )
    items: list[dict[str, Any]] = []
    for d in raw_docs:
        n = str(d["name"])
        item: dict[str, Any] = {
            "name": n,
            "stem": stem(n),
            "filetype": filetype(n),
        }
        if d.get("id") is not None:
            item["id"] = d["id"]
        rel_path = str(d.get("relative_path") or "").strip()
        if rel_path and rel_path != "/" and rel_path != n and rel_path != f"/{n}":
            item["relative_path"] = rel_path
        cat = str(d.get("category") or "").strip()
        if cat:
            item["category"] = cat
        items.append(item)
    return {"documents": items}


@router.get("/document")
async def document(
    request: Request,
    collection: str,
    name: str,
    from_page: int = 1,
    document_id: int | None = None,
):
    """GET document_content → document text pages starting from the given page."""
    s = request.app.state.settings
    params: dict[str, Any] = {
        "collection_name": collection,
        "document_name": name,
        "from_page": max(1, from_page),
        "max_pages": s.preview_pages,
    }
    if document_id is not None:
        params["document_id"] = document_id
    try:
        body = await backend(
            request,
            "GET",
            "document_content",
            params=params,
        )
    except ApiError as exc:
        return _error(exc)
    body = body or {}
    return {
        "name": body.get("document_name", name),
        "pages": [
            {"page": p.get("page"), "content": p.get("content") or ""}
            for p in body.get("pages", [])
        ],
        "total_pages": body.get("total_pages"),
        "next_page": body.get("next_page"),
        "truncated": bool(body.get("truncated")),
    }


# ---------- Chat ----------


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    collection: str | None = (
        None  # None: resumed chat with an unknown base – the backend uses the chat's collection
    )
    chat_id: int | None = None
    documents: list[str] | None = None
    format: str | None = None


async def _generative_model(request: Request) -> str:
    s = request.app.state.settings
    if s.options.get("generative_model"):
        return s.options["generative_model"]
    cache = request.app.state.model_cache
    if "model" not in cache:
        body = await backend(request, "GET", "generative_models")
        names = list(body.keys()) if isinstance(body, dict) else list(body or [])
        if not names:
            raise ApiError(
                "backend", 0, "NO_MODELS", "The backend returned no generative model"
            )
        cache["model"] = names[0]
    return cache["model"]


def _search_options(request: Request, docs: list[str] | None) -> dict[str, Any]:
    opts = dict(request.app.state.settings.search_options)
    if docs is not None:
        opts["documents"] = docs
    return opts


@router.post("/ask")
async def ask(request: Request, data: AskIn):
    """A question or follow-up: POST new_chat (first question) → POST add_user_message."""
    s = request.app.state.settings
    store = request.app.state.store
    fmt = s.format(data.format)
    if data.documents is not None and not data.documents:
        return JSONResponse({"error": "no_documents"}, status_code=400)
    try:
        options = {
            **s.options,
            "generative_model": await _generative_model(request),
            "max_new_tokens": fmt.get("max_new_tokens"),
        }
        options = {k: v for k, v in options.items() if v is not None}
        chat_id = data.chat_id
        if chat_id is None and not data.collection:
            return JSONResponse(
                {"error": "backend", "message": "No knowledge base"}, status_code=400
            )
        if chat_id is None:
            body = await backend(
                request,
                "POST",
                "new_chat",
                json={
                    "collection_name": data.collection,
                    "options": options,
                    "search_options": _search_options(request, data.documents),
                },
            )
            chat_id = int(body["chat"]["id"])
        system_prompt = "\n\n".join(
            p for p in (fmt.get("system_prompt"), s.citation_instruction) if p
        )
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "user_message": data.question.strip(),
            "options": options,
            "search_options": _search_options(request, data.documents),
            "system_prompt": system_prompt,
        }
        if data.collection:
            payload["collection_name"] = data.collection
        body = await backend(
            request,
            "POST",
            "add_user_message",
            json=payload,
            timeout=s.timeout_answer,
        )
    except ApiError as exc:
        return _error(exc)

    body = body or {}
    text = body.get("generated_assistant_message") or ""
    fragments, answer_id, rag_ran = extract_results(body)
    if fragments:
        answer = build_answer(text, fragments)
        answer["no_sources"] = False
    else:
        answer = {
            "html": render_plain(text),
            "plain": text,
            "groups": [],
            "documents_used": 0,
            "fragments": 0,
            "no_sources": True,
        }
    history = body.get("history") or []
    message_id = next(
        (m.get("id") for m in reversed(history) if m.get("role") == "assistant"),
        None,
    )
    answer.update(
        {
            "answer_id": answer_id,
            "message_id": message_id,
            "generation_time": body.get("generation_time"),
            "format": fmt["id"],
            "question": data.question.strip(),
            "scope_count": (
                len(data.documents) if data.documents is not None else None
            ),
        }
    )
    sid = _sid(request)
    if message_id is not None:
        store.put(sid, f"answer:{message_id}", answer)
    if data.collection:
        store.put(
            sid,
            f"chat:{chat_id}",
            {"collection": data.collection, "documents": data.documents},
        )
    return {"chat_id": chat_id, "answer": answer}


@router.get("/chats")
async def chats(request: Request):
    """GET chats → list for the history (title = first question, date = last message)."""
    s = request.app.state.settings
    try:
        body = await backend(request, "GET", "chats")
    except ApiError as exc:
        return _error(exc)
    store, sid = request.app.state.store, _sid(request)
    out = []
    for entry in (body or {}).get("history", []):
        messages = sorted(
            entry.get("chat_history") or [], key=lambda m: m.get("number") or 0
        )
        first = next((m for m in messages if m.get("role") == "user"), None)
        if not first:
            continue
        meta = store.get(sid, f"chat:{entry.get('chat_id')}") or {}
        out.append(
            {
                "chat_id": entry.get("chat_id"),
                "title": _title(first.get("text") or ""),
                "updated": (messages[-1].get("date_time") if messages else None),
                "collection": meta.get("collection"),
            }
        )
    out.sort(key=lambda c: c["updated"] or "", reverse=True)
    return {"chats": out[: s.history_limit * 4]}


@router.get("/chats/{chat_id}")
async def chat_detail(request: Request, chat_id: int):
    """Conversation messages from GET chats; sources only from the current session (until CR-04)."""
    try:
        body = await backend(request, "GET", "chats")
    except ApiError as exc:
        return _error(exc)
    entry = next(
        (e for e in (body or {}).get("history", []) if e.get("chat_id") == chat_id),
        None,
    )
    if entry is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    store, sid = request.app.state.store, _sid(request)
    messages = []
    last_question = ""
    last_user_state = None
    for m in sorted(
        entry.get("chat_history") or [], key=lambda x: x.get("number") or 0
    ):
        if m.get("role") == "user":
            last_question = m.get("text") or ""
            last_user_state = m.get("state")
            messages.append({"role": "user", "text": last_question})
        elif m.get("role") == "assistant":
            stored = store.get(sid, f"answer:{m.get('id')}")
            if stored:
                messages.append({"role": "assistant", "answer": stored})
                last_user_state = None
            else:
                text = m.get("text") or ""
                state = m.get("state") or last_user_state
                last_user_state = None
                fragments, answer_id, _rag_ran = extract_results(
                    {"last_state": [state]} if state else {}
                )
                if fragments:
                    ans = build_answer(text, fragments)
                    ans["no_sources"] = False
                    ans["answer_id"] = answer_id
                    ans["message_id"] = m.get("id")
                    ans["question"] = last_question
                    messages.append({"role": "assistant", "answer": ans})
                else:
                    messages.append(
                        {
                            "role": "assistant",
                            "legacy": True,
                            "html": render_plain(text),
                            "plain": text,
                            "question": last_question,
                        }
                    )
    meta = store.get(sid, f"chat:{chat_id}") or {}
    return {
        "chat_id": chat_id,
        "collection": meta.get("collection") or entry.get("collection_name"),
        "documents": meta.get("documents"),
        "messages": messages,
        "read_only": bool(entry.get("is_read_only")),
    }


class RateIn(BaseModel):
    answer_id: int
    value: int = Field(ge=0, le=1)
    comment: str | None = Field(default=None, max_length=2000)


@router.post("/rate")
async def rate(request: Request, data: RateIn):
    """POST rate_generative_answer (👍 = 1, 👎 = 0, scale 0–1)."""
    payload: dict[str, Any] = {
        "answer_response_id": data.answer_id,
        "rate_value": data.value,
        "rate_value_max": 1,
    }
    if data.comment and data.comment.strip():
        payload["rate_comment"] = data.comment.strip()
    try:
        await backend(request, "POST", "rate_generative_answer", json=payload)
    except ApiError as exc:
        return _error(exc)
    return {"ok": True}


@router.get("/health")
async def health(request: Request):
    """Backend GET healthz – the "service unavailable" banner."""
    try:
        body = await request.app.state.api.call(
            "GET", "healthz", lang=lang_of(request), timeout=5
        )
    except ApiError as exc:
        return JSONResponse({"ok": False, "error": exc.kind}, status_code=503)
    healthy = body.get("healthy", True) if isinstance(body, dict) else True
    return {"ok": bool(healthy)}


def _title(text: str, limit: int = 90) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
