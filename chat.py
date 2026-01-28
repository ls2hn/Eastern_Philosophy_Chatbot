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
APK_PAGE_URL = "https://lily-naranja-3e1.notion.site/2f6a6169acfe80919bd6f40dbfa1a5ee?pvs=74"
ANALECTS_URL = "https://db.cyberseodang.or.kr/front/alphaList/BookMain.do?tab=tab1_02&bnCode=jti_1h0301&titleId=C2"
MENCIUS_URL = "https://db.cyberseodang.or.kr/front/alphaList/BookMain.do?tab=tab1_02&bnCode=jti_1h0601&titleId=C2"
CHANGES_URL = "https://db.cyberseodang.or.kr/front/alphaList/BookMain.do?tab=tab1_02&bnCode=jti_1a0201&titleId=C1"
LEARNING_URL = "https://db.cyberseodang.or.kr/front/alphaList/BookMain.do?tab=tab1_02&bnCode=jti_1h0801&titleId=C1"
MEAN_URL = "https://db.cyberseodang.or.kr/front/alphaList/BookMain.do?tab=tab1_02&bnCode=jti_1h1001&titleId=C2"

st.set_page_config(page_title="Confucian Chatbot", page_icon="📜") 

with st.sidebar:
    st.header("溫故(On-Go) 모바일 앱❗")
    st.markdown("온고지신(溫故知新)의 정신을 바탕으로 한 유학 기반 상담봇.")
    st.write("이 상담봇은 웹에서 바로 사용 가능하며, Android 기기에서는 APK로 설치해 모바일 앱으로도 이용할 수 있습니다.")
    st.write("온고가 잘하는 것: 'Graph-RAG를 활용하여 신뢰도 높은 철학적 답변 생성'")
    st.markdown(f"📱 **[다운로드 페이지로 이동]({APK_PAGE_URL})**")
    st.markdown(
            """  
- 이 모바일 앱은 인터넷 연결이 필요하며, 입력 내용은 답변 생성을 위해 서버/외부 API로 전송됩니다.  
  **민감한 개인정보(주민번호/계좌/비밀번호 등)는 입력을 삼가주세요.**  
"""
    )
    st.header("동양고전DB 사이트에서 유학경전 더 읽어보기❕")
    st.markdown(f"**[논어]({ANALECTS_URL})**")
    st.markdown(f"**[맹자]({MENCIUS_URL})**")
    st.markdown(f"**[주역]({CHANGES_URL})**")
    st.markdown(f"**[대학]({LEARNING_URL})**")
    st.markdown(f"**[중용]({MEAN_URL})**")



st.title("📜일상의 성찰을 돕는 유학(儒學)기반 상담 챗봇: 溫故(On-Go)")
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