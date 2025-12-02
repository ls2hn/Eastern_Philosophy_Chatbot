from langchain_upstage import UpstageEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_openai import ChatOpenAI
from langchain_classic import hub
from langchain_classic.chains import RetrievalQA

def get_ai_message(user_message):
    
    # Upstage에서 제공하는 Embedding Model을 활용해서 chunk를 vector화
    embedding=UpstageEmbeddings(model="solar-embedding-1-large")
    index_name = 'analects-upstage-index'
    database = PineconeVectorStore.from_existing_index(index_name=index_name, embedding=embedding)

    llm = ChatOpenAI(model="gpt-4o")
    prompt = hub.pull("rlm/rag-prompt")
    retriever = database.as_retriever(search_kwargs={'k':4})

    qa_chain = RetrievalQA.from_chain_type(
        llm,
        retriever = retriever,
        chain_type_kwargs = {"prompt":prompt}
    )
    ai_message = qa_chain({"query": user_message})

    return ai_message["result"]