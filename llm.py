from dotenv import load_dotenv
load_dotenv()
from langchain_upstage import UpstageEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_openai import ChatOpenAI
from langchain_classic.chains import create_history_aware_retriever, create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import MessagesPlaceholder, ChatPromptTemplate, FewShotChatMessagePromptTemplate
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda
from typing import Optional, Dict, Any

from config import answer_examples
from graph_store import (
    extract_concepts_mvp,
    retrieve_passages_by_concepts,
    build_graph_evidence_block,
    retrieve_paths_2hop,
    build_graph_path_evidence_block,
)

store = {}

def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

def get_retriever():
    # Upstage에서 제공하는 Embedding Model을 활용해서 chunk를 vector화
    embedding=UpstageEmbeddings(model="solar-embedding-1-large")
    index_name = 'analects-upstage-index'
    database = PineconeVectorStore.from_existing_index(index_name=index_name, embedding=embedding)
    retriever = database.as_retriever(search_kwargs={'k':4})
    return retriever

def get_history_retriever():
    llm = get_llm()
    retriever = get_retriever()

    contextualize_q_system_prompt = (
        "Given a chat history and the latest user question "
        "which might reference context in the chat history, "
        "formulate a standalone question which can be understood "
        "without the chat history. Do NOT answer the question, "
        "just reformulate it if needed and otherwise return it as is."
    )

    contextualize_q_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", contextualize_q_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )

    history_aware_retriever = create_history_aware_retriever(
        llm, retriever, contextualize_q_prompt
    )
    return history_aware_retriever

def get_llm(model='gpt-4o'):
    llm = ChatOpenAI(
        model=model,
        max_tokens=512,
        temperature=0.6,
    )
    return llm


def get_rag_chain():
    llm = get_llm()
    
    example_prompt = ChatPromptTemplate.from_messages(
        [
            ("human", "{input}"),
            ("ai", "{answer}"),
        ]
    )
    few_shot_prompt = FewShotChatMessagePromptTemplate(
        example_prompt=example_prompt,
        examples=answer_examples,
    )

    system_prompt = (
        "You are an expert in Eastern Philosophy and a sincere counseling chatbot "
        "specializing in answering user questions. You must always respond in Korean. "
        "Keep your answers brief. Keep your response to a maximum of 25 sentences. "
        "You're here to help users think, not to preach. Your goal is not to preach or "
        "give one-sided lectures, but to guide users to reflect on their own lives "
        "through shared contemplation and given context. Use the following pieces of "
        "retrieved context from the Analects and other Confucian classics provided to answer the question. "
        "When the answer is based on the provided text from the Analects and Confucian classics, "
        "please begin the response by presenting the relevant original Chinese text along with the chapter "
        "and number. In your response, refrain from making decisions on behalf of the user. "
        "Instead of providing definitive answers, ask up to two meaningful questions "
        "that help the user relate the wisdom of the classics to their personal situation or "
        "counseling needs. If the answer is not found in the provided context, "
        "you may state your thoughts briefly, but never fabricate non-existent records or facts as real. "
        "Adjust the length of your answer based on the amount of retrieved context "
        "\n\n"
        "{context}"
    )

    qa_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            few_shot_prompt,
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )
    history_aware_retriever = get_history_retriever()

    def wrapped_retriever(inputs: dict): # “벡터 검색 결과” 앞에 “그래프 근거”를 추가
        import sys
        print("[DEBUG] wrapped_retriever CALLED", file=sys.stderr, flush=True)

        q = inputs.get("input", "")
        print(f"\n[DEBUG] wrapped_retriever CALLED q={q[:30]!r}", file=sys.stderr, flush=True)

        strength = decide_graph_strength(q, extract_concepts_mvp(q))
        print(f"[DEBUG] strength={strength}", file=sys.stderr, flush=True)

        docs = history_aware_retriever.invoke(inputs) # 파인콘에서 벡터 검색 결과
        print(f"[DEBUG] pinecone docs={len(docs)}", file=sys.stderr, flush=True)
        graph_ctx = get_graph_context(q)  # k를 굳이 안 줘도 됨(동적)
        print(f"[DEBUG] graph_ctx length={len(graph_ctx)}", file=sys.stderr, flush=True)
        print("[DEBUG] graph_ctx head:", graph_ctx[:200].replace("\n"," "), file=sys.stderr, flush=True)

        if graph_ctx:
            graph_doc = Document(
                page_content=graph_ctx, # graph_ctx 그래프 기반 근거
                metadata={"source": "neo4j", "type": "graph_evidence"}
            )
            return [graph_doc] + docs

        return docs

    graph_retriever = RunnableLambda(wrapped_retriever)

    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)

    rag_chain = create_retrieval_chain(graph_retriever, question_answer_chain)

    # chatting history까지 포함된 retriever를 사용한 답변 생성
    conversational_rag_chain = RunnableWithMessageHistory(
        rag_chain,
        get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history",
        output_messages_key="answer",
    ).pick('answer')
 
    return conversational_rag_chain

def decide_graph_strength(question: str, concepts: list[str]) -> str:
    """
    weak: 짧고 단순한 질문 → 그래프 근거 최소
    medium: 기본값
    strong: 비교/적용/원인/관계/사회질서 등 복합 질문 → 그래프 근거 강화
    """
    q = (question or "").strip()

    complex_keywords = [
        "왜", "어떻게", "차이", "비교", "관계", "연결", "영향", "원인", "결과",
        "적용", "현대", "사회", "정치", "질서", "기준", "책임", "갈등", "해결",
        "구체", "사례", "예시", "상황", "상담"
    ]

    # 복잡한 질문 조건: 길거나, 복합 키워드 포함, 개념이 많이 잡힘
    if len(q) >= 80 or any(k in q for k in complex_keywords) or len(concepts) >= 4:
        return "strong"

    # 단순 질문 조건: 매우 짧고 개념도 적음
    if len(q) <= 25 and len(concepts) <= 2:
        return "weak"

    return "medium"


def graph_params_by_strength(strength: str) -> Dict[str, Any]:
    """
    강도별 파라미터(목표: 중간을 기본으로, 필요할 때만 강하게)
    """
    if strength == "weak":
        return dict(k_paths=2, k_seed_passages=6, max_paths=1, k_passages=2, max_chars=2200)
    if strength == "strong":
        return dict(k_paths=10, k_seed_passages=20, max_paths=5, k_passages=5, max_chars=8000)
    # medium (default)
    return dict(k_paths=6, k_seed_passages=12, max_paths=3, k_passages=4, max_chars=4500)


def clip_text(s: str, max_chars: int) -> str:
    if not s:
        return ""
    if len(s) <= max_chars:
        return s
    # 너무 길면 앞부분 위주로 자르되, 줄 단위로 깔끔하게
    cut = s[:max_chars]
    last_nl = cut.rfind("\n")
    return (cut[:last_nl] if last_nl > 200 else cut).rstrip() + "\n\n[...truncated...]"

def get_graph_context(question: str, k: int = 5) -> str:
    concepts = extract_concepts_mvp(question)
    if not concepts:
        return ""
    
    strength = decide_graph_strength(question, concepts)
    params = graph_params_by_strength(strength)

    # k(패시지 evidence 수)는 외부에서 주면 우선, 아니면 강도별 기본값 사용
    k_passages = int(k) if k is not None else params["k_passages"]

    # 1) PATH evidence (논증 사슬) 먼저
    try:
        paths = retrieve_paths_2hop(concepts, k_paths=params["k_paths"], k_seed_passages=params["k_seed_passages"])
        path_ctx = build_graph_path_evidence_block(paths, question, max_paths=params["max_paths"])
    except Exception:
        path_ctx = ""

    try:
        # 2) 기존 passage evidence도 뒤에 붙여서 안정성 확보
        rows = retrieve_passages_by_concepts(concepts, k=k_passages)
        base_ctx = build_graph_evidence_block(rows, question)
    except Exception:
        base_ctx = ""

    combined = ""
    if path_ctx and base_ctx:
        combined = path_ctx + "\n\n" + base_ctx
    else:
        combined = path_ctx or base_ctx

    combined = clip_text(combined, params["max_chars"])

    return combined


def get_ai_response(user_message):
    rag_chain = get_rag_chain()
    ai_response = rag_chain.stream(
        {
            "input": user_message
        },
        config={
            "configurable": {"session_id": "abc123"}
        },
    )

    return ai_response