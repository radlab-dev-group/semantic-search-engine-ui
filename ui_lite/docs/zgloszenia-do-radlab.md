# 03 – Zgłoszenia zmian do backendu RadLab (change requests)

Wersja 0.4 · 2026-11-01 (lista braków w API, CR-19, uzupełnienie CR-05) · adresat: zespół `semantic-search-engine` (RadLab)
Podstawa: analiza kodu backendu (commit 58c0b8d, 2026-10-30), ścieżka użytkownika `04-sciezka-uzytkownika.html`
i benchmark `benchmark/2026-11-01-insp-board.html`.

## Braki w API, których potrzebuje interfejs

Lista endpointów i pól, których dziś nie ma, a które interfejs już przewiduje. „MVP” oznacza, że element jest w MVP
w wersji przejściowej (z widocznym ograniczeniem) albo ukryty za flagą do czasu zmiany.

| # | Czego brakuje (endpoint / pole) | Element UI, który tego potrzebuje | Do czasu zmiany | CR |
|---|---|---|---|---|
| 1 | Historia rozmowy (pytania **i odpowiedzi**) przekazywana do modelu generującego odpowiedź RAG; pole `rewritten_query` | dopytywanie („rozwiń”, „zrób tabelę”), „Pokaż inaczej” bez nowego wyszukiwania | model widzi tylko 4 poprzednie pytania doklejone do wyszukiwania | CR-14 |
| 2 | Numerowane fragmenty w prompcie i pole `citations[]` (`n`, `text_id`, `document_name`, `page_number`, `char_start`, `char_end`) w `add_user_message` | przypisy [n] przy zdaniach | przypis przybliżony: dokument pewny, strona dobrana | CR-01 |
| 3 | `text_id`, `document_id`, `char_start`, `char_end` w `detailed_results_json`; `document_content?text_id=` | podświetlenie cytatu w podglądzie dokumentu | szukanie tekstu cytatu w treści strony po stronie frontendu | CR-02 |
| 4 | `answer_source: "rag" \| "llm_fallback"` w `add_user_message`; opcja `rag_only` | ostrzeżenie „Nie znalazłem tego w dokumentach” | wnioskowanie z pustych `detailed_results_json` | CR-03 |
| 5 | `GET chats?with_sources=true` – stan wiadomości (źródła, `sse_answer.id`) | źródła, przypisy i ocena przy starszych odpowiedziach | komunikat „źródła niedostępne” + „Zapytaj ponownie” | CR-04 |
| 6 | W `GET chats`: `title`, **`collection_name`**, `created_at`, `updated_at`, `messages_count`, paginacja (`limit`, `offset`) | historia: tytuł, data, baza rozmowy, szybkie ładowanie | tytuł = pierwsze pytanie; baza wznowionej rozmowy znana tylko w bieżącej sesji frontendu | CR-05 |
| 7 | `POST rename_chat`, `POST delete_chat` | menu ⋯ przy rozmowie: Zmień nazwę, Usuń | ukryte (flaga `features.chat_sections`) | CR-05 |
| 8 | `GET/POST chat_groups`, `rename_chat_group`, `delete_chat_group`, `POST move_chat`, `POST pin_chat`, `group_id` w `new_chat`, `group_id` i `pinned` w `chats` | sekcje w historii, przypinanie, „+” nowy czat w sekcji | ukryte (flaga `features.chat_sections`) | CR-16 |
| 9 | Zakres dokumentów zapisany przy czacie; `documents` w `GET chats` | panel „Dokumenty” po wznowieniu rozmowy | po wznowieniu zakres wraca do „wszystkie” z komunikatem | CR-18 |
| 10 | `POST cancel_generation` (`chat_id`) | przycisk „Przerwij” | przerywa tylko czekanie w UI; odpowiedź może pojawić się w historii | CR-06 |
| 11 | Zdarzenia postępu / streaming (SSE) z `add_user_message` | etapy „szukam / znalazłem / piszę”, tekst na żywo | licznik sekund | CR-06 |
| 12 | W `GET documents`: `document_date`, `uploaded_at`, `file_type`, `total_pages` | panel „Dokumenty”: data, liczba stron | sama nazwa i typ z rozszerzenia | CR-07 |
| 13 | `system_prompt` z żądania łączony z promptem szablonu pytań zamiast nadpisywany | format odpowiedzi (Zwięźle / W punktach / Szczegółowo / Tabela), polecenie cytowania | w kolekcjach z szablonami format i przypisy mogą nie działać | CR-19 |

Poza MVP (roadmapa): pobranie oryginału pliku (CR-07), udostępnianie w organizacji (CR-08), agenty (CR-09…12),
dopracowanie pytania (CR-15), notatki (CR-17), PPTX/XLSX/CSV (CR-13).

## Priorytety
- **P0 – blokujące.** Wymaganie must have; bez zmiany frontend działa tylko w trybie przejściowym.
- **P1 – ważne dla MVP.** Frontend ma obejście, ale z widocznym ograniczeniem dla pracownika.
- **P2 – kolejna wersja.**
- **R – roadmapa agentów.** Fundament pod agenty, które wielokrotnie odpytują bazę, żeby przygotować materiał.

## Podsumowanie

| ID | Priorytet | Temat | Blokuje |
|---|---|---|---|
| CR-14 | **P0** | Pamięć rozmowy: model zna wcześniejsze pytania, odpowiedzi i źródła | dopytywanie w czacie |
| CR-01 | **P0** | Przypisy: zdanie → fragment → strona | przypisy must have |
| CR-02 | **P0** | Identyfikatory i położenie fragmentów w wynikach | CR-01, podświetlenie w podglądzie, agenty |
| CR-03 | P1 | Jawne oznaczenie odpowiedzi bez dokumentów i możliwość wyłączenia fallbacku | zaufanie |
| CR-04 | P1 | Źródła i przypisy zapisane przy wiadomościach czatu (widok dla pracownika; uzupełnia CR-14) | historia ze źródłami |
| CR-05 | P1 | Zarządzanie czatami: tytuł, usuwanie, paginacja | historia |
| CR-06 | P2 | Postęp, streaming i zatrzymanie generowania | długie czekanie, przycisk „Przerwij” |
| CR-07 | P2 | Metadane dokumentu: data, wersja, typ, liczba stron; pobranie oryginału | aktualność, weryfikacja, podgląd bazy |
| CR-08 | P2 | Udostępnianie czatu w obrębie organizacji | udostępnianie |
| CR-09 | R | API zadań asynchronicznych dla agentów | agenty |
| CR-10 | R | Wyszukiwanie wsadowe i deduplikacja fragmentów | agenty |
| CR-11 | R | Ślad pracy agenta (trace) i cytowania w długich materiałach | agenty |
| CR-12 | R | Kroki planu i pytania doprecyzowujące | agenty |
| CR-18 | P1 | Wybór dokumentów zapamiętany przy czacie | wznowienie rozmowy z tym samym zakresem |
| CR-19 | P1 | `system_prompt` z żądania nie jest nadpisywany przez szablony pytań | format odpowiedzi, przypisy |
| CR-15 | P2 | Dopracowanie pytania przed wysłaniem | złe i zbyt lakoniczne pytania |
| CR-16 | **P1** | Sekcje w historii i przypinanie rozmów (UI gotowe w MVP za flagą) | porządek w historii |
| CR-17 | R | Notatki z odpowiedzi do ponownego użycia | praca na zebranym materiale, agenty |
| CR-13 | później | Obsługa PPTX, XLSX, CSV | dane tabelaryczne |

---

## CR-14 · P0 · Pamięć rozmowy jako kontekst (decyzja 2026-11-01)

> Dodatkowy powód: przycisk „Pokaż inaczej” (zmiana formatu odpowiedzi) dziś ponawia całe wyszukiwanie.
> Z pamięcią rozmowy backend przeformatuje poprzednią odpowiedź bez szukania, w kilka sekund.

**Wymaganie.** Backend pamięta całą rozmowę i używa jej jako kontekstu przy każdej kolejnej odpowiedzi.
Pracownik dopytuje tak jak w rozmowie z człowiekiem („a które z nich dotyczą małych firm?”, „rozwiń punkt 2”,
„zrób z tego tabelę”), a odpowiedź uwzględnia wcześniejsze pytania, odpowiedzi i źródła.

**Stan dziś (kod, commit 58c0b8d).**
- Rozmowa jest zapisana w bazie: każda wiadomość to `Message` z numerem, poprzednią i następną wiadomością.
  Zapis działa, problemem jest to, co trafia do modelu.
- **Model, który pisze odpowiedź RAG, nie dostaje historii.** `_prepare_rag_supervisor_state`
  (`chat/controllers/message.py`, ok. l. 160–230) woła `generative_answer_for_response`
  (`engine/controllers/models_logic/generative.py:516`) tylko z wynikami wyszukiwania i zapytaniem.
  Historia z odpowiedziami asystenta (`_convert_to_history_turns`) idzie do modelu wyłącznie w ścieżce
  bez dokumentów (fallback, ok. l. 89–107).
- **Kontekst to sklejone pytania.** `_prepare_sse_question_based_on_history` dokleja do 4 poprzednich pytań
  użytkownika (`LAST_QUESTIONS_TO_QUERY = 4`, `chat/api.py:128`) w tekst „Użytkownik wcześniej pytał o: … Odpowiedz teraz
  na pytanie: …”. Ten tekst idzie do wyszukiwarki jako jedno zapytanie.
- Jest ukryta opcja `use_intelligent_query_rewrite` (`message.py`, ok. l. 270). LLM przepisuje ostatnie pytanie
  na samodzielne na podstawie 5 ostatnich wiadomości. Model jest wpisany na sztywno (`google/gemini-2.5-flash-lite`),
  opcja nie jest opisana w API i nie zmienia tego, że model generujący odpowiedź nie widzi historii.

**Skutki dla pracownika.**
1. „Rozwiń punkt 2”, „skróć”, „zrób tabelę”, „przetłumacz” nie działają: model nie zna swojej poprzedniej odpowiedzi.
2. Sklejone pytania rozmywają wyszukiwanie. Po zmianie tematu w rozmowie wracają fragmenty dotyczące starych pytań.
3. Pytanie z zaimkiem („a ile to kosztuje?”) zależy od szczęścia przy sklejaniu.
4. Treść sklejki jest na sztywno po polsku, niezależnie od `lang`.

**Propozycja.**
1. Przekazywać do modelu generującego odpowiedź RAG historię rozmowy: pytania i odpowiedzi z ostatnich N tur
   albo w limicie tokenów. Starsze tury streszczać. Nowe fragmenty z wyszukiwania dochodzą obok historii.
2. Zapytanie do wyszukiwarki budować przez przepisanie pytania na samodzielne (query rewrite), a nie przez sklejanie.
   Model przepisujący brać z konfiguracji, nie z kodu. Zwracać przepisane zapytanie w odpowiedzi
   (`rewritten_query`), żeby UI mogło pokazać „Szukałem: …”.
3. Pamiętać źródła rozmowy. Przy dopytaniu model może cytować fragmenty z poprzednich odpowiedzi.
   Numeracja przypisów jest wspólna w obrębie czatu (z CR-01 i CR-02).
4. Rozpoznawać polecenia, które nie wymagają nowego wyszukiwania („skróć”, „zrób tabelę”, „przetłumacz”).
   Odpowiadać na podstawie historii i jej źródeł, z `answer_source: "history"` (rozszerzenie CR-03).
5. Kontekst działa także po wznowieniu czatu z historii, po ponownym zalogowaniu i na innym urządzeniu.
   Stan jest w bazie backendu, nie w sesji frontendu.

**Kryteria akceptacji.**
- Scenariusz testowy z 3 tur: „Jakie obowiązki nakłada AI Act na dostawców?” → „A które z nich dotyczą małych firm?”
  → „Zrób z tego tabelę”. Trzecia odpowiedź to tabela z treści drugiej, z przypisami.
- Po zmianie tematu w czacie wyszukiwanie zwraca fragmenty dotyczące nowego pytania, a nie poprzednich.
- Po wylogowaniu i wznowieniu czatu dopytanie działa tak samo jak przed wylogowaniem.
- Format odpowiedzi jest wstecznie zgodny (nowe pola `rewritten_query`, `answer_source`).

**Tryb przejściowy we frontendzie.** Frontend nie może sam dosłać historii do modelu, bo `add_user_message`
nie ma takiego parametru. Do decyzji RadLab: włączyć w MVP `use_intelligent_query_rewrite=true`
(lepsze wyszukiwanie przy dopytaniach), jeśli model przepisujący jest dostępny w ich routerze.

---

## CR-01 · P0 · Przypisy: zdanie → fragment → strona (must have)

**Problem.** Fragmenty trafiają do modelu jako `{nazwa_dokumentu: [teksty]}`
(`engine/controllers/search/semantic.py`, `convert_search_results_to_doc2answer`, ok. l. 1306;
wywołanie w `engine/controllers/models_logic/generative.py:248`). Bez numerów, stron i identyfikatorów.
Model nie ma czego zacytować, a odpowiedź (`generative_answer`, `add_user_message`) nie zwraca listy użytych fragmentów.

**Propozycja.**
1. Ponumerować fragmenty kontekstu `[1]…[n]`. Każdy z nazwą dokumentu i stroną, np. `[3] (Raport AI Act, s. 44) …tekst…`.
2. Dodać do promptu (router / szablon systemowy) polecenie: każde twierdzenie kończ numerem fragmentu `[n]`,
   nie cytuj numerów spoza listy.
3. Zwracać w odpowiedzi `generative_answer` i `add_user_message` (oraz w `last_state`) pole:
   ```json
   "citations": [
     {"n": 3, "text_id": 1234, "document_id": 56, "document_name": "Raport AI Act.pdf",
      "page_number": 44, "text_str": "…", "char_start": 120, "char_end": 410}
   ]
   ```
4. Walidować po stronie backendu: numery w odpowiedzi ⊆ numery w `citations`. Nieznane numery usuwać albo oznaczać.

**Kryteria akceptacji.**
- Każdy numer `[n]` w odpowiedzi ma wpis w `citations` z dokumentem i stroną.
- Na zestawie testowym RadLab (np. `sse_tools/evaluation`) ≥ 90% zdań merytorycznych ma przypis.
- Format odpowiedzi jest wstecznie zgodny (nowe pole, stare bez zmian).

**Tryb przejściowy we frontendzie.** `use_doc_names_in_response=true` + `system_prompt` z poleceniem cytowania nazwy
dokumentu. Frontend dopasowuje nazwę do `detailed_results_json` i dobiera stronę. Przypis jest oznaczony „przybliżone”.

---

## CR-02 · P0 · Identyfikatory i położenie fragmentów w wynikach

**Problem.** `detailed_results` (wyszukiwanie i stan czatu) nie zawiera `text_id` ani `document_id`
(`engine/core/search_engine.py`, ok. l. 552–593). Podgląd dokumentu (`document_content`) zwraca strony,
ale nie da się w nich wskazać fragmentu.

**Propozycja.**
- Dodać do każdego wyniku `text_id`, `document_id` oraz `char_start` i `char_end` względem treści strony z `document_content`.
- `document_content` przyjmuje opcjonalnie `text_id` i zwraca stronę z zakresem do podświetlenia.

**Kryteria akceptacji.** Kliknięcie przypisu otwiera stronę i podświetla dokładnie cytowany fragment.
Ten sam fragment ma ten sam `text_id` w kolejnych zapytaniach, co umożliwia deduplikację przez agenty.

---

## CR-03 · P1 · Jawne oznaczenie odpowiedzi bez dokumentów

**Problem.** Gdy RAG nic nie znajdzie, czat po cichu odpowiada samym modelem (`chat/controllers/message.py`, ok. l. 89–107).
Frontend wnioskuje to z pustych wyników, a to kruche.

**Propozycja.**
- W odpowiedzi `add_user_message` zwracać pole `answer_source: "rag" | "llm_fallback"`.
- Dodać opcję `rag_only: true`: bez fallbacku, z jasnym komunikatem „brak treści” zależnym od `lang`.
  Dziś komunikat jest na sztywno po polsku.

**Kryteria akceptacji.** Frontend nie musi zgadywać. Przy `rag_only` żadna odpowiedź bez źródeł nie trafia do pracownika.

---

## CR-04 · P1 · Źródła i przypisy zapisane przy wiadomościach czatu

**Problem.** `GET chats` i `GET get_chat_by_hash` zwracają wiadomości bez stanu (`MessageSerializer`).
Źródła i przypisy starszych odpowiedzi znikają po zamknięciu sesji.

**Propozycja.** Dodać opcjonalny parametr `with_sources=true` dla `chats` i `get_chat_by_hash`.
Wtedy zwracany jest `DeepMessageSerializer` z `rag_message_state`, ze skróconymi wynikami i `citations`.

**Kryteria akceptacji.** Po ponownym zalogowaniu każda wcześniejsza odpowiedź RAG ma swoje przypisy i źródła.

**Relacja z CR-14.** CR-04 dotyczy tego, co pracownik widzi przy starszych odpowiedziach. CR-14 dotyczy tego,
co model pamięta. Oba korzystają z tego samego zapisu źródeł przy wiadomości.

---

## CR-05 · P1 · Zarządzanie czatami

**Problem.** `chats` zwraca wszystkie czaty ze wszystkimi wiadomościami, bez tytułów i paginacji.
Nie ma usuwania ani zmiany nazwy.

**Propozycja.**
- `GET chats?limit=&offset=&light=true`: lista `{chat_id, title, collection_name, created_at, updated_at, messages_count}`.
  Dziś `chats` nie zwraca kolekcji czatu (`prepare_response_body`: tylko `chat_id`, `is_read_only`, `chat_history`),
  więc po ponownym zalogowaniu UI nie wie, w jakiej bazie toczyła się rozmowa.
- Tytuł automatyczny z pierwszego pytania, z możliwością zmiany przez `POST rename_chat`.
- `POST delete_chat`.

**Kryteria akceptacji.** Lista 100 czatów ładuje się w < 500 ms. Pracownik może usunąć i nazwać czat.

---

## CR-06 · P2 · Postęp, streaming i zatrzymanie generowania

**Problem.** `add_user_message` blokuje do ~120 s bez informacji zwrotnej.

**Propozycja.** Wariant strumieniowy (SSE): zdarzenia `searching` (liczba dokumentów), `found` (n fragmentów),
`generating`, kolejne tokeny, `done` (pełna odpowiedź z `citations`).

**Zatrzymanie generowania.** `POST cancel_generation` (`chat_id`). Backend przerywa wyszukiwanie lub generowanie
i nie zapisuje niepełnej odpowiedzi w historii. Dziś przerwanie po stronie UI nie zatrzymuje backendu,
więc odpowiedź pojawia się później w historii mimo kliknięcia „Przerwij”.

**Kryteria akceptacji.** Pierwsza informacja o postępie w < 2 s. Frontend może pokazać etapy jak w benchmarku (Elicit).
Po „Przerwij” w historii czatu nie ma przerwanej odpowiedzi.

---

## CR-07 · P2 · Metadane dokumentu i pobranie oryginału

**Problem.**
- Brak daty i wersji dokumentu w wynikach, więc nie da się ostrzec o nieaktualnych lub sprzecznych wersjach (luka z benchmarku).
- Brak pobrania oryginalnego pliku.

**Propozycja.**
- `document_date`, `uploaded_at` i `file_type` w wynikach i w `document_content`.
- Te same pola oraz liczba stron w `GET documents`. Dziś lista zwraca tylko nazwy (`SimpleDocumentSerializer`),
  a podgląd zawartości bazy w MVP pokazuje wyłącznie nazwę i typ pliku z rozszerzenia.
- `GET document_file?document_id=`: plik albo podpisany URL, z poszanowaniem `delete_files_after_indexing`.

---

## CR-08 · P2 · Udostępnianie czatu w organizacji

**Problem.** `get_chat_by_hash` zwraca czat tylko właścicielowi, więc link „udostępnij” nie działa dla kolegi.

**Propozycja.** Czat zapisany jako read-only dostępny dla użytkowników tej samej organizacji lub grupy,
o ile mają dostęp do kolekcji czatu.

---

## CR-09 · R · API zadań asynchronicznych dla agentów

**Kontekst.** Na roadmapie są agenty, które wielokrotnie odpytują bazę, żeby przygotować materiał (raport, notatkę, zestawienie).
Jedno blokujące wywołanie do 120 s na krok tu nie wystarczy.

**Propozycja.**
- `POST agent_jobs` (cel, kolekcje, ograniczenia czasu i liczby zapytań) → `job_id`.
- `GET agent_jobs/{id}`: status, etap, postęp, wynik częściowy.
- `POST agent_jobs/{id}/cancel`.
- Wzorem kolejki indeksacji (Celery + RabbitMQ, `IndexingJob`) – infrastruktura już istnieje.

---

## CR-10 · R · Wyszukiwanie wsadowe i deduplikacja

**Propozycja.**
- `POST search_batch`: wiele `query_str` w jednym wywołaniu, wspólne opcje.
- Wyniki z `text_id` (CR-02), połączone i zdeduplikowane, z informacją, które zapytanie trafiło w który fragment.

**Kryteria akceptacji.** Agent wykonujący 10 podzapytań dostaje jedną listę unikalnych fragmentów ze źródłami.

---

## CR-11 · R · Ślad pracy agenta i cytowania w długich materiałach

**Propozycja.**
- Zapisywać trace: plan → zapytania → znalezione fragmenty → sekcje materiału → cytowania.
- Cytowania (CR-01) muszą być stabilne między krokami. Ten sam `text_id` daje ten sam przypis w całym dokumencie wynikowym.
- Eksport materiału (Markdown/DOCX) z bibliografią: dokument, strona.

**Kryteria akceptacji.** Każde zdanie wygenerowanego materiału da się prześledzić do fragmentu źródłowego.

---

## CR-12 · R · Plan i pytania doprecyzowujące

**Propozycja.**
- Krok „plan” zwracany przed wykonaniem zadania agenta (lista podzapytań i źródeł do edycji przez użytkownika).
- Pytanie doprecyzowujące z opcjami, gdy cel jest niejasny (wzorce Gemini, Copilot i Unify z benchmarku).

---

## CR-18 · P1 · Wybór dokumentów zapamiętany przy czacie

**Kontekst.** W MVP pracownik zaznacza dokumenty, w których RAG ma szukać (wzorzec NotebookLM).
Frontend wysyła je w `search_options.documents` przy każdym `add_user_message` – to działa dziś.

**Problem.** Backend zapisuje `search_options` przy każdej wiadomości, ale `MessageSerializer` ich nie zwraca,
a czat nie ma własnego zakresu. Po wznowieniu rozmowy z wcześniejszej sesji frontend nie wie, które dokumenty
były zaznaczone, i wraca do „wszystkie”.

**Propozycja.**
- Zakres dokumentów zapisany przy czacie: `POST set_chat_documents` (`chat_id`, `documents[]`) albo pole w `new_chat`.
- `GET chats` zwraca `documents` dla czatu. `add_user_message` bez `search_options.documents` używa zakresu czatu.
- Gdy dokument z zakresu zostanie usunięty z bazy, odpowiedź zawiera listę `missing_documents`.

**Kryteria akceptacji.** Po ponownym zalogowaniu i otwarciu czatu zaznaczone są te same dokumenty co przed wylogowaniem.

---

## CR-19 · P1 · `system_prompt` łączony z promptem szablonu

**Problem.** Gdy zapytanie pasuje do szablonów pytań kolekcji, backend losuje prompt szablonu i **zastępuje** nim
`system_prompt` z żądania (`chat/controllers/message.py`, `_prepare_rag_supervisor_state`, `template_prompts`).
Interfejs przekazuje w `system_prompt` format odpowiedzi i polecenie cytowania, więc w takich kolekcjach
oba przestają działać.

**Propozycja.** Łączyć prompty: najpierw prompt szablonu, potem `system_prompt` z żądania. Albo osobne pole
`answer_instructions`, dokładane zawsze na końcu promptu.

**Kryteria akceptacji.** W kolekcji z szablonami odpowiedź ma wybrany format i nazwy dokumentów do przypisów.

---

## CR-15 · P2 · Dopracowanie pytania przed wysłaniem

**Problem.** Pracownicy wpisują krótkie pytania („koszty AI 2025”). RAG szuka wtedy szeroko, a odpowiedź jest ogólna
albo chybiona. W benchmarku dobre narzędzia pomagają doprecyzować pytanie, zanim zaczną szukać
(Unify, Gemini; podobnie tryby w Claude i narzędzia typu Prompt Cowboy).

**Propozycja.**
- `POST refine_question` (`collection_name`, `question`, opcjonalnie `chat_id`) zwraca:
  ```json
  {"refined_question": "Jakie koszty wdrożenia narzędzi AI zaplanowano na 2025 r. w raportach budżetowych?",
   "changes": ["dodano okres", "dodano rodzaj kosztów"],
   "missing": [{"label": "Zakres", "options": ["cała firma", "dział IT", "projekty pilotażowe"]}]}
  ```
- Model bierze pod uwagę opis kolekcji, listę dokumentów i historię czatu (CR-14).
- Wywołanie trwa poniżej 3 s (mały model). Można oprzeć je na istniejącym mechanizmie `_rewrite_query_with_llm`.

**Jak to wygląda w UI.** Przy krótkim lub ogólnym pytaniu pod polem pojawia się propozycja „Doprecyzowane pytanie”.
Pracownik ją akceptuje, poprawia albo wysyła swoją wersję bez zmian. Nic nie dzieje się bez jego zgody.

**Kryteria akceptacji.** Na zestawie testowym RadLab odpowiedzi na pytania doprecyzowane mają wyższą ocenę
niż na pytania oryginalne. Pracownik może zawsze wysłać pytanie bez zmian.

**Relacja.** CR-12 (pytania doprecyzowujące agentów) może korzystać z tego samego endpointu.

---

## CR-16 · P1 · Sekcje w historii i przypinanie rozmów

**Problem.** Historia to płaska lista czatów. Pracownik prowadzący kilka tematów naraz (raport, przetarg, regulacje)
nie ma jak ich uporządkować. Wzorzec: sekcje i projekty w Claude.

**Propozycja.**
- `GET chat_groups`, `POST chat_groups` (`name`), `POST rename_chat_group`, `POST delete_chat_group`
  (czaty wracają do „Bez sekcji”).
- `POST move_chat` (`chat_id`, `group_id`); `GET chats?group_id=` (łącznie z CR-05).
- `POST pin_chat` (`chat_id`, `pinned`); `GET chats` zwraca `group_id` i `pinned` dla każdego czatu.
- `new_chat` przyjmuje opcjonalnie `group_id` (przycisk „+” przy sekcji).
- Kolejność sekcji: `POST reorder_chat_groups` (później, przy przeciąganiu).
- Opcjonalnie: domyślna kolekcja sekcji (nowy czat w sekcji startuje z jej bazą wiedzy).

**Stan UI.** Sekcje są zaprojektowane i działają w prototypie (wzorzec Claude Code: nagłówek sekcji ze zwijaniem i „+”,
menu ⋯ przy rozmowie: Przypnij, Zmień nazwę, Przenieś do sekcji, Usuń). Frontend włączy je flagą `features.chat_sections`
po wdrożeniu tego zgłoszenia i CR-05. Priorytet podniesiony z P2 na P1 decyzją z 2026-11-01.

**Kryteria akceptacji.** Pracownik tworzy sekcję, przenosi do niej czat, przypina czat, a po ponownym zalogowaniu
widzi ten sam układ historii.

---

## CR-17 · R · Notatki z odpowiedzi do ponownego użycia

**Problem.** Dobre odpowiedzi giną w historii. Pracownik chce zebrać z kilku rozmów fragmenty z przypisami
i użyć ich w innym zadaniu (wzorzec NotebookLM).

**Propozycja.**
- `POST notes` (`chat_id`, `message_id`, `text` – cała odpowiedź albo zaznaczony fragment, `citations[]`, opcjonalnie `group_id`).
- `GET notes` (filtr po sekcji z CR-16), `POST update_note`, `POST delete_note`.
- Notatka zachowuje przypisy (`text_id` z CR-02), więc da się ją zweryfikować u źródła także po miesiącu.
- `add_user_message` przyjmuje opcjonalnie `note_ids[]`. Treść notatek trafia do kontekstu modelu obok wyników wyszukiwania.
- Agenty (CR-09) przyjmują notatki jako materiał wejściowy.

**Kryteria akceptacji.** Pracownik zapisuje fragment odpowiedzi jako notatkę, otwiera ją później z przypisami
i zadaje pytanie z tą notatką jako kontekstem.

**Zależności.** CR-01, CR-02, CR-14.

---

## CR-13 · później · PPTX, XLSX, CSV

Odłożone decyzją z 2026-11-01. Do podjęcia po poprawkach MVP: czytniki plików i reprezentacja danych tabelarycznych
(wiersz/arkusz jako źródło przypisu).
