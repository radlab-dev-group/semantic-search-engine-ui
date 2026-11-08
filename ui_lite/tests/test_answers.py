from app.core.answers import Fragment, build_answer, extract_results

A = "Annual report 2025.pdf"
B = "Security policy.docx"


def frags():
    return [
        Fragment(B, 3, "Passwords change every 90 days.", "", "", 0.9),
        Fragment(A, 12, "Revenue grew by 8%.", "", "", 0.8),
        Fragment(A, 14, "Costs fell.", "", "", 0.5),
    ]


def test_footnotes_numbered_in_order_of_first_citation():
    out = build_answer(f"Revenue grew [{A}]. Passwords change often [{B}].", frags())
    assert [g["name"] for g in out["groups"]] == [A, B]
    assert 'data-fn="1"' in out["html"] and 'data-fn="2"' in out["html"]
    assert out["plain"] == "Revenue grew[1]. Passwords change often[2]."
    assert out["cited"] is True


def test_footnote_page_is_best_scored_fragment_and_pages_listed():
    out = build_answer(f"Result [{A}].", frags())
    a = out["groups"][0]
    assert a["page"] == 12 and a["pages"] == [12, 14] and a["quote"] == "Revenue grew by 8%."


def test_name_without_extension_and_case_matches():
    out = build_answer("Result [annual report 2025].", frags())
    assert 'data-fn="1"' in out["html"]


def test_unmatched_brackets_are_kept_and_uncited_documents_listed():
    out = build_answer("See [section 3] and [unknown file.pdf].", frags())
    assert "[section 3]" in out["plain"] and "[unknown file.pdf]" in out["plain"]
    assert out["cited"] is False
    assert [g["name"] for g in out["groups"]] == [B, A]  # relevance order


def test_several_names_in_one_bracket():
    out = build_answer(f"Both documents [{A}; {B}].", frags())
    assert out["plain"].endswith("[1][2].")


def test_raw_html_from_model_is_escaped_and_tables_render():
    out = build_answer(f"<script>alert(1)</script>\n\n| a | b |\n|---|---|\n| x | y [{A}] |", frags())
    assert "<script>" not in out["html"] and "&lt;script&gt;" in out["html"]
    assert "<table>" in out["html"] and 'class="fn approx"' in out["html"]


def test_extract_results_accepts_dict_of_index_and_reads_answer_id():
    body = {"last_state": [{"rag_message_state": {
        "sse_response": {"detailed_results_json": {"0": {"document_name": A, "page_number": 2, "text_str": "x", "score_normalized": 0.5}}},
        "sse_answer": {"id": 77},
    }}]}
    fragments, answer_id, ran = extract_results(body)
    assert len(fragments) == 1 and fragments[0].page == 2 and answer_id == 77 and ran


def test_extract_results_without_rag_state():
    assert extract_results({"last_state": None}) == ([], None, False)
