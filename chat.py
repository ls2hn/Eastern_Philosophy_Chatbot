from dotenv import load_dotenv
import streamlit as st
from llm import get_ai_message

st.set_page_config(page_title="논어 챗봇", page_icon="🎋") 
st.title("🎋 논어 챗봇")
st.caption("논어에 나온 구절을 토대로 얘기해보자.")

load_dotenv()

if 'message_list' not in st.session_state:
    st.session_state.message_list = []

for message in st.session_state.message_list:
    with st.chat_message(message["role"]):
        st.write(message["content"])

if user_question := st.chat_input(placeholder="궁금한 내용들을 말해주세요."):
    with st.chat_message("user"):
        st.write(user_question)
    st.session_state.message_list.append({"role":"user", "content":user_question})

    with st.spinner("생각 중..."):
        ai_message = get_ai_message(user_question)
        with st.chat_message("ai"):
            st.write(ai_message)
        st.session_state.message_list.append({"role":"ai", "content":ai_message})