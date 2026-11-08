# Braki w API semantic-search-engine – czat RAG dla pracownika

1 listopada 2026 · podstawa: kod backendu z commita 58c0b8d (2026-10-30)

Frontend działa na dzisiejszym API. Poniższe braki ograniczają go albo zmuszają do obejść.
**Must have** to pozycje P0: bez nich nie spełnimy dwóch głównych wymagań – przypisu z odesłaniem
do właściwego miejsca w dokumencie i rozmowy, w której model pamięta, o czym była mowa.

Priorytety: **P0** – must have · **P1** – ważne dla MVP · **P2** – kolejna wersja.

## Lista braków

Lista endpointów i pól, których dziś nie ma, a które interfejs już przewiduje. „MVP” oznacza, że element jest w MVP
w wersji przejściowej (z widocznym ograniczeniem) albo ukryty za flagą do czasu zmiany.

| # | Czego brakuje (endpoint / pole) | Element UI, który tego potrzebuje | Do czasu zmiany | CR | Priorytet |
|---|---|---|---|---|---|
| 1 | Historia rozmowy (pytania **i odpowiedzi**) przekazywana do modelu generującego odpowiedź RAG; pole `rewritten_query` | dopytywanie („rozwiń”, „zrób tabelę”), „Pokaż inaczej” bez nowego wyszukiwania | model widzi tylko 4 poprzednie pytania doklejone do wyszukiwania | CR-14 | **P0** |
| 2 | Numerowane fragmenty w prompcie i pole `citations[]` (`n`, `text_id`, `document_name`, `page_number`, `char_start`, `char_end`) w `add_user_message` | przypisy [n] przy zdaniach | przypis przybliżony: dokument pewny, strona dobrana | CR-01 | **P0** |
| 3 | `text_id`, `document_id`, `char_start`, `char_end` w `detailed_results_json`; `document_content?text_id=` | podświetlenie cytatu w podglądzie dokumentu | szukanie tekstu cytatu w treści strony po stronie frontendu | CR-02 | **P0** |
| 4 | `answer_source: "rag" \| "llm_fallback"` w `add_user_message`; opcja `rag_only` | ostrzeżenie „Nie znalazłem tego w dokumentach” | wnioskowanie z pustych `detailed_results_json` | CR-03 | P1 |
| 5 | `GET chats?with_sources=true` – stan wiadomości (źródła, `sse_answer.id`) | źródła, przypisy i ocena przy starszych odpowiedziach | komunikat „źródła niedostępne” + „Zapytaj ponownie” | CR-04 | P1 |
| 6 | W `GET chats`: `title`, **`collection_name`**, `created_at`, `updated_at`, `messages_count`, paginacja (`limit`, `offset`) | historia: tytuł, data, baza rozmowy, szybkie ładowanie | tytuł = pierwsze pytanie; baza wznowionej rozmowy znana tylko w bieżącej sesji frontendu | CR-05 | P1 |
| 7 | `POST rename_chat`, `POST delete_chat` | menu ⋯ przy rozmowie: Zmień nazwę, Usuń | ukryte (flaga `features.chat_sections`) | CR-05 | P1 |
| 8 | `GET/POST chat_groups`, `rename_chat_group`, `delete_chat_group`, `POST move_chat`, `POST pin_chat`, `group_id` w `new_chat`, `group_id` i `pinned` w `chats` | sekcje w historii, przypinanie, „+” nowy czat w sekcji | ukryte (flaga `features.chat_sections`) | CR-16 | P1 |
| 9 | Zakres dokumentów zapisany przy czacie; `documents` w `GET chats` | panel „Dokumenty” po wznowieniu rozmowy | po wznowieniu zakres wraca do „wszystkie” z komunikatem | CR-18 | P1 |
| 10 | `POST cancel_generation` (`chat_id`) | przycisk „Przerwij” | przerywa tylko czekanie w UI; odpowiedź może pojawić się w historii | CR-06 | P2 |
| 11 | Zdarzenia postępu / streaming (SSE) z `add_user_message` | etapy „szukam / znalazłem / piszę”, tekst na żywo | licznik sekund | CR-06 | P2 |
| 12 | W `GET documents`: `document_date`, `uploaded_at`, `file_type`, `total_pages` | panel „Dokumenty”: data, liczba stron | sama nazwa i typ z rozszerzenia | CR-07 | P2 |
| 13 | `system_prompt` z żądania łączony z promptem szablonu pytań zamiast nadpisywany | format odpowiedzi (Zwięźle / W punktach / Szczegółowo / Tabela), polecenie cytowania | w kolekcjach z szablonami format i przypisy mogą nie działać | CR-19 | P1 |

Poza MVP (roadmapa): pobranie oryginału pliku (CR-07), udostępnianie w organizacji (CR-08), agenty (CR-09…12),
dopracowanie pytania (CR-15), notatki (CR-17), PPTX/XLSX/CSV (CR-13).

Pełny opis każdego zgłoszenia (problem, propozycja, kryteria akceptacji) jest w pliku
`frontend/docs/zgloszenia-do-radlab.md`.
