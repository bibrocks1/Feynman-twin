import os
import ssl

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma

CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_db")


def _embedding_client_args() -> dict:
    """SSL context for environments with a misconfigured local CA store."""
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    return {"verify": ssl_ctx}


def get_retriever():
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        client_args=_embedding_client_args(),
    )
    
    # We create a persistent Chroma instance pointing to the generated DB
    vector_db = Chroma(
        persist_directory=CHROMA_DIR,
        embedding_function=embeddings
    )
    
    # Return a retriever that fetches the top 3 chunks
    return vector_db.as_retriever(search_kwargs={"k": 3})

SNIPPET_LENGTH = 150


def _package_sources(docs) -> list[dict]:
    """Build source metadata for the API / Source Blueprint UI."""
    sources: list[dict] = []
    for doc in docs:
        source_path = doc.metadata.get("source", "Unknown Source")
        filename = os.path.basename(source_path)
        content = (doc.page_content or "").strip()
        snippet = content[:SNIPPET_LENGTH]
        if len(content) > SNIPPET_LENGTH:
            snippet += "..."
        sources.append(
            {
                "filename": filename,
                "friendly_name": filename.replace(".md", "").replace("_", " ").title(),
                "snippet": snippet,
            }
        )
    return sources


def retrieve_context_and_sources(query: str) -> tuple[str, list[dict]]:
    """
    Retrieves top-K chunks once, returning formatted LLM context and UI source cards.
    """
    retriever = get_retriever()
    docs = retriever.invoke(query)
    sources = _package_sources(docs)

    formatted_context = ""
    for idx, doc in enumerate(docs):
        source_path = doc.metadata.get("source", "Unknown Source")
        filename = os.path.basename(source_path)
        friendly_source = filename.replace(".md", "").replace("_", " ").title()

        formatted_chunk = (
            f"### Document {idx + 1}\n"
            f"{doc.page_content}\n"
            f"*[Source: {friendly_source}]*\n\n"
        )
        formatted_context += formatted_chunk

    return formatted_context, sources


def retrieve_and_format_context(query: str) -> str:
    """
    Retrieves the most relevant chunks for the given query and formats them
    with explicit markdown citations.
    """
    formatted_context, _ = retrieve_context_and_sources(query)
    return formatted_context

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    # Test execution
    test_query = "What is the atomic hypothesis?"
    print(f"Query: {test_query}\n")
    print("Retrieved Context:\n")
    print(retrieve_and_format_context(test_query))
