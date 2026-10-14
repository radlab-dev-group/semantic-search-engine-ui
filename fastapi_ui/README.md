# Semantic Search Engine UI — FastAPI + Jinja2

Bliźniacza (twin) aplikacja dla `streamlit_ui/` zbudowana na **FastAPI + Jinja2**.
Wszystkie funkcjonalności, końcówki API i zachowania UI odpowiadają wersji
Streamlit — zmieniona jest tylko warstwa prezentacji (szablony HTML zamiast
komponentów Streamlita) oraz sposób utrzymywania stanu (sesja w ciasteczku
zamiast `st.session_state`).

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
| `UI_MAX_UPLOAD_SIZE_MB` | `6000` | limit rozmiaru pojedynczego pliku przy uploadzie, odpowiednik `STREAMLIT_SERVER_MAX_UPLOAD_SIZE` |
| `UI_MAX_UPLOAD_FILES` | `500` | maksymalna liczba plików w jednym żądaniu uploadu |
| `UI_DEFAULT_LANGUAGE` | `en` | język interfejsu (`en` / `pl`), gdy użytkownik go nie wybrał, a przeglądarka nie podaje obsługiwanego języka |

Konfiguracja hostów/endpointów backendu to ten sam plik co w wersji Streamlit:
`configs/ui-configuration.json` (skopiowany z `streamlit_ui/configs/`).

## Mapowanie stron Streamlit → FastAPI

| Streamlit | Trasa FastAPI | Opis |
| --- | --- | --- |
| `Home.py` | `GET /home` | Strona główna z opisem projektu |
| `pages/0_Login.py` | `GET/POST /login`, `GET /logout` | Logowanie (token Django `Authorization: Token ...`) |
| `pages/1_New_Collection.py` | `GET /collections`, `POST /collections/new` | **Lista kolekcji** (`GET api/collections`, odpowiednik `SSEClient.list_collections()`) + tworzenie kolekcji (embedder, reranker, typ indeksu) |
| `pages/2_Upload_Documents.py` | `GET/POST /documents/upload` | Upload `pdf/docx/txt/html/md/zip` + opcje indeksowania |
| `pages/3_Semantic_Search_Engine.py` | `GET/POST /search`, `POST /search/generate`, `POST /search/rate` | Wyszukiwanie + odpowiedź generatywna (doczytywana po wynikach) + ocenianie (gwiazdki) |
| `pages/4_Conversational_Search.py` | — | **Wycofane**: zakładka Chat nie istnieje w tej aplikacji |
| `pages/src/api.py` | `core/api.py` | Klient REST API (bez zależności od Streamlita) |
| `pages/src/config.py` (`SessionConfig`) | `server.py` (`get_token`, `get_username`, `clear_session_state`) | Stan sesji użytkownika |
| `pages/src/constants.py` | `core/constants.py` | Stałe, wartości domyślne formularzy |
| `pages/src/ui_utils.py` | `server.py` (`fetch_*`, `parse_search_form`, `prepare_*_dataframe`) | Przygotowanie danych do widoków |

Dodatkowo (poza oryginałem):

- `GET /api/options?collection_name=...` — JSON z kategoriami i dokumentami
  kolekcji; używany przez `app/static/js/app.js` do odświeżania filtrów po zmianie
  kolekcji (zastępuje automatyczny rerun Streamlita). Filtry (kategorie i
  dokumenty) są — tak jak w oryginale — na stronie wyszukiwania.
- `GET /lang/{pl|en}?next=/sciezka` — przełącza język interfejsu (ciasteczko
  `sse_lang`, rok ważności) i wraca na stronę `next` (tylko ścieżki lokalne).
- `POST /search/generate` (`generation_id`) — odpowiedź generatywna dla
  wyszukiwania, którego wyniki są już na stronie. `POST /search` nie czeka na
  model: od razu renderuje wyniki i kartę „Odpowiedź modelu” w stanie
  oczekiwania, a parametry generowania (`query_response_id`, prompt, opcje)
  odkłada w stanie sesji pod jednorazowym `generation_id`. `app.js` wywołuje ten
  endpoint i podmienia kartę na odpowiedź (JSON: `answer_html` +
  `feedback_html`, czyli formularz oceny). Nieznany/zużyty `generation_id` → 409.
- `GET /healthz` — endpoint kontrolny (health check).
- `GET /docs` — wbudowana dokumentacja OpenAPI.

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

Kody błędów są renderowane na stronie `error.html`, odpowiednik
`show_error_status()` z `streamlit_ui/pages/src/ui_utils.py`.

## Różnice względem wersji Streamlit

- Extractive QA pozostaje opcją w formularzu, ale — tak jak w oryginale —
  wywołanie jest zakomentowane po stronie UI i odpowiada za nie backend.
- W wersji Streamlit wybór języka tłumaczenia odpowiedzi był martwym kodem
  (`translate_output = False`); w FastAPI suwak/zaznaczenie „Translate generated
  answer” jest w pełni funkcjonalne i wysyła `translate_answer` + `answer_language`.
- Zakładka **Chat** (`pages/4_Conversational_Search.py`) została usunięta z tej
  aplikacji: nie ma tras `/chat*`, ani powiązane z nimi opcje
  (dyktowanie głosem `UI_SPEECH_INPUT`, stan RAG/supervisorów w sesji).
  Wersja Streamlit nadal ją zawiera pod `streamlit_ui/`.
- Ocena odpowiedzi (zamiast `st-star-rating`) to wybór 1-5 gwiazdek (radio).
- Tabele wyników (`pandas`) są renderowane jako HTML — sortowanie
  `score_weighted` / `score` bez zmian.

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
  w nagłówku stron kolekcji, uploadu i wyszukiwania.
- **Kolekcje** jako karty (nazwa, opis, data, akcje Upload/Search).
- **Upload**: strefa drag & drop dla plików oraz podgląd chunkowania, który na
  żywo pokazuje stosunek `overlap` do rozmiaru chunka.
- **Wyszukiwanie**: wyróżniona „konsola zapytania”, przykładowe pytania jako
  klikalne chipy, panel parametrów w przyklejonym (sticky) sidebarze, karta
  odpowiedzi modelu z gradientowym akcentem nad wynikami, ocena odpowiedzi
  gwiazdkami. Przy generatywnym QA wyniki pokazują się od razu, a karta
  odpowiedzi ma animowany szkielet i licznik czasu, dopóki model nie skończy.
- **Wyniki („What the engine found”)**: zamiast szerokiej tabeli każdy
  fragment to karta (`partials/hits.html`) z pozycją w rankingu, dokumentem,
  stroną/chunkiem/językiem, skorem i paskiem względem najlepszego trafienia
  oraz tekstem fragmentu z podświetlonymi słowami pytania (dopasowanie po
  rdzeniu, więc łapie też odmiany). Długie fragmenty można rozwinąć, skopiować,
  a pozostałe pola są w „more field(s)”. Chipy nad listą filtrują fragmenty po
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
nieprzetłumaczonych kluczy na stronach), wylogowanie. Nie wymaga prawdziwego
backendu ani bazy wektorów.

```bash
cd fastapi_ui
.venv/bin/pip install httpx            # zależność testowa
.venv/bin/python tests/smoke_test.py   # 77 checków, wyjście != 0 przy porażce
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
│   ├── api.py             # klient REST API SSE (port streamlit_ui/pages/src/api.py)
│   ├── constants.py
│   ├── i18n.py            # tłumaczenia interfejsu (pl / en), wybór języka
│   └── state_store.py     # stan sesji (id ostatniej odpowiedzi) — odpowiednik st.session_state
├── tests/
│   ├── mock_sse_backend.py # atrapa REST API silnika (uruchamiana lokalnie)
│   └── smoke_test.py       # test end-to-end wszystkich stron
├── app/
│   ├── locales/           # en.json, pl.json — teksty interfejsu
│   ├── templates/         # Jinja2: base, home, login, error, collections,
│   │   │                  #        upload_documents, search
│   │   └── partials/      # search_params.html, table.html, messages.html, stepper.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
```
