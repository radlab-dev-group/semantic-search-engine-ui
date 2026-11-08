# ADR 0001 – Serwer frontendu pośredniczy we wszystkich wywołaniach backendu

Data: 2026-11-01 · Status: przyjęta

**Kontekst.** Backend `semantic-search-engine` nie ma CORS, a token użytkownika nie powinien trafiać do kodu JavaScript.
Obecny UI RadLab jest w FastAPI + Jinja2.

**Decyzja.** FastAPI + Jinja2 renderuje strony, a interfejs w przeglądarce woła tylko trasy `/ui-api/*` serwera frontendu.
Serwer dokłada token z podpisanego ciasteczka `HttpOnly` i woła backend. Interfejs to jeden plik JS bez frameworka i bez kroku budowania.

**Konsekwencje.** Brak wymagań wobec CORS w backendzie; prosta obsługa przez RadLab (Python, bez Node.js).
Długie odpowiedzi (do 150 s) przechodzą przez dwa połączenia – proxy musi mieć odpowiedni timeout.
