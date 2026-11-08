# ADR 0003 – Źródła odpowiedzi w pamięci frontendu do czasu CR-04 i CR-05

Data: 2026-11-01 · Status: przyjęta

**Kontekst.** `GET chats` zwraca wiadomości bez źródeł i bez kolekcji czatu.

**Decyzja.** Po każdej odpowiedzi frontend zapisuje jej źródła oraz bazę i zakres dokumentów rozmowy
w pamięci procesu (`MemoryStore`), w obrębie sesji użytkownika. Po wygaśnięciu sesji pokazuje komunikat
„Źródła i przypisy nie są dostępne” z przyciskiem „Zapytaj ponownie”.

**Konsekwencje.** Jeden proces frontendu albo sticky sessions; dla wielu replik – Redis za interfejsem `SessionStore`.
Po CR-04 i CR-05 pamięć staje się zbędna.
