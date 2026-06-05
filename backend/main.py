from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal

from database.db import Base, engine
from database import models  # noqa: F401 — register ORM models
from gemini_generation import GeminiQuotaExhaustedError
from orchestrator import generate_twin_response
from text_sanitize import sanitize_api_text
import uvicorn
from dotenv import load_dotenv

load_dotenv()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Feynman Digital Twin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    mode: Literal["tutor", "student"] = Field(
        default="tutor",
        description=(
            "'tutor'   — Feynman explains physics to the user (default). "
            "'student' — Reverse Feynman: the user explains and Feynman evaluates."
        ),
    )


class RagSourceItem(BaseModel):
    filename: str
    friendly_name: str = ""
    snippet: str = ""


class ChatResponse(BaseModel):
    """Typed API contract returned to the frontend."""

    session_id: str
    response: str = Field(description="Sanitized Feynman reply text")
    sources: list[RagSourceItem] = Field(
        default_factory=list,
        description="RAG chunks used for this reply (filename + snippet)",
    )
    is_cached: bool = Field(
        default=False,
        description="True when the response was served from the semantic cache.",
    )


@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Feynman Digital Twin API is running"}


def _coerce_sources(raw_sources: object) -> list[RagSourceItem]:
    if not isinstance(raw_sources, list):
        return []
    items: list[RagSourceItem] = []
    for entry in raw_sources:
        if not isinstance(entry, dict):
            continue
        items.append(
            RagSourceItem(
                filename=str(entry.get("filename") or "unknown_source.md"),
                friendly_name=str(entry.get("friendly_name") or ""),
                snippet=str(entry.get("snippet") or ""),
            )
        )
    return items


@app.get("/api/test/rag")
def test_rag(query: str = Query(..., description="The physics question to test against the RAG pipeline")):
    try:
        from rag.retrieve import retrieve_context_and_sources

        formatted_context, sources = retrieve_context_and_sources(query)
        return {
            "query": query,
            "context": formatted_context,
            "sources": [s.model_dump() for s in _coerce_sources(sources)],
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    try:
        result = await generate_twin_response(
            req.session_id,
            req.message,
            mode=req.mode,
        )
        return ChatResponse(
            session_id=str(result["session_id"]),
            response=sanitize_api_text(str(result["response"])),
            sources=_coerce_sources(result.get("sources", [])),
            is_cached=bool(result.get("is_cached", False)),
        )
    except GeminiQuotaExhaustedError as exc:
        print(f"/api/chat quota exhausted: {str(exc)}")
        raise HTTPException(
            status_code=503,
            detail=sanitize_api_text(exc.user_message),
        ) from exc
    except Exception as exc:
        print(f"/api/chat failed: {str(exc)}")
        raise HTTPException(status_code=502, detail=sanitize_api_text(str(exc))) from exc


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
