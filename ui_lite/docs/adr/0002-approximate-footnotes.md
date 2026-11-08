# ADR 0002 – Approximate footnotes until CR-01 and CR-02

Date: 2026-11-01 · Status: accepted

**Context.** Footnotes linking to a document page are a "must have" requirement. The backend does not number the fragments
in the prompt and does not return which fragments the model used.

**Decision.** The frontend appends an instruction to `system_prompt` to put the document name in square brackets,
matches the names against `detailed_results_json`, and points to the best-scoring document page. The footnote is marked
as approximate (dashed border and a note under the sources).

**Consequences.** The document in a footnote is certain, the page – approximate. After CR-01/CR-02 the frontend will switch
to the `citations[]` field and exact highlighting, with no visual change beyond the footnote border.
