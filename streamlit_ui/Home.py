import os
import streamlit as st


def home():
    st.set_page_config(
        page_title="Semantic search engine",
        page_icon="🧊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("Conversational UI to search engine (with Q&A models)")
    st.write("## Welcome to SSSUI (Simple Semantic Search UI)! 👋")
    st.sidebar.success("Select an option above.")

    st.markdown(
        """
        This is a fully functional UI to RadLab Semantic Search Engine. 
        This application may be helpful when you want to test LLM models 
        combined with IR/Semantic Search (f.e. for RAG)/Conversational search
        
        **👈 Select an option from the sidebar** to use engine
        
        ### Some dev information
        - Azure Project with [database](https://dev.azure.com/radlab-group/radlab-semantic-search-db) 
        used to store embeddings and similarity search
        - Azure Project with 
        [semantic search engine backend](https://dev.azure.com/radlab-group/radlab-semantic-search-engine)
        with full REST API handling
        - Azure Project with [conversational UI](https://dev.azure.com/radlab-group/radlab-conversational-search-ui)
        providing this streamlit application
        - Azure Project with [LLM API service](https://dev.azure.com/radlab-group/radlab-llama-service)
        provided as internal publicity available api 
        - Azure Project with starter [django-core](https://dev.azure.com/radlab-group/radlab-django-core) 
        for rest framework
    """
    )


if __name__ == "__main__":
    home()
