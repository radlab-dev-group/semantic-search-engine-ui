# Czat RAG dla pracownika – frontend dla `semantic-search-engine`

Minimalistyczny interfejs web, w którym pracownik zadaje pytania do firmowej bazy wiedzy
i dostaje odpowiedź z przypisami prowadzącymi do strony dokumentu.
Działa na istniejącym backendzie RadLab [`semantic-search-engine`](https://github.com/radlab-dev-group/semantic-search-engine)
(sprawdzone na kodzie z commita `58c0b8d`, 2026-10-30). Nie wymaga zmian w backendzie, żeby ruszyć.
Część funkcji działa w trybie przejściowym do czasu zmian opisanych w [docs/zgloszenia-do-radlab.md](docs/zgloszenia-do-radlab.md).

Wersja 0.1.0 · rola: pracownik (bez zarządzania kolekcjami) · tylko web na komputer · PL/EN · tryb jasny i ciemny.

## Co potrafi

- Logowanie lokalne albo kontem firmowym (Keycloak/OAuth przez backend).
- Wybór bazy wiedzy; nowy czat startuje z ostatnio używaną.
- Panel „Dokumenty”: lista dokumentów bazy, pola wyboru i „Zaznacz wszystko” – RAG szuka tylko w zaznaczonych.
- Czat z dopytywaniem; licznik czasu oczekiwania i „Przerwij”.
- Format odpowiedzi: Zwięźle / W punktach / Szczegółowo / Tabela, z „Pokaż inaczej”.
- Przypisy [n] przy zdaniach (na razie przybliżone), źródła pogrupowane po dokumencie, linia pokrycia.
- Podgląd tekstu dokumentu od strony przypisu, z podświetlonym cytatem i kolejnymi stronami.
- Ocena 👍/👎 z komentarzem, „Kopiuj”, „Kopiuj ze źródłami”.
- Historia rozmów i wznowienie rozmowy.
- Jawne komunikaty: brak źródeł w dokumentach, przekroczony czas, brak dostępu, wygasła sesja, usługa niedostępna.

## Szybki start

### Z atrapą backendu (bez RadLab)

```bash
docker compose up --build
```

Otwórz http://localhost:8000, zaloguj się dowolnym loginem i hasłem `demo`.
Pytanie z „licencja” pokazuje odpowiedź bez źródeł.

### Z prawdziwym backendem

```bash
cp configs/ui-configuration.example.json configs/ui-configuration.json   # i uzupełnij
docker build -t radlab-rag-ui .
docker run -p 8000:8000 \
  -e SSE_API_HOST=https://sse.example.org \
  -e SESSION_SECRET="$(openssl rand -base64 32)" \
  -e SESSION_HTTPS_ONLY=true \
  -v "$PWD/configs/ui-configuration.json:/srv/configs/ui-configuration.json:ro" \
  radlab-rag-ui
```

### Bez Dockera

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn mock_backend.server:app --port 8271 &          # tylko gdy nie ma backendu
SSE_API_HOST=http://localhost:8271 SESSION_SECRET=dev .venv/bin/uvicorn app.main:create_app --factory --port 8000
.venv/bin/pytest -q
```

## Konfiguracja

Plik `configs/ui-configuration.json` (ścieżkę zmienia `UI_CONFIG`). Format sekcji `api_hosts` jest zgodny
z `ui-configuration.json` obecnego UI RadLab. Wzór: [configs/ui-configuration.example.json](configs/ui-configuration.example.json).

| Sekcja / zmienna | Co ustawia |
|---|---|
| `api_hosts.semantic_search_engine.host` / `SSE_API_HOST` | adres backendu |
| `…prefix` / `SSE_API_PREFIX` | prefiks API (`api` albo `api/v1`) |
| `…ep` | nazwy endpointów, gdyby wdrożenie je zmieniło |
| `auth.mode` / `AUTH_MODE` | `local` (formularz) albo `sso` (tylko przycisk SSO); `auth.sso_button` dokłada przycisk SSO w trybie `local` |
| `SESSION_SECRET` | **wymagany w produkcji** – klucz podpisu ciasteczka sesji |
| `SESSION_HTTPS_ONLY` | `true` za HTTPS |
| `defaults.options` | opcje generowania wysyłane w każdym `new_chat` i `add_user_message`; `generative_model` pusty = pierwszy z `GET generative_models` |
| `defaults.search_options` | opcje wyszukiwania (liczba wyników, hybrid, reranking, próg podobieństwa) |
| `defaults.document_preview_pages` | ile stron pobiera podgląd dokumentu naraz |
| `citation_instruction` | polecenie dla modelu, żeby po zdaniach podawał nazwę dokumentu (podstawa przypisów przybliżonych) |
| `formats[]` | formaty odpowiedzi: etykiety PL/EN, `system_prompt`, `max_new_tokens`; `default_format` |
| `features.chat_sections` | sekcje w historii – zostaw `false` do czasu CR-16 i CR-05 |
| `timeouts` | GET 30 s, `add_user_message` 150 s |
| `ui.history_limit` | ile rozmów pokazać przed „Pokaż więcej” |

**SSO.** Przycisk woła `POST login_url` i przekierowuje do Keycloak. Adres powrotu, który trzeba ustawić
w kliencie Keycloak/backendzie: `https://<adres-frontendu>/login/callback`. Frontend wymienia `code` i `state`
na token przez `POST login` i odświeża go przez `POST refresh_token` po odpowiedzi 401.

## Jak to działa

Przeglądarka rozmawia tylko z serwerem frontendu (`/ui-api/*`). Serwer woła backend z tokenem z sesji,
więc backend nie potrzebuje CORS, a token nie trafia do kodu JavaScript (ciasteczko `HttpOnly`, podpisane).

### Mapa endpointów

| Element UI | Trasa frontendu | Endpoint backendu |
|---|---|---|
| Logowanie lokalne | `POST /login` | `POST login` (`username`, `password`) |
| Logowanie SSO | `GET /login/sso`, `GET /login/callback` | `POST login_url`, `POST login` (`code`, `state`, `session_state`), `POST refresh_token` |
| Wylogowanie | `POST /logout` | `POST logout` (tylko SSO) |
| Lista baz wiedzy | `GET /ui-api/collections` | `GET collections` |
| Panel „Dokumenty” | `GET /ui-api/documents` | `GET documents?collection_name=` |
| Pytanie / dopytanie | `POST /ui-api/ask` | `POST new_chat` (pierwsze pytanie), `POST add_user_message` |
| Zakres dokumentów | (w `ask`) | `search_options.documents` w `new_chat` i `add_user_message` (pomijane, gdy zaznaczone wszystkie) |
| Format odpowiedzi | (w `ask`) | `system_prompt` = `formats[].system_prompt` + `citation_instruction`; `options.max_new_tokens` |
| Model | (w `ask`) | `GET generative_models` (raz, gdy brak `generative_model` w konfiguracji) |
| Przypisy i źródła | (z `ask`) | `last_state[0].rag_message_state.sse_response.detailed_results_json` |
| Podgląd dokumentu | `GET /ui-api/document` | `GET document_content` (`from_page`, `max_pages`, `next_page`) |
| Ocena | `POST /ui-api/rate` | `POST rate_generative_answer` (`answer_response_id` = `sse_answer.id`, `rate_value` 0/1, `rate_value_max` 1) |
| Historia | `GET /ui-api/chats`, `GET /ui-api/chats/{id}` | `GET chats` |
| Baner „usługa niedostępna” | `GET /ui-api/health` | `GET healthz` |
| Kopiuj, kopiuj ze źródłami, motyw, język | – | tylko frontend (`lang` idzie w każdym wywołaniu) |

### Przypisy przybliżone (do CR-01)

Backend przekazuje modelowi fragmenty jako `{nazwa_dokumentu: [teksty]}`, bez numerów i stron.
Frontend prosi model (`citation_instruction`), żeby po zdaniu podawał w nawiasie kwadratowym nazwę dokumentu,
dopasowuje te nazwy do `detailed_results_json` ([app/core/answers.py](app/core/answers.py)) i jako stronę
przypisu bierze najlepiej ocenioną stronę fragmentu z tego dokumentu. Przypis ma przerywaną ramkę i opis
„strona może być przybliżona”. Gdy model nie poda nazw, pod odpowiedzią zostaje lista źródeł.

## Braki w API, które trzeba uzupełnić

Pełna lista z kryteriami akceptacji: [docs/zgloszenia-do-radlab.md](docs/zgloszenia-do-radlab.md) (sekcja „Braki w API”).

| Priorytet | Czego brakuje | CR |
|---|---|---|
| P0 | Historia rozmowy (pytania i odpowiedzi) przekazywana do modelu generującego odpowiedź RAG | CR-14 |
| P0 | Numerowane fragmenty i pole `citations[]` w odpowiedzi | CR-01 |
| P0 | `text_id`, `document_id`, `char_start/end` w wynikach; `document_content?text_id` | CR-02 |
| P1 | `answer_source` i opcja `rag_only` | CR-03 |
| P1 | `chats?with_sources=true` | CR-04 |
| P1 | W `chats`: `title`, `collection_name`, daty, paginacja; `rename_chat`, `delete_chat` | CR-05 |
| P1 | Sekcje i przypinanie: `chat_groups`, `move_chat`, `pin_chat` | CR-16 |
| P1 | Zakres dokumentów zapisany przy czacie | CR-18 |
| P1 | `system_prompt` łączony z promptem szablonu pytań, nie nadpisywany | CR-19 |
| P2 | `cancel_generation`, postęp / streaming | CR-06 |
| P2 | Data, typ i liczba stron w `documents` | CR-07 |

## Do sprawdzenia na prawdziwym backendzie

Frontend był testowany na atrapie ([mock_backend/server.py](mock_backend/server.py)), zbudowanej z kodu backendu.
Przy pierwszym uruchomieniu z RadLab sprawdźcie:

- [ ] Lokalny `POST login` przyjmuje JSON `{username, password}` i zwraca `{"token": …}`.
- [ ] Odpowiedź `POST login` z `code` (SSO) ma `token` i `refresh_token` w `body`.
- [ ] `rate_generative_answer` z `answer_response_id = last_state[0].rag_message_state.sse_answer.id` zapisuje ocenę.
- [ ] Model w wybranym routerze stosuje `citation_instruction` (nazwy dokumentów w nawiasach kwadratowych). Jeśli nie, dostosujcie tekst w konfiguracji.
- [ ] Kolekcje z szablonami pytań nie nadpisują `system_prompt` (CR-19). Do tego czasu w takich kolekcjach format i przypisy mogą nie działać.
- [ ] `search_options.documents` zawęża wyszukiwanie w ścieżce czatu (z kodu: `engine/controllers/search/semantic.py`, ok. l. 632).
- [ ] `GET documents` działa dla zwykłego pracownika w kolekcji udostępnionej jego grupie.
- [ ] Czas odpowiedzi mieści się w 150 s (inaczej zwiększcie `timeouts.add_user_message_s` i timeout proxy).

## Bezpieczeństwo i wdrożenie

- Sesja to podpisane ciasteczko `HttpOnly`, `SameSite=Lax`; za HTTPS ustawcie `SESSION_HTTPS_ONLY=true`.
- Odpowiedzi modelu są renderowane z Markdown z wyłączonym HTML, więc model nie wstrzyknie skryptu.
- Fonty (Inter, Newsreader – SIL OFL 1.1) są w repo; strona nie łączy się z zewnętrznymi serwerami.
- **Skalowanie:** źródła odpowiedzi i bazę rozmowy frontend trzyma w pamięci procesu (`app/core/session_store.py`),
  bo backend ich nie zwraca w historii (CR-04, CR-05). Uruchamiajcie jeden proces albo sticky sessions;
  przy kilku replikach podmieńcie `MemoryStore` na Redis (interfejs `SessionStore`).
- Proxy przed frontendem musi pozwolić na żądania do 150 s (`/ui-api/ask`).

## Struktura

```
app/
  main.py               – aplikacja FastAPI
  core/config.py        – konfiguracja (JSON + zmienne środowiskowe)
  core/api_client.py    – wywołania backendu, envelope, mapowanie błędów
  core/answers.py       – przypisy, grupowanie źródeł, Markdown
  core/session_store.py – pamięć źródeł i metadanych rozmów
  routes/               – logowanie, strona, /ui-api
  templates/, static/   – HTML, CSS (tokeny RadLab), JS, fonty
  locales/              – teksty PL i EN
mock_backend/           – atrapa semantic-search-engine
tests/                  – testy logiki przypisów i testy kontraktowe
docs/                   – zgłoszenia do RadLab, decyzje architektoniczne (ADR)
```

Klikalny prototyp z opisem przepływów: `projekt/prototyp/` w repozytorium projektu.
