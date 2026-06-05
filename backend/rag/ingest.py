import os
import ssl
import time

from dotenv import load_dotenv
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_genai._common import GoogleGenerativeAIError
from langchain_community.vectorstores import Chroma

BATCH_SIZE = 8
BATCH_DELAY_SEC = 4
MAX_RETRIES = 6

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_db")

def ingest_documents(reset_chroma: bool = True):
    if reset_chroma and os.path.isdir(CHROMA_DIR):
        import shutil
        print(f"Resetting existing Chroma store at {CHROMA_DIR}...")
        shutil.rmtree(CHROMA_DIR)

    print(f"Loading documents from {DATA_DIR}...")
    loader = DirectoryLoader(
        DATA_DIR,
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    documents = loader.load()
    
    if not documents:
        print("No documents found to ingest.")
        return

    print(f"Loaded {len(documents)} documents. Splitting...")
    
    # 500 tokens roughly translates to ~2000 characters. 100 token overlap = ~400 characters.
    # Using chunk_size=2000 and chunk_overlap=400 as character equivalents for tokens.
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=2000,
        chunk_overlap=400,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    
    chunks = text_splitter.split_documents(documents)
    print(f"Split into {len(chunks)} chunks. Generating embeddings and storing in Chroma...")

    # Using the standard Gemini embedding model
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        client_args={"verify": ssl_ctx},
    )
    
    vector_db = None
    total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[batch_idx : batch_idx + BATCH_SIZE]
        batch_num = batch_idx // BATCH_SIZE + 1

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if vector_db is None:
                    vector_db = Chroma.from_documents(
                        documents=batch,
                        embedding=embeddings,
                        persist_directory=CHROMA_DIR,
                    )
                else:
                    vector_db.add_documents(batch)
                print(f"Ingested batch {batch_num}/{total_batches} ({len(batch)} chunks)")
                if batch_num < total_batches:
                    time.sleep(BATCH_DELAY_SEC)
                break
            except GoogleGenerativeAIError as exc:
                if "429" not in str(exc) and "RESOURCE_EXHAUSTED" not in str(exc):
                    raise
                wait_sec = 20 * attempt
                print(
                    f"Rate limited on batch {batch_num} "
                    f"(attempt {attempt}/{MAX_RETRIES}); waiting {wait_sec}s..."
                )
                time.sleep(wait_sec)
        else:
            raise RuntimeError(
                f"Failed to ingest batch {batch_num} after {MAX_RETRIES} retries."
            )

    print(f"Successfully ingested {len(chunks)} chunks into {CHROMA_DIR}")

if __name__ == "__main__":
    # Ensure Gemini API key is set
    if "GEMINI_API_KEY" not in os.environ:
        print("ERROR: GEMINI_API_KEY environment variable not set.")
        exit(1)
    
    ingest_documents()
