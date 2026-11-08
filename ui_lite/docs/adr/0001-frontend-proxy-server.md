# ADR 0001 – The frontend server proxies all backend calls

Date: 2026-11-01 · Status: accepted

**Context.** The `semantic-search-engine` backend has no CORS, and the user's token should not reach the JavaScript code.
The current RadLab UI is built with FastAPI + Jinja2.

**Decision.** FastAPI + Jinja2 renders the pages, and the browser interface only calls the frontend server's `/ui-api/*` routes.
The server adds the token from the signed `HttpOnly` cookie and calls the backend. The interface is a single JS file with no framework and no build step.

**Consequences.** No CORS requirements on the backend; easy operation for RadLab (Python, no Node.js).
Long answers (up to 150 s) travel over two connections – the proxy needs an appropriate timeout.
