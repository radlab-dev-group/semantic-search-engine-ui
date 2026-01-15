import streamlit as st

from pages.src.constants import session_config, sse_api_engine
from pages.src.ui_utils import prepare_collection_to_choose


upload_dir = "./uploads/"


def home():
    st.set_page_config(
        page_title="SSE - upload documents",
        page_icon="🧊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("Upload documents to SSE")


def prepare_files_to_upload_to_collection():
    upl_container = st.container(border=True)
    uploaded_files = upl_container.file_uploader(
        "Add file to collection",
        accept_multiple_files=True,
        type=["pdf", "docx", "txt", "zip"],
    )
    return uploaded_files


def index_files_in_database(upload_files, collection_of_documents) -> bool:
    form = st.form("index_collection_files_form")
    container = form.container(border=True)

    container.write("Documents indexing options")

    tic_col, ot_col = container.columns(2)
    tokens_in_chunk = tic_col.slider(
        "Max tokens in chunk", min_value=10, max_value=1000, value=200
    )
    overlap_tokens = ot_col.slider(
        "Number of overlapping tokens between chunks",
        min_value=0,
        max_value=200,
        value=20,
    )

    chk_1_c, chk_2_c = container.columns(2)
    use_text_denoiser = chk_1_c.checkbox(
        "Denoise text before indexing (radlab/polish-denoiser-t5-base)", value=False
    )
    clear_text = chk_1_c.checkbox(
        "Clear text before indexing (full chain processor)", value=True
    )
    check_text_lang = chk_1_c.checkbox(
        "Check language of indexed files (store to database)", value=True
    )
    prepare_proper_pages = chk_2_c.checkbox(
        "Prepare proper pages (merge single texts from same page)", value=True
    )
    merge_document_pages = chk_2_c.checkbox(
        "Merge whole document to single page and process it", value=False
    )

    btn = form.form_submit_button("Start indexing")
    if btn:
        indexing_options = {
            "clear_text": clear_text,
            "use_text_denoiser": use_text_denoiser,
            "check_text_lang": check_text_lang,
            "prepare_proper_pages": prepare_proper_pages,
            "merge_document_pages": merge_document_pages,
            "max_tokens_in_chunk": tokens_in_chunk,
            "number_of_overlap_tokens": overlap_tokens,
        }
        upload_response = sse_api_engine.upload_files(
            token=session_config.get_session_token(),
            files_to_upload=upload_files,
            collection_name=collection_of_documents,
            indexing_options=indexing_options,
        )
        if upload_response is None or upload_response["status"] is False:
            st.error("Problem while uploading files to engine backend")
            st.write(upload_response)
            return False
        st.info(
            "Files are uploaded and indexed! Go to `Semantic Search Engine` "
            "and test ask about knowledge from the indexed documents!",
            icon="ℹ️",
        )
        st.page_link(
            "pages/3_Semantic_Search_Engine.py",
            label="Click here to use Semantic Search Engine",
            icon="🚒",
        )
        st.divider()
        st.write(upload_response)
        st.balloons()
        return True
    return False


def main():
    if session_config.get_session_token() is None:
        st.switch_page("pages/0_Login.py")
    home()

    collection_of_documents = prepare_collection_to_choose(
        token=session_config.get_session_token()
    )
    if collection_of_documents is None:
        return

    files_to_upload = prepare_files_to_upload_to_collection()
    if files_to_upload is not None and len(files_to_upload):
        index_files_in_database(files_to_upload, collection_of_documents)


if __name__ == "__main__":
    main()
