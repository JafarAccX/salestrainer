from pathlib import Path as FsPath
from typing import Any, Literal

import logging
from fastapi import FastAPI, File, HTTPException, Path, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.document_store import document_store
from core.evaluator import evaluator
from core.livekit_service import livekit_service
from core.mock_call_history_store import mock_call_history_store
from core.llm_client import llm_client
from core.rag_engine import rag_engine
from core.config_store import config_store

app = FastAPI(title="CRM Sales Trainer Backend")
FRONTEND_INDEX = FsPath(__file__).resolve().parent.parent / "frontend" / "index.html"
FRONTEND_ADMIN = FsPath(__file__).resolve().parent.parent / "frontend" / "admin.html"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ModuleRequest(BaseModel):
    name: str = Field(..., min_length=1, examples=["Generative AI Program"])
    description: str = ""


class ModuleUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, examples=["How should I explain generative AI to a prospect?"])
    module_id: str | None = None
    sales_rep_id: str | None = None
    crm_context: dict[str, Any] | None = None


class EvalRequest(BaseModel):
    question: str
    answer: str
    module_id: str | None = None

class CurriculumResponse(BaseModel):
    curriculum: str
    module_id: str


class MockCallStartRequest(BaseModel):
    sales_rep_id: str
    module_id: str | None = None


class MockCallEvaluateRequest(BaseModel):
    session_id: str | None = None
    voice_transcript: str | None = None
    chat_transcript: str | None = None
    module_id: str | None = None
    transcript: str | None = None # backwards compat
    text_question: str | None = None # backwards compat
    text_answer: str | None = None # backwards compat


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


class DocumentResponse(BaseModel):
    id: str
    module_id: str
    filename: str
    path: str
    content_type: str | None = None
    size_bytes: int
    status: str
    created_at: str
    updated_at: str
    chunk_count: int | None = None
    error: str | None = None


class ModuleResponse(BaseModel):
    id: str
    name: str
    description: str
    documents: list[DocumentResponse]
    created_at: str
    updated_at: str


class ModuleListResponse(BaseModel):
    modules: list[ModuleResponse]


class UploadResponse(BaseModel):
    message: str
    document: DocumentResponse


class DeleteModuleResponse(BaseModel):
    deleted_module: ModuleResponse
    deleted_vectors: int


class DeleteDocumentResponse(BaseModel):
    deleted_document: DocumentResponse
    deleted_vectors: int


class ChatResponse(BaseModel):
    response: str
    module_id: str | None = None


class QuestionListResponse(BaseModel):
    questions: list[str]
    module_id: str | None = None


class EvalResponse(BaseModel):
    score: float
    feedback: str
    raw_response: str | None = None
    module_id: str | None = None


class MockCallStartResponse(BaseModel):
    session_id: str
    room_name: str
    participant_identity: str
    livekit_url: str | None = None
    participant_token: str | None = None
    agent_name: str
    agent_dispatched: bool = False
    module_id: str | None = None
    voice_pipeline: dict[str, Any]
    created_at: str
    frontend_message: str | None = None
    connection_link: str | None = None
    kb_context: str | None = None



class MockCallEvalResponse(BaseModel):
    final_score: float
    voice_score: float
    text_score: float
    product_accuracy: float | None = None
    discovery: float | None = None
    objection_handling: float | None = None
    empathy: float | None = None
    closing_clarity: float | None = None
    voice_feedback: str
    text_feedback: str | None = None
    module_id: str | None = None
    hiring_decision: str


class MockCallHistoryResponse(BaseModel):
    records: list[dict[str, Any]]

class ConfigResponse(BaseModel):
    active_module_id: str | None = None
    active_agent_id: str | None = None
    timer_minutes: int
    agents: list[dict[str, str]] | None = None

class ConfigUpdateRequest(BaseModel):
    active_module_id: str | None = None
    active_agent_id: str | None = None
    timer_minutes: int | None = None

class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    instructions: str = Field(..., min_length=1)

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok", "service": "sales-trainer-backend"}


@app.get("/", include_in_schema=False)
async def frontend_home():
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)
    raise HTTPException(status_code=404, detail="Frontend not found.")

@app.get("/admin", include_in_schema=False)
async def frontend_admin():
    if FRONTEND_ADMIN.exists():
        return FileResponse(FRONTEND_ADMIN)
    raise HTTPException(status_code=404, detail="Admin frontend not found.")

@app.get("/ui", include_in_schema=False)
async def frontend_ui():
    return await frontend_home()

@app.get("/api/config", response_model=ConfigResponse)
async def get_config():
    return config_store.get_config()

@app.post("/api/config", response_model=ConfigResponse)
async def update_config(request: ConfigUpdateRequest):
    return config_store.update_config(request.active_module_id, request.active_agent_id, request.timer_minutes)

@app.get("/api/agents")
async def list_agents():
    return {"agents": config_store.list_agents()}

@app.post("/api/agents")
async def create_agent(request: AgentCreateRequest):
    import uuid
    agent_id = str(uuid.uuid4())
    return config_store.create_agent(agent_id, request.name, request.instructions)

@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    success = config_store.delete_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "deleted"}


@app.get("/api/kb/modules", response_model=ModuleListResponse)
async def list_modules():
    return {"modules": document_store.list_modules()}


@app.get("/api/kb/modules/{module_id}", response_model=ModuleResponse)
async def get_module(module_id: str = Path(..., description="Knowledge base module id returned by POST /api/kb/modules.")):
    module = document_store.get_module(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Knowledge base module not found.")
    return module


@app.patch("/api/kb/modules/{module_id}", response_model=ModuleResponse)
async def update_module(module_id: str, request: ModuleUpdateRequest):
    module = document_store.update_module(module_id, request.name, request.description)
    if not module:
        raise HTTPException(status_code=404, detail="Knowledge base module not found.")
    return module


@app.post("/api/kb/modules/{module_id}/documents", response_model=UploadResponse)
async def upload_module_document(module_id: str, file: UploadFile = File(...)):
    if not _is_supported_file(file.filename):
        raise HTTPException(status_code=400, detail="Only PDF, TXT, and Markdown files are supported.")

    document = await document_store.add_document(module_id, file)
    if not document:
        raise HTTPException(status_code=404, detail="Knowledge base module not found.")

    success, msg, chunk_count = rag_engine.process_document(
        document["path"],
        module_id=module_id,
        document_id=document["id"],
    )
    if not success:
        document_store.mark_document_failed(module_id, document["id"], msg)
        raise HTTPException(status_code=500, detail=msg)

    indexed_document = document_store.mark_document_indexed(module_id, document["id"], chunk_count)
    return {"message": "Document uploaded and indexed successfully.", "document": indexed_document}


@app.delete("/api/kb/modules/{module_id}/documents/{document_id}", response_model=DeleteDocumentResponse)
async def delete_module_document(module_id: str, document_id: str):
    document = document_store.delete_document(module_id, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    _, deleted_vectors = rag_engine.delete_document_vectors(module_id, document_id)
    return {"deleted_document": document, "deleted_vectors": deleted_vectors}


@app.post("/api/chat", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    logger.info("--> Received CHAT request: %s (Module: %s)", request.message, request.module_id)
    _validate_module_id(request.module_id)
    context = rag_engine.retrieve_context(request.message, module_id=request.module_id)
    if request.module_id and not context.strip():
        return {
            "response": "I do not have enough information from the uploaded documents in this knowledge base module to answer that.",
            "module_id": request.module_id,
        }
    config = config_store.get_config()
    agent_instructions = ""
    if config.get("active_agent_id"):
        agent = config_store.get_agent(config["active_agent_id"])
        if agent:
            agent_instructions = f"Custom Persona Instructions:\n{agent['instructions']}\n\n"
            
    system = (
        "You are a CRM-integrated AI sales assistant for sales representatives. "
        f"{agent_instructions}"
        "Answer using the uploaded company knowledge base. If the answer is not present in the context, "
        "say you do not have enough information from the uploaded documents."
    )
    crm_context = request.crm_context or {}
    prompt = (
        f"Knowledge Base Context:\n{context}\n\n"
        f"CRM Context:\n{crm_context}\n\n"
        f"Sales Rep Question:\n{request.message}"
    )
    response = llm_client.generate([{"role": "user", "content": prompt}], system=system)
    return {"response": response, "module_id": request.module_id}


@app.get("/api/test/start", response_model=QuestionListResponse)
async def start_evaluation(module_id: str | None = Query(default=None)):
    _validate_module_id(module_id)
    context = rag_engine.retrieve_context("Company product features overview target audience", top_k=5, module_id=module_id)
    if not context.strip():
        raise HTTPException(status_code=400, detail="Knowledge base is empty. Please upload documents first.")
    questions = evaluator.generate_questions(context, num_questions=3)
    return {"questions": questions, "module_id": module_id}


@app.post("/api/test/evaluate", response_model=EvalResponse)
async def evaluate_answer(request: EvalRequest):
    _validate_module_id(request.module_id)
    context = rag_engine.retrieve_context(request.question, module_id=request.module_id)
    if request.module_id and not context.strip():
        raise HTTPException(status_code=400, detail="Knowledge base module has no relevant indexed content for this question.")
    result = evaluator.evaluate_answer(request.question, request.answer, context)
    result["module_id"] = request.module_id
    return result


@app.post("/api/mock-call/start", response_model=MockCallStartResponse)
async def start_mock_call(request: MockCallStartRequest):
    _validate_module_id(request.module_id)
    try:
        session = await livekit_service.create_mock_call_session(request.sales_rep_id, request.module_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return session


@app.post("/api/mock-call/evaluate", response_model=MockCallEvalResponse)
async def evaluate_mock_call(request: MockCallEvaluateRequest):
    _validate_module_id(request.module_id)
    
    v_transcript = request.voice_transcript or request.transcript or "No voice transcript."
    c_transcript = request.chat_transcript or "No chat transcript."
    
    # Fetch the actual "crux" of the documents
    context = rag_engine.get_all_context_for_module(request.module_id, max_chars=15000)
    if not context.strip():
        raise HTTPException(status_code=400, detail="Knowledge base module has no indexed content. Upload documents first.")

    result = evaluator.evaluate_full_session(c_transcript, v_transcript, context)

    final_score, hiring_decision = evaluator.combine_scores(result["voice_score"], result["chat_score"])
    
    config = config_store.get_config()
    agent_id = config.get("active_agent_id")

    mock_call_history_store.add(
        {
            "session_id": request.session_id,
            "module_id": request.module_id,
            "agent_id": agent_id,
            "transcript": v_transcript, # keep naming for old frontend UI if needed
            "text_question": "Chat Transcript Graded",
            "text_answer": c_transcript,
            "voice_score": result["voice_score"],
            "text_score": result["chat_score"],
            "final_score": final_score,
            "product_accuracy": result["product_accuracy"],
            "discovery": result["discovery"],
            "objection_handling": result["objection_handling"],
            "empathy": result["empathy"],
            "closing_clarity": result["closing_clarity"],
            "voice_feedback": result["voice_feedback"],
            "text_feedback": result["chat_feedback"],
            "hiring_decision": hiring_decision,
        }
    )

    return {
        "final_score": final_score,
        "voice_score": result["voice_score"],
        "text_score": result["chat_score"],
        "product_accuracy": result["product_accuracy"],
        "discovery": result["discovery"],
        "objection_handling": result["objection_handling"],
        "empathy": result["empathy"],
        "closing_clarity": result["closing_clarity"],
        "voice_feedback": result["voice_feedback"],
        "text_feedback": result["chat_feedback"],
        "module_id": request.module_id,
        "hiring_decision": hiring_decision,
    }


@app.get("/api/mock-call/history", response_model=MockCallHistoryResponse)
async def list_mock_call_history(module_id: str | None = Query(default=None), session_id: str | None = Query(default=None)):
    if module_id is not None:
        _validate_module_id(module_id)
    return {"records": mock_call_history_store.list(module_id=module_id, session_id=session_id)}


# ── Admin: Session Transcripts ────────────────────────────────────────────────

@app.get("/api/admin/sessions", include_in_schema=True)
async def list_sessions():
    """Admin only: List all voice mock call sessions with their transcript status."""
    sessions = livekit_service.session_store.list_sessions() if hasattr(livekit_service, 'session_store') else []
    from core.livekit_session_store import livekit_session_store as _sess_store
    sessions = _sess_store.list_sessions()
    # Return session metadata without the full kb_context to keep payload small
    return {
        "sessions": [
            {
                "room_name": s.get("room_name"),
                "session_id": s.get("session_id"),
                "module_id": s.get("module_id"),
                "sales_rep_id": s.get("sales_rep_id"),
                "agent_dispatched": s.get("agent_dispatched"),
                "created_at": s.get("created_at"),
                "has_transcript": bool(s.get("voice_transcript")),
                "transcript_turns": len(s.get("voice_transcript") or []),
            }
            for s in sessions
        ]
    }


@app.get("/api/admin/sessions/{room_name}/transcript", include_in_schema=True)
async def get_session_transcript(room_name: str):
    """Admin only: Get the full voice call transcript for a specific session."""
    from core.livekit_session_store import livekit_session_store as _sess_store
    session = _sess_store.get_by_room_name(room_name)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    transcript = session.get("voice_transcript")
    return {
        "room_name": room_name,
        "session_id": session.get("session_id"),
        "module_id": session.get("module_id"),
        "sales_rep_id": session.get("sales_rep_id"),
        "created_at": session.get("created_at"),
        "transcript": transcript or [],
        "transcript_available": bool(transcript),
    }


@app.post("/api/sessions/{room_name}/transcript", include_in_schema=True)
async def save_session_transcript(room_name: str, payload: dict):
    """
    Called by the voice_agent_worker.py after a call ends to persist the transcript.
    Payload: {"transcript": [{"role": "Rep", "text": "..."}, ...]}
    """
    from core.livekit_session_store import livekit_session_store as _sess_store
    transcript = payload.get("transcript", [])
    if not isinstance(transcript, list):
        raise HTTPException(status_code=400, detail="'transcript' must be a list of turn objects.")
    _sess_store.save_transcript(room_name, transcript)
    logger.info("Transcript saved via API for room: %s (%d turns)", room_name, len(transcript))
    return {"status": "saved", "turns": len(transcript)}


def _is_supported_file(filename: str | None) -> bool:
    if not filename:
        return False
    return filename.lower().endswith((".pdf", ".txt", ".md"))


def _validate_module_id(module_id: str | None) -> None:
    if module_id and not document_store.get_module(module_id):
        raise HTTPException(status_code=404, detail="Knowledge base module not found.")


@app.get("/api/learn/curriculum", response_model=CurriculumResponse)
async def generate_curriculum(module_id: str = Query(...)):
    _validate_module_id(module_id)
    context = rag_engine.get_all_context_for_module(module_id)
    if not context.strip():
        raise HTTPException(status_code=400, detail="Knowledge base module has no indexed content. Upload documents first.")
    
    system = "You are an expert Sales Training Manager creating a structured learning curriculum."
    prompt = (
        f"Based on the following comprehensive knowledge base documents for this training module, create a structured 'Learning Curriculum and Product Guide' for a new sales representative.\n"
        f"Break it down into:\n"
        f"1. Core Concepts & Value Proposition\n"
        f"2. Product Features & Specs\n"
        f"3. Target Audience & Personas\n"
        f"4. Common Objections & How to Handle Them\n"
        f"5. Key Discovery Questions to Ask\n\n"
        f"Use clean markdown formatting. Keep it engaging, easy to read, and highly focused on sales execution.\n\n"
        f"Knowledge Base Content:\n{context}"
    )
    
    logger.info("Generating curriculum for module %s", module_id)
    response = llm_client.generate([{"role": "user", "content": prompt}], system=system)
    
    return {"curriculum": response, "module_id": module_id}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
