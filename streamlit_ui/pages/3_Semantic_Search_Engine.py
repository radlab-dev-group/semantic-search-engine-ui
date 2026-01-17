import os
import logging
import pandas as pd
import streamlit as st
from streamlit_star_rating import st_star_rating

import datetime

from pages.src.ui_utils import (
    prepare_collection_to_choose,
    prepare_search_params,
    show_error_status,
    prepare_generative_qa_results,
)
from pages.src.constants import (
    session_config,
    sse_api_engine,
    MAX_VAL_RATING_GENERATIVE_ANSWER,
)


def home():
    st.set_page_config(
        page_title="Semantic search engine",
        page_icon="🧊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("SSE with generative response")

    questions_container = st.container(border=True)
    questions_container.write("<b>Przykładowe pytania:</b>", unsafe_allow_html=True)
    questions_container.write("Sample question.....")
    questions_container.write("Sample question.....")
    questions_container.write("Sample question.....")

    if "answer_state" not in st.session_state:
        st.session_state["answer_state"] = False

    if "rate_state" not in st.session_state:
        st.session_state["rate_state"] = False

    if "stars_count" not in st.session_state:
        st.session_state["stars_count"] = 0

    if "last_query_response_id" not in st.session_state:
        st.session_state["last_query_response_id"] = None


def set_after_rate_state():
    st.session_state["rate_state"] = True
    st.session_state["answer_state"] = True


def set_after_run_state():
    st.session_state["rate_state"] = True
    st.session_state["answer_state"] = False


def rate_generated_answer(max_value: int = 5, default_value: int = 5):
    form = st.form("generative_answer_rating_form", border=True)
    star_rate_col, answer_rate_col = form.columns([1, 4])
    with star_rate_col:
        st.write("Set the number of stars")
        stars = st_star_rating(
            label="",
            maxValue=max_value,
            defaultValue=default_value,
            key="rating",
            dark_theme=True,
            size=30,
        )
        btn = st.form_submit_button(
            "Send your feedback!", on_click=set_after_rate_state
        )

    with answer_rate_col:
        comment = st.text_area("Please leave your comment")

    return btn, stars, comment


def prepare_search_form():
    form = st.form("search_form")
    question_str, question_prompt = form.columns(2)
    question = question_str.text_area("Enter a sentence to search", value="")
    prompt = question_prompt.text_area("Enter an instruction to search", value="")
    btn = form.form_submit_button("Run", on_click=set_after_run_state)
    return question, prompt, btn


def visualise_search_results(
    results, qa_results, qa_gen_results, qa_gen_results_time
):
    results_container = st.container(border=True)
    ss_tab, sr_tab, a_tab, gen_tab = results_container.tabs(
        [
            "Search statistics",
            "Search results",
            "Answers (extractive QA)",
            "Answers (generative QA)",
        ]
    )

    if "results" in results["body"]:
        # Show general stats (question - document relevance)
        if "stats" in results["body"]["results"]:
            stats_pd = pd.DataFrame.transpose(
                pd.DataFrame.from_dict(results["body"]["results"]["stats"])
            ).sort_values("score_weighted", ascending=False)
            ss_tab.write(stats_pd)

        # Show specific search results
        if "detailed_results" in results["body"]["results"]:
            search_results_pd = pd.DataFrame.transpose(
                pd.DataFrame(results["body"]["results"]["detailed_results"])
            ).sort_values("score", ascending=False)
            sr_tab.write(search_results_pd)

    # Extractive wa results
    if qa_results and len(qa_results):
        a_tab.write(
            pd.DataFrame.transpose(pd.DataFrame.from_dict(qa_results)).sort_values(
                "score", ascending=False
            )
        )

    # Generative QA answer
    if qa_gen_results and len(qa_gen_results):
        gen_tab.write(f"Generation time: {qa_gen_results_time}")

        gen_tab.divider()
        gen_tab.write(qa_gen_results.get("answer", ""))

        gen_tab.divider()

        gen_tab_exp = gen_tab.expander(label="Show json", expanded=False)
        gen_tab_exp.write(qa_gen_results)


#
# def prepare_extractive_qa_results(
#     question: str, answers: dict, model_path: str = "radlab/polish-qa-v2"
# ) -> dict:
#     # Load model when is not in cache
#     if model_path not in st.session_state["CACHED_CONTROLLERS"]:
#         st.session_state["CACHED_CONTROLLERS"][model_path] = ExtractiveQAController(
#             model_path, device="cuda"
#         )
#     ex_qa_controller = st.session_state["CACHED_CONTROLLERS"][model_path]
#     return ex_qa_controller.run_extractive_qa(
#         question_str=question, search_results=answers
#     )

# def display_pdf_file(file_path, page_number, display_column=None):
#     with open(file_path, "rb") as f:
#         base64_pdf = base64.b64encode(f.read()).decode("utf-8")
#
#     # Embedding PDF in HTML
#     pdf_display = f"""
#         <iframe src="data:application/pdf;base64,
#         {base64_pdf}#page={page_number}" width="700" height="950"
#         type="application/pdf"></iframe>
#         """
#     # pdf_display = f"""<embed
#     #     class="pdfobject"
#     #     type="application/pdf"
#     #     title="Embedded PDF"
#     #     src="data:application/pdf;base64,{base64_pdf}#page={page_number};"
#     #     style="overflow: auto; width: 100%; height: 950px;">"""
#
#     # Displaying File
#     if display_column is not None:
#         display_column.markdown(pdf_display, unsafe_allow_html=True)


def main():
    if session_config.get_session_token() is None:
        st.switch_page("pages/0_Login.py")
    home()

    collection_of_documents = prepare_collection_to_choose(
        token=session_config.get_session_token()
    )
    if collection_of_documents is None:
        return

    search_options, answer_options, run_models_options = prepare_search_params(
        collection_name=collection_of_documents,
        show_content_supervisor=False,
        show_rag_supervisor=False,
    )
    question_str, question_prompt, search_button = prepare_search_form()
    # use_qa_generative
    if (
        st.session_state["answer_state"] is False
        or st.session_state["rate_state"] is False
    ):
        if not search_button or not question_str or not len(question_str.strip()):
            return

        with st.spinner("Loading"):
            results = sse_api_engine.search_answer_with_options(
                token=session_config.get_session_token(),
                collection_name=collection_of_documents,
                question=question_str,
                options=search_options,
            )
            if results["status"] is False:
                return show_error_status(results)

            if "body" not in results or "results" not in results["body"]:
                return

            if len(results["body"]["results"]):
                qa_results = {}
                if run_models_options["use_qa_extractive"]:
                    # qa_results = prepare_extractive_qa_results(question_str, results)
                    pass

                qa_gen_results = []
                qa_gen_results_time = 0
                if run_models_options["use_qa_generative"]:
                    qa_gen_results = prepare_generative_qa_results(
                        results=results,
                        question_prompt=question_prompt,
                        generate_options=answer_options,
                        logging=logging,
                    )
                    qa_gen_results_time = datetime.timedelta(
                        seconds=float(qa_gen_results["generation_time"])
                    )
                visualise_search_results(
                    results, qa_results, qa_gen_results, qa_gen_results_time
                )
                st.session_state["answer_state"] = True
            else:
                st.warning("No results found!")
                return

    if st.session_state["answer_state"] is True:
        if st.session_state["last_query_response_id"] is None:
            st.session_state["answer_state"] = False
            return

        if run_models_options["use_qa_generative"] is False:
            st.session_state["answer_state"] = False
            return

        rate_btn, stars_count, rate_comment = rate_generated_answer(
            max_value=MAX_VAL_RATING_GENERATIVE_ANSWER
        )
        if rate_btn:
            last_query_response_id = st.session_state["last_query_response_id"]

            sse_api_engine.set_rating_for_generative_answer(
                token=session_config.get_session_token(),
                answer_response_id=last_query_response_id,
                rate_value=stars_count,
                rate_value_max=MAX_VAL_RATING_GENERATIVE_ANSWER,
                rate_comment=rate_comment,
            )
            logging.info(
                f"Starring with {stars_count} for response {last_query_response_id}"
            )
            st.session_state["rate_state"] = False
            st.session_state["answer_state"] = False
            st.session_state["last_query_response_id"] = None
            st.rerun()


if __name__ == "__main__":
    main()
