# ADR 0002 – Przypisy przybliżone do czasu CR-01 i CR-02

Data: 2026-11-01 · Status: przyjęta

**Kontekst.** Przypisy z odesłaniem do strony dokumentu są wymaganiem „must have”. Backend nie numeruje fragmentów
w prompcie i nie zwraca, które fragmenty model wykorzystał.

**Decyzja.** Frontend dokłada do `system_prompt` polecenie podawania nazwy dokumentu w nawiasie kwadratowym,
dopasowuje nazwy do `detailed_results_json` i wskazuje najlepiej ocenioną stronę dokumentu. Przypis jest oznaczony
jako przybliżony (przerywana ramka i opis pod źródłami).

**Konsekwencje.** Dokument w przypisie jest pewny, strona – przybliżona. Po CR-01/CR-02 frontend przełączy się
na pole `citations[]` i dokładne podświetlenie bez zmian w wyglądzie poza ramką przypisu.
