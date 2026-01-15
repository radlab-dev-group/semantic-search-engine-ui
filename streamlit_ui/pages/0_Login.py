import streamlit as st

from pages.src.constants import session_config, sse_api_engine


def home():
    st.set_page_config(
        page_title="SSE - Log in",
        page_icon="🧊",
        layout="centered",
        initial_sidebar_state="expanded",
    )
    st.title("Log in to SSE")


def show_login_window() -> (str | None, str | None):
    token = ""
    with st.form("login_form"):
        username = st.text_input("Username", session_config.get_session_username())
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Submit")
        if submitted:
            token = sse_api_engine.login(username=username, password=password)
            if token is None:
                username = None
    return submitted, token, username


def main():
    home()

    username = session_config.get_session_username()
    if username is not None and len(username.strip()) > 0:
        st.info(f"You are logged as {username}")
        return

    submitted, token, username = show_login_window()
    if submitted and (token is None or not len(token)):
        st.error("Invalid username or password!")
        st.info(f"get_session_token={session_config.get_session_token()}")
    elif submitted:
        st.info("You are logged as {} now".format(username))
        st.info("Feel free to use Semantic Search Engine!")

    session_config.set_session_token_username(token, username)
    if submitted:
        st.switch_page("pages/3_Semantic_Search_Engine.py")


if __name__ == "__main__":
    main()
