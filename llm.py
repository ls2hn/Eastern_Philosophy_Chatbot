from langchain_upstage import UpstageEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_openai import ChatOpenAI
from langchain_classic.chains import create_history_aware_retriever, create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import MessagesPlaceholder, ChatPromptTemplate, FewShotChatMessagePromptTemplate
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory

from config import answer_examples

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
        "You are an expert in Eastern Philosophy specializing in answering user questions. "
        "You must always respond in Korean. "
        "Use the following pieces of retrieved context from the Analects to answer the question. "
        "When the answer is based on the Analects text, please begin the response by presenting "
        "the relevant original Chinese text along with the Analects chapter and number. "
        "If the answer is not found in the provided context, you may state your thoughts briefly, "
        "but never fabricate non-existent records or facts as real. "
        "Adjust the length of your answer based on the amount of retrieved context "
        "and keep the answer concise. Limit your response to a maximum of thirty sentences. "
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
    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)

    rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)

    # chatting history까지 포함된 retriever를 사용한 답변 생성
    conversational_rag_chain = RunnableWithMessageHistory(
        rag_chain,
        get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history",
        output_messages_key="answer",
    ).pick('answer')
 
    return conversational_rag_chain


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