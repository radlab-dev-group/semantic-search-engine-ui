import json
import streamlit as st

from pages.src.ui_utils import show_error_status
from pages.src.constants import session_config, sse_api_engine


def home():
    st.set_page_config(
        page_title="SSE - new collection",
        page_icon="🧊",
        layout="centered",
        initial_sidebar_state="expanded",
    )
    st.title("Add new collection to SSE")


def prepare_new_collection():
    form = st.sidebar.form("new_collection")
    form.write("Create new collection")
    btn = form.form_submit_button("Add")
    return btn


def show_new_collection_window(embedders: list, rerankers: list):
    form = st.form("new_collection_properties")
    container = form.container(border=True)
    collection_name = container.text_input("Collection code name", value="")
    collection_display_name = container.text_input(
        "Collection display name", value=""
    )

    collection_index = container.selectbox("Index type", ("IVF_FLAT", "HNSW"))
    embedder_model = container.selectbox(
        "Name of embedder model", embedders, index=0
    )
    re_ranker_model = container.selectbox(
        "Name of re-ranker model", rerankers, index=0
    )

    collection_desc = container.text_area("Collection description", value="")
    btn_create = form.form_submit_button("Create")

    if not len(collection_desc):
        collection_desc = f"Opis kolekcji {collection_display_name}"

    collection_property = {
        "collection_name": collection_name,
        "collection_display_name": collection_display_name,
        "embedder_index_type": collection_index,
        "collection_description": collection_desc,
        "model_reranker": re_ranker_model,
        "model_embedder": embedder_model,
    }

    return btn_create, collection_property


def proper_collection_name(orig_col_name: str, username_str: str):
    orig_col_name = (
        orig_col_name.replace(" ", "_")
        .replace("'", "")
        .replace('"', "")
        .replace(".", "_")
        .replace("\t", "_")
    )
    username_str = (
        username_str.replace(" ", "_")
        .replace("'", "")
        .replace('"', "")
        .replace(".", "_")
        .replace("\t", "_")
    )
    return f"{username_str}_{orig_col_name}"


def main():
    if session_config.get_session_token() is None:
        st.switch_page("pages/0_Login.py")
    if session_config.get_session_username() is None or not len(
        session_config.get_session_username()
    ):
        st.switch_page("pages/0_Login.py")

    home()

    embedders = sse_api_engine.embedders(token=session_config.get_session_token())
    rerankers = sse_api_engine.rerankers(token=session_config.get_session_token())
    add_collection, collection_params = show_new_collection_window(
        embedders=embedders, rerankers=rerankers
    )

    orig_col_name = collection_params["collection_name"]
    username_str = session_config.get_session_username()
    collection_params["collection_name"] = proper_collection_name(
        orig_col_name, username_str
    )

    if add_collection is not None and add_collection:
        result = sse_api_engine.new_collection(
            token=session_config.get_session_token(),
            collection_params=collection_params,
        )

        if not result["status"]:
            return show_error_status(result)

        collection_name = collection_params["collection_name"]
        st.info(
            f"Collection {collection_name} has been created! "
            f"Go to 'Upload Documents' and choose {collection_name} "
            f"to add documents to collection!",
            icon="ℹ️",
        )
        st.page_link(
            "pages/2_Upload_Documents.py",
            label="Click here to Upload documents",
            icon="⛽",
        )
        st.divider()
        st.write(result)


if __name__ == "__main__":
    main()
