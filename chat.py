from dotenv import load_dotenv
import streamlit as st
import os

if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
if "PINECONE_API_KEY" in st.secrets:
    os.environ["PINECONE_API_KEY"] = st.secrets["PINECONE_API_KEY"]
if "UPSTAGE_API_KEY" in st.secrets:
    os.environ["UPSTAGE_API_KEY"] = st.secrets["UPSTAGE_API_KEY"]
if "NEO4J_URI" in st.secrets:
    os.environ["NEO4J_URI"] = st.secrets["NEO4J_URI"]
    os.environ["NEO4J_USER"] = st.secrets["NEO4J_USER"]
    os.environ["NEO4J_PASSWORD"] = st.secrets["NEO4J_PASSWORD"]

from llm import get_ai_response
APK_PAGE_URL = "https://lily-naranja-3e1.notion.site/On-Go-2e5a6169acfe80adac9bcde2e1e5b38e"
st.set_page_config(page_title="Confucian Chatbot", page_icon="📜") 

with st.sidebar:
    st.header("溫故(On-Go) 모바일 앱❕")
    st.markdown("온고지신(溫故知新)의 정신을 바탕으로 한 유학 기반 상담봇.")
    st.write("이 상담봇은 웹에서 바로 사용 가능하며, Android 기기에서는 APK로 설치해 모바일 앱으로도 이용할 수 있습니다.")
    st.markdown(f"📱 **[다운로드 페이지로 이동]({APK_PAGE_URL})**")
    st.markdown(
            """
- APK는 이 링크에서만 다운로드하세요.  
- 압축을 풀고난 후 앱 설치 시 Android 설정에서 **‘알 수 없는 앱 설치’ 허용**이 필요합니다.
- 인터넷 연결이 필요하며, 입력 내용은 답변 생성을 위해 서버/외부 API로 전송됩니다.  
  **민감한 개인정보(주민번호/계좌/비밀번호 등)는 입력하지 마세요.**  
- 전문 판단이 필요한 사안은 **전문가 상담을 권장**합니다.
"""
    )



st.title("📜성찰을 돕는 유학 기반 상담봇: 溫故(On-Go)")
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