from dotenv import load_dotenv
import streamlit as st
import os

if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
if "PINECONE_API_KEY" in st.secrets:
    os.environ["PINECONE_API_KEY"] = st.secrets["PINECONE_API_KEY"]
if "UPSTAGE_API_KEY" in st.secrets:
    os.environ["UPSTAGE_API_KEY"] = st.secrets["UPSTAGE_API_KEY"]

from llm import get_ai_response

st.set_page_config(page_title="Confucian Chatbot", page_icon="📜") 
st.title("🏮 성찰을 돕는 유학 기반 상담봇")
st.caption("유학의 지혜를 빌려 당신의 일상을 함께 성찰합니다. 고민이 있나요?")

load_dotenv()

if 'message_list' not in st.session_state:
    st.session_state.message_list = []

# 이전 대화 랜더링
for message in st.session_state.message_list:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# 새 입력 받기
if user_question := st.chat_input(placeholder="궁금한 내용들을 말해주세요."):
    # 유저 메시지 출력 + 저장
    with st.chat_message("user"):
        st.write(user_question)
    st.session_state.message_list.append({"role":"user", "content":user_question})

    # AI 응답
    with st.spinner("생각 중..."):
        ai_response = get_ai_response(user_question)
        with st.chat_message("ai"):
            ai_message = st.write_stream(ai_response)
            st.session_state.message_list.append({"role":"ai", "content":ai_message})