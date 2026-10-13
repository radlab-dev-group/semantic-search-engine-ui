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
| `UI_SPEECH_INPUT` | `false` | dyktowanie głosem w czacie (Web Speech API), odpowiednik `STREAMLIT_SSL_CONNECTION`/`STREAMLIT_RUN_SERVER_LOCALHOST` |

Konfiguracja hostów/endpointów backendu to ten sam plik co w wersji Streamlit:
`configs/ui-configuration.json` (skopiowany z `streamlit_ui/configs/`).

## Mapowanie stron Streamlit → FastAPI

| Streamlit | Trasa FastAPI | Opis |
| --- | --- | --- |
| `Home.py` | `GET /home` | Strona główna z opisem projektu |
| `pages/0_Login.py` | `GET/POST /login`, `GET /logout` | Logowanie (token Django `Authorization: Token ...`) |
| `pages/1_New_Collection.py` | `GET/POST /collections/new` | Tworzenie kolekcji (embedder, reranker, typ indeksu) |
| `pages/2_Upload_Documents.py` | `GET/POST /documents/upload` | Upload `pdf/docx/txt/zip` + opcje indeksowania |
| `pages/3_Semantic_Search_Engine.py` | `GET/POST /search`, `POST /search/rate` | Wyszukiwanie + odpowiedź generatywna + ocenianie (gwiazdki) |
| `pages/4_Conversational_Search.py` | `GET /chat`, `POST /chat/message`, `POST /chat/clear` | Wyszukiwanie konwersacyjne (RAG, supervisorowie, stan RAG) |
| `pages/src/api.py` | `core/api.py` | Klient REST API (bez zależności od Streamlita) |
| `pages/src/config.py` (`SessionConfig`) | `server.py` (`get_token`, `get_username`, `clear_chat_session`) | Stan sesji użytkownika |
| `pages/src/constants.py` | `core/constants.py` | Stałe, wartości domyślne formularzy |
| `pages/src/ui_utils.py` | `server.py` (`fetch_*`, `parse_search_form`, `prepare_*_dataframe`) | Przygotowanie danych do widoków |
| `pages/src/env_utils.py` | `core/env_utils.py` | Parsowanie flag z otoczenia |

Dodatkowo (poza oryginałem):

- `GET /api/options?collection_name=...` — JSON z kategoriami i dokumentami
  kolekcji; używany przez `app/static/js/app.js` do odświeżania filtrów po zmianie
  kolekcji (zastępuje automatyczny rerun Streamlita). Filtry (kategorie i
  dokumenty) są — tak jak w oryginale — na stronie wyszukiwania i na stronie czatu.
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
- Strona `4_Conversational_Search.py` jest w Streamlicie wyłączana przez
  przezwisko pliku (`.py_`); tutaj jest zawsze dostępna pod `/chat`.
  `st.chat_input` zastępuje pole tekstowe, a `streamlit_mic_recorder` — przycisk
  „🎤 Dictate” oparty o Web Speech API (język `pl`), włączany flagą
  `UI_SPEECH_INPUT`; przeglądarki wymagają HTTPS albo `localhost`.
- Ocena odpowiedzi (zamiast `st-star-rating`) to suwak 1-5 gwiazdek.
- Tabele wyników (`pandas`) są renderowane jako HTML — sortowanie
  `score_weighted` / `score` bez zmian.

## Wygląd (UI)

Nowoczesny, responsywny interfejs bez zewnętrznych zależności (żadnych CDN-ów ani
fontów z sieci — działa offline, ikony są w inline SVG).

- **Motyw jasny/ciemny**: wartość `auto` podąża za `prefers-color-scheme`, a
  przycisk w pasku nawigacji przełącza `auto → light → dark`; wybór zapisywany
  jest w `localStorage` pod kluczem `sse-theme` (ustawiany przed pierwszym
  malowaniem, więc brak „flasha” przy wczytywaniu).
- **Tokeny designu** w `:root` (kolory, cienie, radiusy, odstępy) w
  `app/static/css/style.css` — naklejenie innego brandu to zmiana
  kilku zmiennych.
- **Responsywność**: breakpointy 1080 px (siatka paneli), 980 px (nawigacja w
  hamburger), 860 px (jedna kolumna), 560 px (stackowanie pól i suwaków).
- **Dostępność**: link „Skip to content”, widoczne ramki fokusu, `aria-*` przy
  przełącznikach i nawigacji, respektowane `prefers-reduced-motion`, styl do
  druku.
- **UX**: zakładki wyników jako segmentowany kontroler, sticky-header tabel,
  rozwijane sekcje (JSON, opcje generacji, stan supervisora), pasek postępu
  uploadu, spinner na przyciskach formularzy, podświetlanie aktywnej pozycji w
  nawigacji, `Ctrl/Cmd + Enter` wysyła wiadomość w czacie, a filtry kategorii i
  dokumentów odświeżają się bez przeładowania po zmianie kolekcji.

## Testy

Smoke test odpala aplikację FastAPI wraz z **mockowanym backendem SSE**
(`tests/mock_sse_backend.py` odwzorowuje kształty odpowiedzi
`radlab-semantic-search-engine`), przechodzi całą ścieżkę: logowanie, tworzenie
kolekcji, upload plików, wyszukiwanie z odpowiedzią generatywną, ocenianie,
czat RAG i wylogowanie. Nie wymaga prawdziwego backendu ani bazy wektorów.

```bash
cd fastapi_ui
.venv/bin/pip install httpx            # zależność testowa
.venv/bin/python tests/smoke_test.py   # 53 checki, wyjście != 0 przy porażce
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
│   ├── env_utils.py
│   └── state_store.py     # stan sesji (czat, stan RAG) — odpowiednik st.session_state
├── tests/
│   ├── mock_sse_backend.py # atrapa REST API silnika (uruchamiana lokalnie)
│   └── smoke_test.py       # test end-to-end wszystkich stron
├── app/
│   ├── templates/         # Jinja2: base, home, login, error, new_collection,
│   │   │                  #        upload_documents, search, chat
│   │   └── partials/      # search_params.html, table.html, messages.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
```
