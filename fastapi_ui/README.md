# Semantic Search Engine UI — FastAPI + Jinja2

Aplikacja interfejsu użytkownika dla silnika **[semantic-search-engine](https://github.com/radlab-dev-group/semantic-search-engine)** zbudowana na **FastAPI + Jinja2**.
Prezentacja oparta jest o renderowane po stronie serwera szablony HTML (bez zewnętrznych frameworków SPA) oraz stan sesji przechowywany w bezpiecznym, podpisanym ciasteczku sesyjnym i magazynie pamięciowym.

## Uruchomienie

```bash
cd fastapi_ui
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
bash run.sh                       # http://localhost:8000
```

Bezpośrednio:

```bash
cd fastapi_ui
uvicorn server:app --host 0.0.0.0 --port 8000
```

### Zmienne środowiskowe

| Zmienna | Domyślnie | Opis |
| --- | --- | --- |
| `UI_HOST` | `0.0.0.0` | adres nasłuchu Uvicorn |
| `UI_PORT` | `8000` | port Uvicorn |
| `UI_CONFIG_PATH` | `configs/ui-configuration.json` | ścieżka do konfiguracji API |
| `UI_SECRET_KEY` | `change-me-in-production` | klucz podpisujący ciasteczko sesji (**zmień w produkcji**) |
| `UI_MAX_UPLOAD_SIZE_MB` | `6000` | limit rozmiaru pojedynczego pliku przy uploadzie (w MB) |
| `UI_MAX_UPLOAD_FILES` | `500` | maksymalna liczba plików w jednym żądaniu uploadu |
| `UI_DEFAULT_LANGUAGE` | `en` | język interfejsu (`en` / `pl`), gdy użytkownik go nie wybrał, a przeglądarka nie podaje obsługiwanego języka |

Konfiguracja hostów/endpointów backendu znajduje się w pliku `configs/ui-configuration.json` (lub pod ścieżką wskazaną w `UI_CONFIG_PATH`).

## Trasy i moduły aplikacji

| Trasa / Moduł | Opis |
| --- | --- |
| `GET /home` | Strona główna z opisem projektu i schematem pipeline'u RAG |
| `GET/POST /login`, `GET /logout` | Logowanie użytkownika (token Django `Authorization: Token ...`) i wylogowanie |
| `GET /collections`, `POST /collections/new`, `POST /collections/delete` | **Baza wiedzy → Kolekcje**: lista kolekcji (`GET api/collections`, z chunkingiem z `metadata_json`), tworzenie nowej kolekcji (`api/embedders` / `api/rerankers` z `models_info`, `api/filter_options` → `chunking_defaults`, opcjonalne `chunking` + `strict_chunking` w `POST api/new_collection`) oraz usuwanie kolekcji (`POST api/delete_collection`) |
| `GET /collections/manage`, `POST /collections/manage/delete-*` | **Baza wiedzy → Dokumenty**: lista dokumentów kolekcji, usuwanie dokumentów (`api/delete_documents`), usuwanie chunków tekstu (`api/delete_texts`), włączanie/wyłączanie dokumentów w wyszukiwaniu (`POST /collections/manage/visibility` → `api/set_documents_use_in_search`) oraz usuwanie kolekcji |
| `GET /collections/documents/preview` | **Baza wiedzy → Dokumenty → Podgląd**: cała treść jednego dokumentu w osobnym oknie (`GET api/document_content`); `?download=1` zwraca ten tekst jako plik `.txt` |
| `GET/POST /documents/upload`, `POST /collections/manage/add-text` | **Baza wiedzy → Dodaj treść**: upload plików (`pdf/docx/txt/html/md/zip`) z opcjami indeksowania albo wklejenie surowego tekstu (`api/add_and_index_texts`); klucze chunkingu w `indexing_options` są opcjonalne (domyślnie ustawienia kolekcji), błędy `000005_DATA` / `000006_DATA` wracają na formularz |
| `GET /collections/indexing-status` | **Baza wiedzy → Indeksacja**: JSON z postępem indeksacji (`api/indexing_status`) — liczniki najnowszego zadania kolekcji (albo zadania o danym `job_id`), dokumenty z ich statusami i ile dokumentów wciąż czeka; czyta go panel postępu i `app.js` |
| `GET/POST /search`, `POST /search/generate`, `POST /search/rate` | **Wyszukiwanie**: wyszukiwanie semantyczne/hybrydowe, odpowiedź generatywna (doczytywana asynchronicznie po wynikach) oraz ocenianie (gwiazdki i komentarz) |
| `core/api.py` | Klient REST API backendu SSE |
| `core/state_store.py` | Pamięciowy magazyn stanu sesji użytkownika |
| `core/constants.py` | Stałe, wartości domyślne formularzy i limitów |
| `server.py` | Główna aplikacja FastAPI: routing, obsługa sesji, walidacja i przygotowanie danych |

### Dodatkowe endpointy i mechanizmy:

- `GET /api/options?collection_name=...` — JSON z kategoriami i dokumentami
  kolekcji; używany przez `app/static/js/app.js` do odświeżania filtrów po zmianie
  kolekcji bez przeładowania całej strony. Filtry (kategorie i
  dokumenty) są dostępne na stronie wyszukiwania.
- `GET /lang/{pl|en}?next=/sciezka` — przełącza język interfejsu (ciasteczko
  `sse_lang`, rok ważności) i wraca na stronę `next` (tylko ścieżki lokalne).
- `GET /search/history/{query_response_id}` — wyszukiwanie z historii: pytanie,
  instrukcja, zapisane wyniki i ostatnia wygenerowana odpowiedź (z formularzem
  oceny, zapisana ocena jest zaznaczona). Panel „Historia wyszukiwań” pod
  polem pytania pokazuje wyszukiwania użytkownika tylko w wybranej kolekcji
  (silnik: `GET api/search_history?collection_name=…`, maks. 50, od
  najnowszych), każdy wpis z datą i godziną wyszukiwania (`created_on`
  silnika, „RRRR-MM-DD GG:MM”; silnik bez tego pola nie pokazuje daty); po zmianie kolekcji w panelu bocznym jest odświeżany przez
  `GET /search/history?collection_name=…` (JSON z fragmentem HTML). Szczegóły
  wpisu pobiera `GET api/get_search_history?query_response_id=…`. Gdy plik
  konfiguracyjny nie zawiera tych endpointów, używane są domyślne ścieżki.
- `GET /search/params/reset?collection_name=…` — przywraca domyślne parametry
  wyszukiwania. Opcje z panelu bocznego (liczba wyników, modele, opcje
  generowania, filtry, prompt) są zapamiętywane w stanie sesji przy każdym
  `POST /search` i wypełniają formularz po wyszukiwaniu, po ocenie odpowiedzi
  i przy kolejnym wejściu na `/search`. Niezależnie od tego przeglądarka
  zapamiętuje panel w `localStorage` (`sse-search-params`, `app.js` →
  `initParamsMemory`): wartości pól oraz zwinięcie/rozwinięcie grup Kolekcja /
  Modele / Filtry i „Opcje generowania” wracają przy następnej wizycie także bez
  uruchomienia wyszukiwania (filtry tylko dla kolekcji, w której je wybrano;
  `?collection_name=` w adresie ma pierwszeństwo przed zapamiętaną kolekcją).
  Reset przekierowuje na `/search?…&params_reset=1`, co każe przeglądarce
  zapomnieć również swoją kopię.
- `POST /search/generate` (`generation_id`) — odpowiedź generatywna dla
  wyszukiwania, którego wyniki są już na stronie. `POST /search` nie czeka na
  model: od razu renderuje wyniki i kartę „Odpowiedź modelu” w stanie
  oczekiwania, a parametry generowania (`query_response_id`, prompt, opcje)
  odkłada w stanie sesji pod jednorazowym `generation_id`. `app.js` wywołuje ten
  endpoint i podmienia kartę na odpowiedź (JSON: `answer_html` +
  `feedback_html`, czyli formularz oceny). Nieznany/zużyty `generation_id` → 409.
- `GET /healthz` — endpoint kontrolny (health check).
- `GET /docs` — wbudowana dokumentacja OpenAPI.

## Indeksacja i jej postęp

Silnik indeksuje dokumenty **w wątku żądania** (domyślnie) albo w **kolejce
Celery z RabbitMQ** (`ENV_USE_CELERY=1` w backendzie, opis w
`../semantic-search-engine/README.md`). Interfejs nie musi się o to martwić:
endpointy `api/upload_and_index_files` i `api/add_and_index_texts` odpowiadają
zadaniem indeksacji w polu `indexing_job` (plus `"async": true`, gdy praca
została tylko wpisana do kolejki), a `GET api/indexing_status` mówi, na czym
polega.

**Panel „Postęp indeksowania"** (`app/templates/partials/indexing_status.html`)
widać na stronach *Dodaj treść* i *Dokumenty*:

- pasek postępu (wyznaczony, gdy znana jest liczba dokumentów, w przeciwnym
  razie przesuwający się), liczniki: zaindeksowane / oczekujące / błędy /
  pominięte oraz procent,
- dokument indeksowany w tej chwili, lista dokumentów, którym się nie powiodło,
  i komunikat błędu zadania,
- licznik dokumentów kolekcji, które wciąż czekają na indeksowanie.

Dokumenty na liście dostają plakietkę stanu (`pending` / `indexing` /
`failed` / `skipped`); zaindeksowany dokument nie potrzebuje plakietki.

**Pasek na liście kolekcji** (`collections.html`, `initCollectionIndexing` w
`app.js`): karta kolekcji, której najnowsze zadanie indeksacji wciąż trwa
(`job.finished == false` z `GET api/indexing_status`), dostaje pod spodem
poruszający się pasek z napisem „Indeksowanie…”. Pasek nie musi oddawać
realnego postępu — jest animacją CSS (`indeterminate`); liczniki i szczegóły
zadania widać po wejściu w kolekcję. `app.js` odpytuje
`GET /collections/indexing-status?collection_name=…` co
`INDEXING_POLL_INTERVAL_MS` (2 s), pauzuje, gdy karta jest niewidoczna
(`visibilitychange`), przerywa po trzech kolejnych błędach (silnik bez
endpointu nie może zapętlzić strony) i **przeładowuje listę tylko wtedy, gdy
któraś odpowiedź różni się od tej, z której karty zostały wyrenderowane**
(`status:percent` na kartę) — lista, na której nic się nie zmieniło, ładuje
się ponownie nigdy.

Dopóki zadanie jest w toku, `app.js` (`initIndexingStatus`) odpytuje
`GET /collections/indexing-status?collection_name=…&job_id=…` co
`constants.INDEXING_POLL_INTERVAL_MS` (2 s): aktualizuje panel i plakietki
wierszy, pauzuje, gdy karta jest niewidoczna (`visibilitychange`), i kończy,
gdy zadanie się skończyło albo po `INDEXING_POLL_TIMEOUT_MS` (30 min).
Silnik bez `api/indexing_status` (albo z błędującym endpointem) nie psuje
stron — panel po prostu nie pojawia się, a trasa JSON zwraca 502.

## Obsługa API backendu

Logowanie (`POST /login`) wysyła `username`/`password` na `api/login`, a zwrócony
`token` jest zapisywany w podpisanej sesji (ciasteczko `sse_ui_session`) — hasło
nigdy nie jest przechowywane. Wszystkie kolejne żądania idą z nagłówkiem
`Authorization: Token <token>` (patrz `fastapi_ui/core/api.py`).

Format odpowiedzi backendu (radlab-semantic-search-engine):

```json
{"status": true, "body": { "...": "..." }}
```

```json
{"status": false, "errors": [{"code": "...", "msg": "...", "required_params": []}]}
```

Kody błędów są renderowane na dedykowanej stronie `error.html` z czytelnym podsumowaniem problemu i ewentualnymi szczegółami z odpowiedzi silnika.

### Treść jednego dokumentu (`GET api/document_content`)

Podgląd dokumentu pyta silnik o całą jego treść:

```
GET {host}/api/document_content?collection_name=…&document_name=…
```

Ścieżkę endpointu ustawia `document_content` w `configs/ui-configuration.json`
(domyślnie `api/document_content`), więc wdrożenie z `/api/v1/` albo z inną
nazwą nie wymaga zmian w kodzie. Interfejs przyjmuje każdy z kształtów, jakie
silnik może zwrócić w `body`:

| Kształt `body` | Co widać w oknie |
| --- | --- |
| `{"pages": [{"page": 1, "content": "…"}, …]}` | treść strona po stronie z numerem strony |
| `{"content": "…"}` (także `text` / `text_str` / `page_content`) | cały tekst w jednym bloku |
| `{"texts": [...]}` / `{"chunks": [...]}` | chunki scalone w jednym tekście (wg `text_number` / `id`) |
| `status: false` (brak endpointu, dokument nieznany) | komunikat o braku treści, bez pustej strony |

Silnik odpowiada jednym `content` **i** tym samym tekstem w `pages[]` — numery
stron wygrywają, więc okno ich nie wyrzuca. Pola okna (`total_pages`,
`truncated`) mówią, czy doczytano tylko część dokumentu: licznik pokazuje
wszystkie strony, a pod nagłówkiem pojawia się informacja, ile z nich
zaprezentowano.

Tekst w oknie jest **przygotowany do czytania** (`preview_text`): podwójne i
dłuższe serie spacji w środku linii stają się jedną spacją, linia nie ma
spacji na końcu, po kolei zostaje co najwyżej jedna pusta linia, a wcięcie
większe niż 8 znaków jest przycinane do 8. Indeksowany PDF rozsuwa słowa
setkami spacji i zostawia całe strony pustki, a okno ma czytać dokument, nie
odtwarzać układu jego źródła; łamane są wyrazy, nie układ strony (CSS
`overflow-wrap: anywhere`, inaczej tekst o niepodzielnym TOKEN-ie albo o
setkach spacji rozpychał okno w poziomie). `Pobierz jako .txt` oddaje tekst
silnika bez tych zmian.

## Uwagi implementacyjne

- **Extractive QA**: pozostaje opcją w formularzu; faktyczne wykonanie ekstrakcji realizowane jest po stronie silnika.
- **Tłumaczenie odpowiedzi**: suwak i wybór języka („Translate generated answer”) wysyła `translate_answer` + `answer_language` bezpośrednio do backendu.
- **Ocena odpowiedzi**: wybór 1-5 gwiazdek (radio) z opcjonalnym komentarzem tekstowym, powiązany z ID wygenerowanej odpowiedzi.
- **Tabele i fragmenty wyników**: renderowane jako karty HTML lub tabele z sortowaniem według `score_weighted` / `score`.

## Wygląd (UI)

Nowoczesny, responsywny interfejs bez zewnętrznych zależności (żadnych CDN-ów ani
fontów z sieci — działa offline, ikony są w inline SVG). Język wizualny
„przestrzeni wektorowej” nawiązuje do przeznaczenia aplikacji: ciemne tło z
delikatną siatką współrzędnych, świecące węzły (embeddingi) i gradient
podobieństwa teal → fiolet → magenta, używany m.in. w paskach `score`.

- **Strona główna**: hero „Search by meaning, not by keywords” z animowaną
  wizualizacją przestrzeni embeddingów (zapytanie + k najbliższych sąsiadów ze
  skorami cosinusowymi), schemat pipeline'u RAG (Chunk → Embed → Retrieve &
  rerank → Generate) i skróty do kolejnych kroków.
- **Stepper pipeline'u** (`partials/stepper.html`): Collection → Index → Search
  w nagłówku strony wyszukiwania.
- **Baza wiedzy** — jedna pozycja w nawigacji zamiast trzech. Strony kolekcji,
  dokumentów i dodawania treści mają wspólny nagłówek (`partials/kb_header.html`)
  z zakładkami Kolekcje / Dokumenty / Dodaj treść i przełącznikiem kolekcji;
  wybrana kolekcja jest zapamiętywana w stanie sesji (`kb_collection`), więc
  przechodzenie między zakładkami jej nie gubi.
  - **Kolekcje** jako karty (nazwa, opis, data, a pod nią liczniki z
    `GET api/collections` w osobnym wierszu: wszystkie dokumenty i osobno te
    biorące udział w wyszukiwaniu — „128 dokumentów · 120 aktywnych”, przy
    czym karta kolekcji z silnika starszego niż 0.1.5 (brak pól) nie pokazuje
    niczego zamiast zera; dalej zadeklarowany podział na chunki z
    `metadata_json` — „512 tokenów · zakładka 32” plus odznaka
    `strict`, albo „podział niezadeklarowany” gdy `metadata_json` jest `null`;
    akcje Dokumenty / Dodaj treść / Szukaj, usuwanie ikoną kosza). Nad kartami
    jest filtr po nazwie (jak filtr dokumentów): pole `type=search`
    wszystkie wpisane słowa z `data-search` karty, czyli małą nazwą
    wyświetlaną i techniczną kolekcji; licznik „{n} z {total}” pojawia się
    tylko przy aktywnym filtrze, a przy braku trafień widać komunikat
    (`initCollectionFilter` w `app.js`, nic nie jest odpytywany silnik).
    Kart widać po sześć (`COLLECTIONS_PER_PAGE` w `app.js`), a pod siatką
    pojawiają się strzałki i wpis „strona X z Y” — sterunek chowa się, gdy
    wszystkie karty mieszczą się na jednej stronie (również po przefiltrowaniu),
    a filtrowanie wraca na pierwszą stronę. Zmiana strony nic nie przewija:
    karta zostaje dokładnie tam, gdzie ją zostawiono. Wszystkie karty są w HTML od
    serwera, więc bez JS lista zostaje kompletna, tylko bez okienkowania.
  - **Nowa kolekcja**: oprócz modeli i typu indeksu karta „Podział na chunki”
    (`max_tokens_in_chunk`, `number_of_overlap_tokens`, przełącznik
    `strict_chunking`). Oba parametry to suwaki (jak przy indeksowaniu)
    ustawione na `chunking_defaults` z `GET api/filter_options`; `chunking`
    trafia do `POST api/new_collection` tylko wtedy, gdy użytkownik je
    przesunął (`app.js` ustawia ukryte `chunking_edited`, serwer porównuje też
    z wartościami wyrenderowanymi w formularzu). Opcje embedderów i rerankerów
    niosą `models_info` (`data-max-length`, `data-vector-size`,
    `data-device`): zakres suwaka chunka kończy się na `max_model_length`
    wybranego embedera (brak = zwykły zakres `MAX_TOKENS_IN_CHUNK_LIMIT`,
    rozciągany, gdy pokazywana wartość jest większa), suwak zakładki jest
    ograniczany do `[0, chunk)` (i `OVERLAP_TOKENS_LIMIT`), a chunk ≥
    `max_model_length` rerankera daje tylko ostrzeżenie. Bez `filter_options`
    suwaki stają na `DEFAULT_MAX_TOKENS_IN_CHUNK` / `DEFAULT_OVERLAP_TOKENS`,
    ale dopóki ich nie ruszysz, do silnika nadal nic nie jest wysyłane.
  - **Dokumenty**: lista z filtrem i zaznaczaniem wielu pozycji, obok panel
    usuwania chunków po ID i strefa usunięcia kolekcji. Przy każdym dokumencie,
    obok kosza, jest przełącznik „W wyszukiwaniu” (`use_in_search`): wyłączony
    dokument zostaje w kolekcji (teksty i wektory), ale silnik go nie
    przeszukuje i nie ma go w filtrach wyszukiwarki. Przełącznik działa bez
    przeładowania strony (JSON z `POST /collections/manage/visibility`), a
    przyciski „Włącz / Wyłącz zaznaczone” zmieniają wiele dokumentów naraz.
    Lista pobiera dokumenty z `GET api/documents?with_disabled=true`; silnik bez
    tego parametru zwraca tylko włączone dokumenty, więc wyłączonych nie
    będzie widać.
    Każdy wiersz ma też link **„Podgląd”** (`GET /collections/documents/preview`,
    `target="_blank"`): w nowym oknie pokazuje **całą treść dokumentu**
    zaciągniętą z `GET api/document_content` — wiersz po wierszu, strona po
    stronie (silnik zwraca jeden tekst, strony albo chunki, patrz niżej). Okno
    ma przycisk pobrania `Pobierz jako .txt` i wraca na zakładkę Dokumenty;
    dokument bez tekstu i odmowa silnika mają osobne komunikaty, a bardzo długi
    tekst jest w oknie przycinany (`DOCUMENT_PREVIEW_MAX_CHARS`) — pobrany plik
    ma zawsze całą treść.
  - **Dodaj treść**: przełącznik „Wgraj pliki” (drag & drop + podgląd
    chunkowania pokazujący stosunek `overlap` do rozmiaru chunka) /
    „Wklej tekst”. Oba formularze (`partials/indexing_options.html`) mają
    wybór `chunking_mode`: **Ustawienia kolekcji** (domyślnie — do
    `indexing_options` nie trafiają klucze chunkingu, silnik dzieli tak, jak
    deklaruje kolekcja albo wg swoich domyślnych) lub **Własne wartości**
    (wysyłane są oba klucze; po wybraniu tej opcji suwaki startują od
    `DEFAULT_MAX_TOKENS_IN_CHUNK` = 300 tokenów i `DEFAULT_OVERLAP_TOKENS`
    = 60 tokenów zakładki, a powrót do „Ustawienia kolekcji” przywraca
    wartości kolekcji). Przy kolekcji `strict` wybór własnych wartości od
    razu ostrzega, że silnik odpowie `CHUNKING_MISMATCH`.
  - **Błędy chunkingu silnika** (`errors[].error_code`, HTTP 200):
    `000005_DATA` (CHUNKING_TOO_LONG) wraca na formularz z podświetlonym
    polem/suwakiem rozmiaru chunka i komunikatem silnika (w języku UI, parametr
    `lang`), `000006_DATA` (CHUNKING_MISMATCH) czyści nadpisanie i proponuje
    wartości kolekcji; wklejony tekst nie ginie (`text_draft`).
- **Usuwanie**: zamiast `confirm()` przeglądarki stylowany dialog
  (`<dialog id="confirm-dialog">` w `base.html`, atrybuty `data-confirm*` na
  formularzu lub przycisku) z listą usuwanych pozycji; usunięcie kolekcji
  wymaga wpisania jej nazwy. Wynik pokazuje alert `alert-deleted` z ikoną
  kosza, przekreślonymi nazwami / ID i liczbą usuniętych chunków i wektorów.
- **Wyszukiwanie**: wyróżniona „konsola zapytania” z banerem przeszukiwanej
  kolekcji nad polem pytania (nazwa, nazwa techniczna, opis, liczba
  dokumentów i data utworzenia oraz przyciski „Dokumenty” / „Zmień”; `app.js`
  → `initCollectionBanner` odświeża go po zmianie kolekcji w sidebarze z
  atrybutów `data-description` / `data-created` opcji `<select>`, a bez
  wybranej kolekcji pokazuje podpowiedź), przykładowe pytania jako
  klikalne chipy, panel parametrów w przyklejonym (sticky) sidebarze
  (`partials/search_params.html`: zwijane grupy Kolekcja / Modele / Filtry z
  podsumowaniem w nagłówku, opcje jako kafelki z opisem — w tym przełącznik
  wyszukiwania hybrydowego `hybrid_search` i rerankingu, licznik wyników
  z −/+ i szybkim wyborem, suwaki z opisem i oznaczeniem wartości innych niż
  domyślne, filtry jako listy z wyszukiwaniem — natywne `<select multiple>`
  zostają w formularzu jako źródło prawdy; w grupie Filtry jest też suwak
  „Minimalne podobieństwo (cosinus)” → opcja `min_similarity` zapytania
  `search_with_options` w zakresie 0–1, domyślnie `DEFAULT_MIN_SIMILARITY`
  = 0.5 jak w silniku, 0 wyłącza próg — fragmenty poniżej progu są odrzucane,
  więc wysoki próg może dać pustą listę wyników; serwer przycina wartość do
  [0, 1], a próg inny niż domyślny widać w podsumowaniu grupy), karta
  odpowiedzi modelu z gradientowym akcentem nad wynikami, ocena odpowiedzi
  gwiazdkami. Przy generatywnym QA wyniki pokazują się od razu, a karta
  odpowiedzi ma animowany szkielet i licznik czasu, dopóki model nie skończy.
- **Wyniki („What the engine found”)**: zamiast szerokiej tabeli każdy
  fragment to karta (`partials/hits.html`) z pozycją w rankingu, dokumentem,
  stroną/chunkiem/językiem, skorem i paskiem względem najlepszego trafienia
  oraz tekstem fragmentu z podświetlonymi słowami pytania (dopasowanie po
  rdzeniu, więc łapie też odmiany). Długie fragmenty można rozwinąć, skopiować,
  a pozostałe pola są w „more field(s)”. Nad i pod fragmentem widać jego
  kontekst (`left_context` / `right_context` z silnika — sąsiednie chunki,
  przycięte do kilku linii i rozwijane razem z fragmentem). Tekst fragmentów i
  kontekstu jest renderowany jako Markdown (surowy HTML jest escapowany);
  przełączniki „Kontekst” i „Markdown” w pasku narzędzi pozwalają ukryć
  kontekst lub wrócić do zwykłego tekstu (zapamiętywane w `localStorage`).
  „Kopiuj” zawsze kopiuje oryginalny tekst. Chipy nad listą filtrują fragmenty po
  dokumencie. Statystyki (`partials/doc_board.html`) to ranking dokumentów z
  udziałem w masie rankingu. Surowa tabela jest nadal dostępna przełącznikiem
  „Table” (wybór zapamiętywany w `localStorage`).
- **Motyw jasny/ciemny**: wartość `auto` podąża za `prefers-color-scheme`, a
  przycisk w pasku nawigacji przełącza `auto → light → dark`; wybór zapisywany
  jest w `localStorage` pod kluczem `sse-theme` (ustawiany przed pierwszym
  malowaniem, więc brak „flasha” przy wczytywaniu).
- **Tokeny designu** w `:root` (kolory, gradienty, cienie, radiusy, odstępy) w
  `app/static/css/style.css` — naklejenie innego brandu to zmiana
  kilku zmiennych.
- **Responsywność**: breakpointy 1024 px (jedna kolumna hero/sidebar), 900 px
  (nawigacja w hamburger), 720 px (stackowanie pól i suwaków), 420 px
  (kompaktowy stepper).
- **Dostępność**: link „Skip to content”, widoczne ramki fokusu, `aria-*` przy
  przełącznikach, nawigacji i stepperze, respektowane `prefers-reduced-motion`,
  styl do druku.
- **UX**: zakładki wyników jako segmentowany kontroler, sticky-header tabel,
  rozwijane sekcje (JSON, opcje generacji), pasek postępu
  uploadu, spinner na przyciskach formularzy, podświetlanie aktywnej pozycji w
  nawigacji, a filtry kategorii i dokumenty odświeżają się bez przeładowania po
  zmianie kolekcji.
- **Komunikaty** (`app/templates/partials/messages.html`): jeden styl alertów
  (ikona SVG + `alert__content`) dla `error` / `warning` / `success` oraz dla
  błędów zwróconych przez silnik. Po utworzeniu kolekcji i po indexowaniu
  zamiast zrzutu słownika API renderowane jest podsumowanie (`dl.kv` z nazwą
  kolekcji, modelem, typem indeksu, liczbą plików…) oraz przycisk przejścia do
  następnego kroku — `GET /documents/upload` i `GET /search` przyjmują
  `?collection_name=`, więc kolekcja jest już wybrana. Surowy JSON zostaje
  tylko tam, gdzie ma sens: w `error.html` i sekcjach „Show json".

## Wielojęzyczność (PL / EN)

Interfejs jest dostępny po polsku i po angielsku. Przełącznik `EN | PL` jest w
pasku nawigacji (także na stronie logowania).

- **Wybór języka**: ciasteczko `sse_lang` (ustawiane przez `GET /lang/<kod>`),
  potem nagłówek `Accept-Language` przeglądarki, a na końcu
  `UI_DEFAULT_LANGUAGE`.
- **Teksty** są w `app/locales/en.json` i `app/locales/pl.json`. To zagnieżdżone
  obiekty, a w szablonach odwołujesz się do nich kluczem z kropkami:
  `{{ t('nav.search') }}`, `{{ t('collections.created_on', date=...) }}`.
  Brakujący klucz w danym języku zastępuje tekst angielski.
- **Liczba mnoga**: wpis może być obiektem z formami CLDR `one` / `few` /
  `many` / `other`, używany przez `{{ t.plural('upload.files_count', n) }}`
  („1 plik”, „3 pliki”, „5 plików”). W przeglądarce formę wybiera
  `Intl.PluralRules`.
- **HTML w tłumaczeniach**: tylko klucze z sufiksem `_html` mogą zawierać
  znaczniki. Wstawiane do nich wartości są escapowane.
- **JavaScript**: sekcja `js` aktualnego języka trafia do strony jako
  `<script type="application/json" id="i18n-data">`, a `app.js` korzysta z niej
  przez `t(key, vars)`.
- **Komunikaty serwera** (błędy formularzy, sukces uploadu itd.) są tłumaczone
  w `server.py` przez `translator(request)`. Treść zwracana przez silnik (np.
  błędy API, odpowiedzi modelu) i dane wysyłane do silnika (np. domyślny opis
  kolekcji „Opis kolekcji …”) zostają bez zmian.
- Nowy język to nowy plik `app/locales/<kod>.json` i wpis w
  `core/i18n.py: LANGUAGES` (oraz reguła liczby mnogiej w `plural_category`).

## Testy

Smoke test odpala aplikację FastAPI wraz z **mockowanym backendem SSE**
(`tests/mock_sse_backend.py` odwzorowuje kształty odpowiedzi
`radlab-semantic-search-engine`), przechodzi całą ścieżkę: logowanie, tworzenie
kolekcji, upload plików, wyszukiwanie z odpowiedzią generatywną, ocenianie,
przełączanie języka (zgodność kluczy PL/EN, formy mnogie, brak
nieprzetłumaczonych kluczy na stronach), wylogowanie. Osobna funkcja
`check_indexing` przechodzi indeksację: zadanie w kolejce (atrapa silnika
przesuwa kolekcję o jeden dokument na każde pytanie o status), trasę JSON
`/collections/indexing-status`, plakietki stanów na liście dokumentów i
zachowanie stron, gdy silnik nie ma `api/indexing_status`. Osobny blok sprawdza
podgląd całego dokumentu: link w wierszu listy, treść z
`api/document_content` (tekst i strony), pobranie `.txt`, dokument bez treści,
odmowę silnika i przycięcie długich tekstów. Nie wymaga prawdziwego backendu
ani bazy wektorów.

```bash
cd fastapi_ui
.venv/bin/pip install httpx            # zależność testowa
.venv/bin/python tests/smoke_test.py     # 195 checków, wyjście != 0 przy porażce
```

## Struktura katalogów

```text
fastapi_ui/
├── server.py              # aplikacja FastAPI: trasy, sesja, przygotowanie danych
├── run.sh                 # skrypt uruchomieniowy
├── requirements.txt
├── configs/
│   └── ui-configuration.json
├── core/
│   ├── api.py             # klient REST API SSE
│   ├── constants.py
│   ├── i18n.py            # tłumaczenia interfejsu (pl / en), wybór języka
│   ├── markdown.py        # renderowanie Markdown z podświetlaniem i tabelami
│   └── state_store.py     # stan sesji (id ostatniej odpowiedzi, parametry wyszukiwania)
├── tests/
│   ├── mock_sse_backend.py # atrapa REST API silnika (uruchamiana lokalnie)
│   └── smoke_test.py       # test end-to-end wszystkich stron
├── app/
│   ├── locales/           # en.json, pl.json — teksty interfejsu
│   ├── templates/         # Jinja2: base, home, login, error, collections,
│   │                      #        manage_collection, document_preview,
│   │                      #        upload_documents, search
│   │   └── partials/      # search_params.html, table.html, messages.html, stepper.html, kb_header.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
```
