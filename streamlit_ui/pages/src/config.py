import streamlit as st


class SessionConfig:
    TOKEN_SESSION_NAME = "sse_token"
    TOKEN_SESSION_LOGIN = "sse_login"
    AVAILABLE_COLLECTIONS = "collections"
    CACHED_CONTROLLERS = "cached_controllers"

    CHAT = "chat"
    CHAT_ID = "chat_id"

    CS_RAG_DETECTED_QUESTION = "cs_rag_detected_question_str"
    CS_RAG_GENERAL_STATS = "cs_rag_general_stats"
    CS_RAG_DETAILED_RESULTS = "cs_rag_detailed_stats"

    @staticmethod
    def __return__value__(ret_value):
        if ret_value is None:
            return None
        if type(ret_value) in [str]:
            return None if not len(ret_value.strip()) else ret_value
        return ret_value

    @staticmethod
    def set_session_state():
        st.session_state[SessionConfig.CHAT] = []
        st.session_state[SessionConfig.CHAT_ID] = None
        st.session_state[SessionConfig.TOKEN_SESSION_NAME] = None
        st.session_state[SessionConfig.TOKEN_SESSION_LOGIN] = None
        st.session_state[SessionConfig.AVAILABLE_COLLECTIONS] = []
        st.session_state[SessionConfig.CACHED_CONTROLLERS] = {}
        st.session_state[SessionConfig.CS_RAG_GENERAL_STATS] = None
        st.session_state[SessionConfig.CS_RAG_DETAILED_RESULTS] = None
        st.session_state[SessionConfig.CS_RAG_DETECTED_QUESTION] = None

    @staticmethod
    def set_session_token_username(token: str | None, username: str | None) -> None:
        st.session_state[SessionConfig.TOKEN_SESSION_NAME] = token
        st.session_state[SessionConfig.TOKEN_SESSION_LOGIN] = username

    @staticmethod
    def set_available_collections(collections: dict):
        st.session_state[SessionConfig.AVAILABLE_COLLECTIONS] = collections

    @staticmethod
    def get_available_collections():
        return st.session_state[SessionConfig.AVAILABLE_COLLECTIONS]

    @staticmethod
    def get_session_token():
        if SessionConfig.TOKEN_SESSION_NAME not in st.session_state:
            return None
        token_str = st.session_state[SessionConfig.TOKEN_SESSION_NAME]
        return SessionConfig.__return__value__(token_str)

    @staticmethod
    def get_session_username():
        if SessionConfig.TOKEN_SESSION_LOGIN not in st.session_state:
            return None
        username = st.session_state[SessionConfig.TOKEN_SESSION_LOGIN]
        return SessionConfig.__return__value__(username)

    @staticmethod
    def set_session_chat_chat_id(chat: list, chat_id: str):
        st.session_state[SessionConfig.CHAT_ID] = chat_id
        st.session_state[SessionConfig.CHAT] = chat

    @staticmethod
    def set_session_cs_rag(
        detected_question: str | None,
        general_stats: dict | None,
        detailed_results: dict | None,
    ):
        st.session_state[SessionConfig.CS_RAG_GENERAL_STATS] = general_stats
        st.session_state[SessionConfig.CS_RAG_DETAILED_RESULTS] = detailed_results
        st.session_state[SessionConfig.CS_RAG_DETECTED_QUESTION] = detected_question

    @staticmethod
    def get_session_cs_rag() -> list:
        if SessionConfig.CS_RAG_DETECTED_QUESTION not in st.session_state:
            return [None, None, None]
        return [
            st.session_state[SessionConfig.CS_RAG_DETECTED_QUESTION],
            st.session_state[SessionConfig.CS_RAG_GENERAL_STATS],
            st.session_state[SessionConfig.CS_RAG_DETAILED_RESULTS],
        ]

    @staticmethod
    def get_session_chat():
        if SessionConfig.CHAT not in st.session_state:
            return []
        chat = st.session_state[SessionConfig.CHAT]
        return SessionConfig.__return__value__(chat)

    @staticmethod
    def get_session_chat_id():
        if SessionConfig.CHAT_ID not in st.session_state:
            return None
        chat_id = st.session_state[SessionConfig.CHAT_ID]
        return SessionConfig.__return__value__(chat_id)


SessionConfig.set_session_state()
