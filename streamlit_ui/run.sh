#!/bin/bash

# Run application under streamlit server
export STREAMLIT_SERVER_MAX_UPLOAD_SIZE=6000
export STREAMLIT_SSL_CONNECTION=0
export STREAMLIT_RUN_SERVER_LOCALHOST=1


# Run application
if [ $# -eq 1 ]
then
  if [ "${1}" == "secret:csb" ]
  then
    ~/.local/bin/streamlit run Home.py
  else
    mv pages/4_Conversational_Search.py pages/4_Conversational_Search.py.tmp
    ~/.local/bin/streamlit run Home.py --server.port 8502
    mv pages/4_Conversational_Search.py.tmp pages/4_Conversational_Search.py
  fi
else
    mv pages/4_Conversational_Search.py pages/4_Conversational_Search.py.tmp
    ~/.local/bin/streamlit run Home.py --server.port 8502
    mv pages/4_Conversational_Search.py.tmp pages/4_Conversational_Search.py
fi
