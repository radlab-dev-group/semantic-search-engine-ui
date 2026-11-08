# ADR 0003 – Answer sources in frontend memory until CR-04 and CR-05

Date: 2026-11-01 · Status: accepted

**Context.** `GET chats` returns messages without sources and without the chat's collection.

**Decision.** After each answer the frontend stores its sources, plus the conversation's base and document scope,
in process memory (`MemoryStore`), scoped to the user's session. After the session expires it shows a message
"Sources and footnotes are not available" with an "Ask again" button.

**Consequences.** One frontend process or sticky sessions; for multiple replicas – Redis behind the `SessionStore` interface.
After CR-04 and CR-05 the store becomes unnecessary.
