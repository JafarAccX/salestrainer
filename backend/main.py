from pathlib import Path as FsPath
from typing import Any, Literal
from collections import defaultdict

import logging
from fastapi import FastAPI, File, HTTPException, Path, Query, Request, UploadFile
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
from core import prompts
from core.course_store import course_store
from core.token_tracker import token_tracker
from core.agent_store import agent_store, DIFFICULTY_PRESETS, AVAILABLE_OBJECTIONS
from core.progress_store import progress_store
from core.rate_limiter import chat_limiter, mock_call_limiter, eval_limiter

# In-memory conversation history for multi-turn chat (keyed by session_id)
_chat_history: dict[str, list[dict[str, str]]] = defaultdict(list)
_MAX_HISTORY_TURNS = 10  # Keep last N exchanges per session

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
    session_id: str | None = None
    tier: int = 1  # 1 = learner Q&A, 2 = structured deep-dive
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
    round: int = 2  # 1 = AI counsellor demo, 2 = AI prospect (learner pitches)


class MockCallEvaluateRequest(BaseModel):
    session_id: str | None = None
    voice_transcript: str | None = None
    chat_transcript: str | None = None
    module_id: str | None = None
    round: int = 2  # 2 = Tier 3 Round 2 (strengths/priority output)
    transcript: str | None = None # backwards compat
    text_question: str | None = None # backwards compat
    text_answer: str | None = None # backwards compat


class HealthResponse(BaseModel):
    status: str
    service: str
    checks: dict[str, bool] | None = None


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
    strengths: str | None = None
    improvement_areas: str | None = None
    priority_focus: str | None = None


class MockCallHistoryResponse(BaseModel):
    records: list[dict[str, Any]]


class CourseCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    kb_module_id: str | None = None
    agent_id: str | None = None
    target_audience: str = ""
    passing_score: float = 7.0


class CourseUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    kb_module_id: str | None = None
    agent_id: str | None = None
    target_audience: str | None = None
    passing_score: float | None = None
    tier_sequence: list[str] | None = None
    tier_config: dict[str, Any] | None = None
    approval_required: bool | None = None
    assigned_users: list[str] | None = None


class EnrollRequest(BaseModel):
    user_id: str = Field(..., min_length=1)


class StepCompleteRequest(BaseModel):
    sales_rep_id: str = Field(..., min_length=1)
    course_id: str = Field(..., min_length=1)
    step: str = Field(..., description="tier1 | tier2 | tier3 | evaluation")


class ApprovalDecisionRequest(BaseModel):
    sales_rep_id: str = Field(..., min_length=1)
    course_id: str = Field(..., min_length=1)
    decision: str = Field(..., description="approved | rejected")
    note: str = ""


class AgentConfigRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    difficulty: str | None = None          # easy | medium | hard | custom
    base_instructions: str | None = None   # used when difficulty == custom
    prospect_profile: dict[str, Any] | None = None
    llm_settings: dict[str, Any] | None = None
    conversation_rules: dict[str, Any] | None = None
    tier3_round1_enabled: bool | None = None
    tier3_round2_enabled: bool | None = None
    status: str | None = None

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
    checks = {
        "anthropic_configured": bool(config_store.get_config() and rag_engine is not None),
        "chroma_db": False,
        "livekit_url": bool(getattr(__import__("config", fromlist=["config"]).config, "LIVEKIT_URL", None)),
        "anthropic_key": bool(getattr(__import__("config", fromlist=["config"]).config, "ANTHROPIC_API_KEY", None)),
    }
    try:
        # Verify ChromaDB is queryable
        rag_engine.vector_store.get(limit=1)
        checks["chroma_db"] = True
    except Exception:
        pass
    status = "ok" if all(checks.values()) else "degraded"
    return {"status": status, "service": "sales-trainer-backend", "checks": checks}


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

@app.get("/admin/console", include_in_schema=False)
async def frontend_admin_console():
    console_path = FsPath(__file__).resolve().parent.parent / "frontend" / "admin-console.html"
    if console_path.exists():
        return FileResponse(console_path)
    raise HTTPException(status_code=404, detail="Admin console not found.")

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


@app.post("/api/kb/modules", response_model=ModuleResponse)
async def create_module(request: ModuleRequest):
    return document_store.create_module(request.name, request.description)


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
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, TXT, and Markdown files are supported.")

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
async def chat_with_agent(request: ChatRequest, raw_request: Request):
    chat_limiter.check(raw_request)
    logger.info(
        "--> Received CHAT request (Tier %s): %s (Module: %s)",
        request.tier, request.message, request.module_id,
    )
    _validate_module_id(request.module_id)

    session_id = request.session_id or request.sales_rep_id or "default"
    history = _chat_history[session_id]
    is_first_turn = len(history) == 0

    # ── Context retrieval ─────────────────────────────────────────────────────
    # Tier 2 needs the full module picture; the proactive deep-dive (first turn)
    # pulls all KB content. Tier 1 and Tier 2 follow-ups use targeted retrieval.
    if request.tier == 2 and is_first_turn:
        context = rag_engine.get_all_context_for_module(request.module_id) if request.module_id else ""
    else:
        context = rag_engine.retrieve_context(request.message, module_id=request.module_id)

    if request.module_id and not context.strip():
        return {
            "response": "I do not have enough information from the uploaded documents in this knowledge base module to answer that.",
            "module_id": request.module_id,
        }

    # ── Select system prompt by tier ──────────────────────────────────────────
    if request.tier == 2:
        base_system = prompts.tier2_intro_system() if is_first_turn else prompts.tier2_followup_system()
    else:
        base_system = prompts.tier1_chat_system()

    config = config_store.get_config()
    agent_instructions = ""
    if config.get("active_agent_id"):
        agent = config_store.get_agent(config["active_agent_id"])
        if agent:
            agent_instructions = f"\n\nCustom Persona Instructions:\n{agent['instructions']}"

    system = base_system + agent_instructions
    crm_context = request.crm_context or {}

    # ── Build messages with conversation history ──────────────────────────────
    messages = []
    for turn in history[-_MAX_HISTORY_TURNS:]:
        messages.append(turn)

    current_prompt = (
        f"Knowledge Base Context:\n{context}\n\n"
        f"CRM Context:\n{crm_context}\n\n"
        f"Sales Rep Message:\n{request.message}"
    )
    messages.append({"role": "user", "content": current_prompt})

    # Tier 2 intro produces a long structured walkthrough — allow more tokens.
    max_tokens = 4096 if (request.tier == 2 and is_first_turn) else 2048
    response = llm_client.generate(
        messages,
        system=system,
        max_tokens=max_tokens,
        session_id=session_id,
        user_id=request.sales_rep_id,
    )

    # ── Save to history ───────────────────────────────────────────────────────
    history.append({"role": "user", "content": request.message})
    history.append({"role": "assistant", "content": response})
    if len(history) > _MAX_HISTORY_TURNS * 2:
        _chat_history[session_id] = history[-_MAX_HISTORY_TURNS * 2:]

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
async def start_mock_call(request: MockCallStartRequest, raw_request: Request):
    mock_call_limiter.check(raw_request)
    _validate_module_id(request.module_id)
    try:
        session = await livekit_service.create_mock_call_session(
            request.sales_rep_id, request.module_id, round_num=request.round
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return session


@app.post("/api/mock-call/evaluate", response_model=MockCallEvalResponse)
async def evaluate_mock_call(request: MockCallEvaluateRequest, raw_request: Request):
    eval_limiter.check(raw_request)
    _validate_module_id(request.module_id)

    v_transcript = request.voice_transcript or request.transcript or "No voice transcript."
    c_transcript = request.chat_transcript or "No chat transcript."

    # Fetch the actual "crux" of the documents
    context = rag_engine.get_all_context_for_module(request.module_id, max_chars=15000)
    if not context.strip():
        raise HTTPException(status_code=400, detail="Knowledge base module has no indexed content. Upload documents first.")

    config = config_store.get_config()
    agent_id = config.get("active_agent_id")

    # ── Tier 3 Round 2: voice-only counsellor assessment ──────────────────────
    if request.round == 2:
        result = evaluator.evaluate_round2_call(v_transcript, context)
        voice_score = result["voice_score"]
        hiring_decision = result["hiring_decision"]
        final_score = round(float(voice_score), 2)

        mock_call_history_store.add(
            {
                "session_id": request.session_id,
                "module_id": request.module_id,
                "agent_id": agent_id,
                "transcript": v_transcript,
                "voice_score": voice_score,
                "text_score": 0,
                "final_score": final_score,
                "product_accuracy": result["product_accuracy"],
                "discovery": result["discovery"],
                "objection_handling": result["objection_handling"],
                "empathy": result["empathy"],
                "closing_clarity": result["closing_clarity"],
                "voice_feedback": result["improvement_areas"],
                "strengths": result["strengths"],
                "priority_focus": result["priority_focus"],
                "hiring_decision": hiring_decision,
            }
        )

        return {
            "final_score": final_score,
            "voice_score": voice_score,
            "text_score": 0,
            "product_accuracy": result["product_accuracy"],
            "discovery": result["discovery"],
            "objection_handling": result["objection_handling"],
            "empathy": result["empathy"],
            "closing_clarity": result["closing_clarity"],
            "voice_feedback": result["improvement_areas"],
            "text_feedback": None,
            "module_id": request.module_id,
            "hiring_decision": hiring_decision,
            "strengths": result["strengths"],
            "improvement_areas": result["improvement_areas"],
            "priority_focus": result["priority_focus"],
        }

    # ── Legacy: combined chat + voice full-session evaluation ──────────────────
    result = evaluator.evaluate_full_session(c_transcript, v_transcript, context)

    final_score, hiring_decision = evaluator.combine_scores(result["voice_score"], result["chat_score"])

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
    return filename.lower().endswith((".pdf", ".txt", ".md", ".docx", ".doc"))


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

# ── Admin: Course Management ──────────────────────────────────────────────────

@app.get("/api/admin/courses")
async def list_courses():
    return {"courses": course_store.list_courses()}


@app.post("/api/admin/courses")
async def create_course(request: CourseCreateRequest):
    if request.kb_module_id:
        _validate_module_id(request.kb_module_id)
    course = course_store.create_course(
        name=request.name,
        description=request.description,
        kb_module_id=request.kb_module_id,
        agent_id=request.agent_id,
        target_audience=request.target_audience,
        passing_score=request.passing_score,
    )
    return course


@app.get("/api/admin/courses/{course_id}")
async def get_course(course_id: str):
    course = course_store.get_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


@app.put("/api/admin/courses/{course_id}")
async def update_course(course_id: str, request: CourseUpdateRequest):
    updates = request.model_dump(exclude_none=True)
    course = course_store.update_course(course_id, updates)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


@app.delete("/api/admin/courses/{course_id}")
async def delete_course(course_id: str):
    course = course_store.delete_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    return {"deleted_course": course}


@app.post("/api/admin/courses/{course_id}/publish")
async def publish_course(course_id: str):
    course = course_store.set_status(course_id, "active")
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


@app.post("/api/admin/courses/{course_id}/archive")
async def archive_course(course_id: str):
    course = course_store.set_status(course_id, "archived")
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


@app.post("/api/admin/courses/{course_id}/duplicate")
async def duplicate_course(course_id: str):
    clone = course_store.duplicate_course(course_id)
    if not clone:
        raise HTTPException(status_code=404, detail="Course not found.")
    return clone


@app.get("/api/admin/courses/{course_id}/enrollments")
async def list_enrollments(course_id: str):
    course = course_store.get_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    return {"course_id": course_id, "assigned_users": course.get("assigned_users", [])}


@app.post("/api/admin/courses/{course_id}/enroll")
async def enroll_user(course_id: str, request: EnrollRequest):
    course = course_store.enroll_user(course_id, request.user_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


@app.delete("/api/admin/courses/{course_id}/enroll/{user_id}")
async def unenroll_user(course_id: str, user_id: str):
    course = course_store.unenroll_user(course_id, user_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


# ── Admin: Evaluation Dashboard ───────────────────────────────────────────────

@app.get("/api/admin/evaluations")
async def list_evaluations(module_id: str | None = Query(default=None)):
    """All evaluation records, newest first."""
    records = mock_call_history_store.list(module_id=module_id)
    records = sorted(records, key=lambda r: r.get("created_at", ""), reverse=True)
    return {"evaluations": records, "count": len(records)}


@app.get("/api/admin/evaluations/stats")
async def evaluation_stats():
    """Overview tiles + per-dimension averages for charts."""
    records = mock_call_history_store.list()
    total = len(records)

    def _avg(key):
        vals = [float(r[key]) for r in records if r.get(key) not in (None, 0)]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    passing = [r for r in records if float(r.get("final_score") or 0) >= 7.0]
    hire_rate = round((len(passing) / total) * 100, 1) if total else 0.0

    return {
        "total_evaluations": total,
        "avg_final_score": _avg("final_score"),
        "hire_rate_percent": hire_rate,
        "hire_count": len(passing),
        "dimension_averages": {
            "product_accuracy": _avg("product_accuracy"),
            "discovery": _avg("discovery"),
            "objection_handling": _avg("objection_handling"),
            "empathy": _avg("empathy"),
            "closing_clarity": _avg("closing_clarity"),
        },
    }


@app.get("/api/admin/evaluations/leaderboard")
async def evaluation_leaderboard(module_id: str | None = Query(default=None)):
    """Trainees ranked by final score (highest first)."""
    records = mock_call_history_store.list(module_id=module_id)
    ranked = sorted(records, key=lambda r: float(r.get("final_score") or 0), reverse=True)
    leaderboard = []
    for i, r in enumerate(ranked, start=1):
        leaderboard.append({
            "rank": i,
            "session_id": r.get("session_id"),
            "module_id": r.get("module_id"),
            "final_score": r.get("final_score"),
            "product_accuracy": r.get("product_accuracy"),
            "discovery": r.get("discovery"),
            "objection_handling": r.get("objection_handling"),
            "empathy": r.get("empathy"),
            "closing_clarity": r.get("closing_clarity"),
            "hiring_decision": r.get("hiring_decision"),
            "created_at": r.get("created_at"),
        })
    return {"leaderboard": leaderboard}


# ── Admin: Token Usage & Cost ─────────────────────────────────────────────────

@app.get("/api/admin/usage")
async def usage_summary():
    """Token + cost summary tiles."""
    return token_tracker.summary()


@app.get("/api/admin/usage/by-session")
async def usage_by_session():
    return {"sessions": token_tracker.by_session()}


@app.get("/api/admin/usage/by-course")
async def usage_by_course():
    return {"courses": token_tracker.by_course()}


# ── Admin: AI Agent Behaviour Configuration ───────────────────────────────────

@app.get("/api/admin/agents/presets")
async def agent_presets():
    """Difficulty presets + available objection types for the editor UI."""
    return {
        "difficulties": {
            k: {"description": v["description"], "num_objections": v["num_objections"]}
            for k, v in DIFFICULTY_PRESETS.items()
        },
        "available_objections": AVAILABLE_OBJECTIONS,
    }


@app.get("/api/admin/agents")
async def list_admin_agents():
    return {"agents": agent_store.list_agents()}


@app.post("/api/admin/agents")
async def create_admin_agent(request: AgentConfigRequest):
    data = request.model_dump(exclude_none=True)
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="Agent name is required.")
    return agent_store.create_agent(data)


@app.get("/api/admin/agents/{agent_id}")
async def get_admin_agent(agent_id: str):
    agent = agent_store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent


@app.put("/api/admin/agents/{agent_id}")
async def update_admin_agent(agent_id: str, request: AgentConfigRequest):
    agent = agent_store.update_agent(agent_id, request.model_dump(exclude_none=True))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent


@app.delete("/api/admin/agents/{agent_id}")
async def delete_admin_agent(agent_id: str):
    agent = agent_store.delete_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return {"deleted_agent": agent}


@app.post("/api/admin/agents/{agent_id}/preview")
async def preview_admin_agent(agent_id: str):
    """Returns the compiled prospect instructions so admins can review before publishing."""
    agent = agent_store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    instructions = agent_store.build_instructions(agent, kb_context="", module_name="(preview)")
    return {"agent_id": agent_id, "compiled_instructions": instructions}


# ── Learner Progress & Sequential Gating ──────────────────────────────────────

@app.get("/api/progress")
async def get_progress(sales_rep_id: str = Query(...), course_id: str = Query(...)):
    """Returns step lock/unlock/complete status + approval state for a learner+course."""
    return progress_store.get(sales_rep_id, course_id)


@app.post("/api/progress/complete")
async def complete_progress_step(request: StepCompleteRequest):
    rec = progress_store.complete_step(request.sales_rep_id, request.course_id, request.step)
    if rec is None:
        raise HTTPException(status_code=400, detail="Invalid step.")
    return rec


# ── Admin: Approval Queue ─────────────────────────────────────────────────────

@app.get("/api/admin/approvals")
async def list_approvals():
    """Pending evaluation approvals awaiting admin sign-off."""
    pending = progress_store.list_pending_approvals()
    return {"pending": pending, "count": len(pending)}


@app.post("/api/admin/approvals/decide")
async def decide_approval(request: ApprovalDecisionRequest):
    if request.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'.")
    rec = progress_store.set_approval(
        request.sales_rep_id, request.course_id, request.decision, request.note
    )
    if rec is None:
        raise HTTPException(status_code=404, detail="Progress record not found.")
    return rec


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
