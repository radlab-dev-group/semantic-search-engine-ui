import json
import os
import streamlit as st

from pages.src.constants import session_config, sse_api_engine


def prepare_collection_to_choose(token: str):
    result = sse_api_engine.list_user_collections(token=token)
    if "status" in result and not result["status"]:
        return show_error_status(result)

    st.sidebar.title("Semantic search engine")
    search_container = st.sidebar.container(border=True)

    collections = [c["name"] for c in result["body"]["collections"]]
    if collections is None or not len(collections):
        st.warning(
            "You do not have any collections of documents. "
            "Go to the 'New Collection' and create a new collection."
        )
        st.page_link(
            "pages/1_New_Collection.py",
            label="Click here to New collection",
            icon="🆕",
        )
        return None

    session_config.set_available_collections(collections)

    collection_name = search_container.selectbox(
        "Collection name",
        collections,
        index=None,
        placeholder="Choose collection...",
    )
    st.write(f"You selected collection {collection_name}")
    return collection_name


def set_on_change_state():
    st.session_state["chat"] = []
    st.session_state["answer_state"] = False
    st.session_state["general_stats"] = None
    st.session_state["detected_question_str"] = None


def prepare_search_params(
    collection_name: str,
    force_generative: bool = False,
    show_content_supervisor: bool = False,
    show_rag_supervisor: bool = False,
    default_max_new_tokens: int = 1024,
):
    st.sidebar.title("Semantic search engine")

    search_container = st.sidebar.container(border=True)
    search_container.write("Search parameters")

    results_count = search_container.number_input(
        "Number of results",
        value=25,
        min_value=1,
        max_value=100,
        on_change=set_on_change_state,
    )

    use_content_supervisor = False
    if show_content_supervisor:
        use_content_supervisor = search_container.toggle(
            "Content supervisor", value=False, on_change=set_on_change_state
        )

    use_rag_supervisor = True
    if show_rag_supervisor:
        use_rag_supervisor = search_container.toggle(
            "RAG supervisor", value=True, on_change=set_on_change_state
        )

    rerank_results = search_container.toggle(
        "Rerank results", value=False, on_change=set_on_change_state
    )

    return_with_factored_fields = False
    if not force_generative:
        return_with_factored_fields = search_container.toggle(
            "Results count with factored number of results",
            value=False,
            on_change=set_on_change_state,
        )

    use_qa_extractive = False
    if not force_generative:
        use_qa_extractive = search_container.toggle(
            "Run Extractive QA", value=False, on_change=set_on_change_state
        )

    generative_models = sse_api_engine.list_generative_models(
        token=session_config.get_session_token()
    )

    if not generative_models["status"]:
        st.error("Generative models cannot be retrieved!")
        st.write(generative_models)
    else:
        generative_models = generative_models["body"]["models"]

    use_gen_qa = True
    if not force_generative:
        use_gen_qa = search_container.toggle(
            "Run Generative QA", value=False, on_change=set_on_change_state
        )

    if use_gen_qa:
        use_doc_names_in_response = search_container.toggle(
            "Document names in answer", value=False, on_change=set_on_change_state
        )

        qa_gen_model = search_container.selectbox(
            "Model for results summarization",
            generative_models,
            0,
            on_change=set_on_change_state,
        )

        perc_rank_to_gen_qa = search_container.number_input(
            "Percentage rank to generative QA",
            value=40,
            min_value=1,
            max_value=100,
            on_change=set_on_change_state,
        )

        translate_output = False
        if "openai" not in qa_gen_model.lower():
            translate_output = search_container.toggle(
                "Translate answer", value=False, on_change=set_on_change_state
            )

        lang_options = None
        if translate_output:
            lang_options = search_container.selectbox(
                f"Generated answer target language",
                ["pl", "en-us", "en-gb", "de", "cs"],
                0,
                on_change=set_on_change_state,
            )

        gen_model_opt_expander = search_container.expander("Generation options")
        top_k = gen_model_opt_expander.slider(
            "top_k",
            value=50,
            max_value=500,
            min_value=0,
            step=1,
            on_change=set_on_change_state,
        )
        top_p = gen_model_opt_expander.slider(
            "top_p",
            value=0.95,
            max_value=1.0,
            min_value=0.0,
            step=0.01,
            on_change=set_on_change_state,
        )
        temperature = gen_model_opt_expander.slider(
            "temperature",
            value=0.65,
            max_value=2.0,
            min_value=0.0,
            step=0.01,
            on_change=set_on_change_state,
        )
        typical_p = gen_model_opt_expander.slider(
            "typical_p",
            value=1.0,
            max_value=2.0,
            min_value=0.0,
            step=0.01,
            on_change=set_on_change_state,
        )
        repetition_penalty = gen_model_opt_expander.slider(
            "repetition_penalty",
            value=1.1,
            max_value=2.0,
            min_value=0.0,
            step=0.01,
            on_change=set_on_change_state,
        )
        set_max_new_tokens = gen_model_opt_expander.toggle(
            "Set max new tokens", value=False, on_change=set_on_change_state
        )

        max_new_tokens = default_max_new_tokens
        if set_max_new_tokens:
            max_new_tokens = gen_model_opt_expander.slider(
                "max_new_tokens",
                value=default_max_new_tokens,
                max_value=4000,
                min_value=10,
                step=1,
                on_change=set_on_change_state,
            )
    else:
        top_k, top_p, temperature, typical_p, repetition_penalty, max_new_tokens = [
            None,
            None,
            None,
            None,
            None,
            None,
        ]

        use_doc_names_in_response = False
        qa_gen_model = ""
        perc_rank_to_gen_qa = 0
        lang_options = ""
        translate_output = ""

    categories = sse_api_engine.list_categories_from_collection(
        token=session_config.get_session_token(), collection_name=collection_name
    )
    if categories["status"] is False:
        return show_error_status(categories)

    if (
        "body" not in categories
        or "categories" not in categories["body"]
        or not len(categories["body"]["categories"])
    ):
        categories = []
    else:
        categories = sorted(
            c for c in categories["body"]["categories"] if c is not None and len(c)
        )

    cat_doc_container = st.container(border=True)
    cat_column, doc_column = cat_doc_container.columns(2)
    cat_options = cat_column.multiselect(
        f"Select categories to search (number of categories in "
        f"collection {len(categories)})",
        categories,
        [],
    )

    documents_names = sse_api_engine.list_documents_from_collection(
        token=session_config.get_session_token(), collection_name=collection_name
    )
    if documents_names["status"] is False:
        return show_error_status(documents_names)
    documents_names = sorted(
        c["name"] for c in documents_names["body"]["documents"] if len(c["name"])
    )

    doc_options = doc_column.multiselect(
        f"Select documents to search (number of documents in "
        f"collection {len(documents_names)})",
        documents_names,
        [],
    )

    search_options = {
        "categories": cat_options,
        "documents": doc_options,
        "max_results": results_count,
        "rerank_results": rerank_results,
        "return_with_factored_fields": return_with_factored_fields,
    }
    run_models_options = {
        "use_qa_extractive": use_qa_extractive,
        "use_qa_generative": use_gen_qa,
    }
    answer_options = {
        "use_qa_extractive": use_qa_extractive,
        "use_qa_generative": use_gen_qa,
        "generative_model": qa_gen_model,
        "percentage_rank_mass": perc_rank_to_gen_qa,
        "answer_language": lang_options,
        "translate_answer": translate_output,
        "use_doc_names_in_response": use_doc_names_in_response,
        "top_k": top_k,
        "top_p": top_p,
        "temperature": temperature,
        "typical_p": typical_p,
        "repetition_penalty": repetition_penalty,
        "use_content_supervisor": use_content_supervisor,
        "use_rag_supervisor": use_rag_supervisor,
    }
    if max_new_tokens is not None:
        answer_options["max_new_tokens"] = max_new_tokens

    return search_options, answer_options, run_models_options


def prepare_generative_qa_results(
    results: dict, question_prompt: str, generate_options: dict, logging
) -> (list | dict | None, float | None):
    query_response_id = results["body"]["query_response_id"]
    qa_gen_model = generate_options["generative_model"]

    logging.info(
        f"Generative answer for {query_response_id} query response "
        f"will be generated using {qa_gen_model} model."
    )

    results = sse_api_engine.generative_answer_from_results(
        token=session_config.get_session_token(),
        query_response_id=query_response_id,
        query_prompt=question_prompt,
        query_options=generate_options,
    )

    if not results["status"]:
        return show_error_status(results)

    st.session_state["last_query_response_id"] = results["body"]["response_id"]
    return results["body"]


def show_error_status(result):
    st.error(f"Error occurred while processing")
    for err in result["errors"]:
        if "required_params" in err and len(err["required_params"]):
            st.write(err)
