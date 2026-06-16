# Sales Trainer Backend LLD

## Scope

This backend is designed to integrate with a company's CRM and provide:

- A ChatGPT-style sales assistant for sales reps.
- A persistent company knowledge base split into modules.
- Document upload, indexing, retrieval, and deletion.
- Text-based sales training questions and answer evaluation.
- Voice mock-call session setup through LiveKit.
- Score aggregation from AI voice-call evaluation and text evaluation.

## Main Components

### API Layer

File: `main.py`

Responsibilities:

- Expose REST APIs for CRM/frontend clients.
- Validate request payloads.
- Route work to document storage, RAG, LLM, evaluator, and LiveKit services.

### Knowledge Base Store

File: `core/document_store.py`

Responsibilities:

- Create, list, update, and delete knowledge-base modules.
- Store uploaded documents under `kb_store/{module_id}/`.
- Maintain module and document metadata in `kb_store/modules.json`.
- Preserve uploaded documents until an explicit delete operation is called.

### RAG Engine

File: `core/rag_engine.py`

Responsibilities:

- Load PDF, TXT, and Markdown documents.
- Split text into overlapping chunks.
- Generate embeddings using `sentence-transformers/all-MiniLM-L6-v2`.
- Persist vectors in ChromaDB.
- Scope retrieval and deletion by `module_id` and `document_id`.

### LLM Client

File: `core/llm_client.py`

Responsibilities:

- Call Anthropic Claude Messages API.
- Default model: `claude-haiku-4-5-20251001`.
- Centralize LLM generation for chat, question generation, and evaluation.

### Evaluator

File: `core/evaluator.py`

Responsibilities:

- Generate sales discovery questions from knowledge-base context.
- Evaluate text answers out of 10.
- Evaluate mock-call transcripts out of 10.
- Average voice and text scores into a final score.

### LiveKit Service

File: `core/livekit_service.py`

Responsibilities:

- Create LiveKit mock-call room/session metadata.
- Generate LiveKit participant tokens when credentials are configured.
- Declare the intended voice pipeline:
  - STT: ElevenLabs
  - LLM: Claude Haiku
  - TTS: ElevenLabs
- Persist the module-scoped knowledge context into a session registry so the worker can load it by room name.

### LiveKit Session Store

File: `core/livekit_session_store.py`

Responsibilities:

- Persist one session record per LiveKit room.
- Store `module_id`, `room_name`, and precomputed knowledge-base context.
- Let the worker resolve the correct KB context after joining the room.

### Mock Call History Store

File: `core/mock_call_history_store.py`

Responsibilities:

- Persist scored mock-call results.
- Store transcript, question/answer pair, voice score, text score, and final score.
- Expose history for CRM review through a read API.

The actual LiveKit voice agent worker runs as a separate process and loads the session record for the room it joined.

## API Surface

### Knowledge Base

- `POST /api/kb/modules`
- `GET /api/kb/modules`
- `GET /api/kb/modules/{module_id}`
- `PATCH /api/kb/modules/{module_id}`
- `DELETE /api/kb/modules/{module_id}`
- `POST /api/kb/modules/{module_id}/documents`
- `DELETE /api/kb/modules/{module_id}/documents/{document_id}`

### Chat Agent

- `POST /api/chat`

Request supports:

- `message`
- `module_id`
- `sales_rep_id`
- `crm_context`

### Text Test

- `GET /api/test/start?module_id=...`
- `POST /api/test/evaluate`

### Voice Mock Call

- `POST /api/mock-call/start`
- `POST /api/mock-call/evaluate`
- `GET /api/mock-call/history`

## Environment Variables

- `ANTHROPIC_API_KEY`
- `MODEL_NAME`
- `VECTOR_DB_DIR`
- `UPLOAD_DIR`
- `KB_STORE_DIR`
- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `LIVEKIT_AGENT_NAME`
- `DEEPGRAM_API_KEY`
- `ELEVENLABS_API_KEY`
- `VOICE_STT_PROVIDER`
- `VOICE_TTS_PROVIDER`

## Data Flow

### Document Upload

```text
CRM/Admin -> upload document -> DocumentStore saves file
  -> RAGEngine extracts text
  -> splitter creates chunks
  -> embeddings generated
  -> Chroma stores vectors with module_id/document_id metadata
```

### Sales Assistant Chat

```text
Sales Rep -> chat message + module_id
  -> RAGEngine retrieves module-scoped chunks
  -> Claude answers using retrieved context
  -> API returns grounded answer
```

### Voice Mock Call

```text
Sales Rep -> start mock call
  -> API creates LiveKit room/token
  -> LiveKit agent handles STT -> Claude -> TTS
  -> transcript submitted to /api/mock-call/evaluate
  -> evaluator scores transcript
  -> optional text score is averaged
  -> final score out of 10 returned
```
