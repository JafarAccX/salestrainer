# 🧠 AI Sales Trainer — Project Analysis

> **A fully integrated, AI-powered sales roleplay and evaluation platform**
> Built for onboarding and assessing sales representatives through voice and text mock calls.

---

## 📁 Repository Structure

```
salestrainer/
├── backend/                  ← FastAPI server + LiveKit voice worker
│   ├── core/                 ← Core service modules (RAG, LLM, LiveKit, Eval…)
│   ├── main.py               ← REST API entrypoint (517 lines)
│   ├── voice_agent_worker.py ← Standalone LiveKit voice agent process
│   ├── config.py             ← Centralised env/config loader
│   ├── requirements.txt      ← Python dependencies
│   └── .env                  ← Secrets (API keys, URLs)
├── frontend/
│   ├── index.html            ← Sales Rep SPA (37 KB)
│   ├── admin.html            ← Admin/Manager SPA (37 KB)
│   └── widget/
│       ├── widget.js         ← Embeddable CRM widget
│       └── widget.css        ← Widget styles
├── external/
│   └── agents-main/          ← Vendored LiveKit agents SDK
│       ├── livekit-agents/   ← Core agent framework
│       └── livekit-plugins/  ← 72+ provider plugins
├── HOW_TO_OPERATE.md
├── README.md
└── pyrightconfig.json
```

---

## 🏗️ Architecture Overview

The platform runs as **three independent processes**:

```
┌──────────────────────────┐     HTTP REST      ┌──────────────────────┐
│   Frontend (HTML/JS)     │ ◄────────────────► │  FastAPI Backend     │
│   index.html / admin.html│                    │  main.py (:8000)     │
└──────────────────────────┘                    └──────────┬───────────┘
                                                           │
                              LiveKit Cloud ◄──────────────┤
                                  │                        │
                                  ▼                        ▼
                      ┌────────────────────┐   ┌──────────────────────┐
                      │  Voice Agent Worker │   │  ChromaDB (local)    │
                      │  voice_agent_worker │   │  + kb_store/         │
                      │  .py (LiveKit SDK) │   │  (vector embeddings) │
                      └────────────────────┘   └──────────────────────┘
```

### External Services Used

| Service | Purpose | Provider |
|---|---|---|
| **Anthropic Claude** | LLM for chat, eval, curriculum | `claude-haiku-4-5-20251001` |
| **LiveKit Cloud** | Real-time voice call infrastructure | `wss://sound-jeyr1n4k.livekit.cloud` |
| **ElevenLabs** | Speech-to-Text (STT) | `elevenlabs.STT` |
| **Cartesia** | Text-to-Speech (TTS) | `sonic-3` model, voice ID set |
| **Silero** | Voice Activity Detection (VAD) | local model |
| **ChromaDB** | Local vector database for RAG | `./chroma_db` |
| **SentenceTransformers** | Embedding model for RAG | `all-MiniLM-L6-v2` |

---

## 🔧 Backend — Core Modules

### `main.py` — API Layer
- **Framework:** FastAPI with CORS middleware (allows all origins)
- **Serves:** REST API on port `8000` and serves the frontend HTML directly
- **Pydantic models:** Fully typed request/response schemas
- Key routes:

| Route | Method | Description |
|---|---|---|
| `/` | GET | Serves `frontend/index.html` |
| `/admin` | GET | Serves `frontend/admin.html` |
| `/api/health` | GET | Health check |
| `/api/config` | GET/POST | Read/update global config (active module, agent, timer) |
| `/api/agents` | GET/POST/DELETE | Manage AI persona agents |
| `/api/kb/modules` | GET/POST | List/create knowledge base modules |
| `/api/kb/modules/{id}` | GET/PATCH/DELETE | Module CRUD |
| `/api/kb/modules/{id}/documents` | POST/DELETE | Upload/delete documents |
| `/api/chat` | POST | RAG-grounded sales assistant chat |
| `/api/test/start` | GET | Generate 3 sales assessment questions |
| `/api/test/evaluate` | POST | Score a text answer (0–10) |
| `/api/mock-call/start` | POST | Create LiveKit room & token |
| `/api/mock-call/evaluate` | POST | Score full call transcript |
| `/api/mock-call/history` | GET | Retrieve past scored sessions |
| `/api/learn/curriculum` | GET | Generate structured study guide |
| `/api/admin/sessions` | GET | List all voice sessions (admin) |
| `/api/admin/sessions/{room}/transcript` | GET | Get session transcript |
| `/api/sessions/{room}/transcript` | POST | Worker saves transcript post-call |

---

### `core/document_store.py` — Knowledge Base Manager
- Manages **modules** and **documents** using a JSON metadata store (`kb_store/modules.json`)
- Documents stored under `kb_store/{module_id}/`
- Tracks: filename, content type, size, status (`pending`, `indexed`, `failed`), chunk count
- CRUD: create / get / update / delete modules; add / delete / mark documents

---

### `core/rag_engine.py` — RAG Pipeline
- **Load:** PDF (`pypdf`), TXT, Markdown files
- **Split:** Overlapping text chunks (via LangChain splitter)
- **Embed:** `sentence-transformers/all-MiniLM-L6-v2`
- **Store:** ChromaDB, scoped by `module_id` + `document_id` metadata
- **Retrieve:** `retrieve_context(query, module_id, top_k)` — cosine similarity search
- **Bulk retrieve:** `get_all_context_for_module(module_id, max_chars=15000)` for curriculum/eval

---

### `core/llm_client.py` — LLM Abstraction
- Wraps the **Anthropic Messages API**
- Single `generate(messages, system)` method
- Default model: `claude-haiku-4-5-20251001` (configurable via `.env`)
- Centralises all LLM calls: chat, question gen, evaluation, curriculum

---

### `core/evaluator.py` — Scoring Engine
- **`generate_questions(context, num=3)`** — generates sales discovery questions from KB context
- **`evaluate_answer(question, answer, context)`** → `{score: float, feedback: str}` (0–10)
- **`evaluate_full_session(chat_transcript, voice_transcript, context)`** → multi-dimensional scores:
  - `product_accuracy`, `discovery`, `objection_handling`, `empathy`, `closing_clarity`
  - `voice_score`, `chat_score`
- **`combine_scores(voice, chat)`** → `(final_score, hiring_decision)`
  - Threshold: **7.0/10** → `"Hire"` or `"Do Not Hire"`

---

### `core/livekit_service.py` — Voice Session Manager
- Creates LiveKit room metadata and participant access tokens
- Declares voice pipeline: STT → LLM → TTS
- Stores `module_id`, `kb_context` into `livekit_session_store` keyed by `room_name`
- Worker looks up KB context on job start using the room name

---

### `core/livekit_session_store.py` — Session Registry
- In-memory (or persisted) store: one record per LiveKit room
- Fields: `room_name`, `session_id`, `module_id`, `sales_rep_id`, `kb_context`, `voice_transcript`
- `save_transcript(room_name, turns)` — called by worker on shutdown

---

### `core/config_store.py` — Global Config
- Stores: `active_module_id`, `active_agent_id`, `timer_minutes`, custom agents list
- `create_agent(id, name, instructions)` — admin can define custom AI personas
- Custom personas override the default 5-phase protocol prompt

---

### `core/mock_call_history_store.py` — History Log
- Persists scored mock-call results (in-memory list)
- Filterable by `module_id` and `session_id`
- Fields: transcript, voice/text/final scores, all 5 rubric scores, hiring decision

---

## 🎙️ Voice Agent Worker — `voice_agent_worker.py`

A **separate Python process** (not part of FastAPI) using the LiveKit Agents SDK.

### Plugin Stack
```python
LLM  → anthropic.LLM(model="claude-haiku-4-5-20251001")
STT  → elevenlabs.STT(api_key=...)
TTS  → cartesia.TTS(model="sonic-3", voice="f786b574-...")
VAD  → silero.VAD.load()
```

### 5-Phase Assessment Protocol
The agent acts as a **realistic prospect**, guiding the call through:

| Phase | Focus |
|---|---|
| **1 — Product Knowledge** | Tests if rep knows product features, ICP, differentiators |
| **2 — Discovery** | Tests if rep proactively asks qualifying questions |
| **3 — Objection Handling** | Raises 2+ realistic objections (price, competition, approval) |
| **4 — Communication** | Assessed throughout: clarity, listening, no jargon |
| **5 — Closing** | Tests if rep confidently asks for the next step |

### Transcript Capture
- Hooks into `user_speech_committed` and `agent_speech_committed` session events
- Fallback: reads from `session.chat_ctx.messages` if events don't fire
- On shutdown: saves to `livekit_session_store` via `save_transcript()`

---

## 🌐 Frontend

### `frontend/index.html` — Sales Rep Portal (Single-Page App)
**Tabs:**
1. **Knowledge Base** — Create modules, upload PDFs/TXTs/MDs, manage documents
2. **Learning Hub** — Generate AI curriculum from uploaded documents
3. **AI Chat Assistant** — RAG-grounded text chat with the sales AI
4. **Voice Mock Call** — Start a LiveKit session, launch the playground
5. **Evaluation Dashboard** — Paste transcript, generate score + hiring decision

**Sidebar:**
- Module selector dropdown (synced globally)
- Assessment Timer (countdown, locks access on expiry)
- Call history viewer

### `frontend/admin.html` — Admin/Manager Portal
- Manage knowledge base modules
- Configure active module, active agent, timer defaults
- Create/delete custom AI agent personas with custom instructions
- View all voice sessions and transcripts

### `frontend/widget/` — CRM Embeddable Widget
- `widget.js` + `widget.css` — lightweight embed for integration into CRM dashboards
- Provides quick access to the sales assistant without leaving the CRM

---

## 📦 External — `external/agents-main/`

A **vendored copy of the LiveKit Agents monorepo** providing:
- `livekit-agents/` — Core SDK: `Agent`, `AgentSession`, `JobContext`, `WorkerOptions`, `cli`
- `livekit-plugins/` — 72+ provider plugins including:
  - AI/LLM: `openai`, `anthropic`, `google`, `groq`, `mistralai`, `xai`, `cerebras`
  - STT: `deepgram`, `elevenlabs`, `assemblyai`, `azure`, `aws`, `gladia`
  - TTS: `cartesia`, `elevenlabs`, `lmnt`, `minimax`, `neuphonic`
  - VAD: `silero`, `turn-detector`
  - Avatars: `tavus`, `hedra`, `simli`, `did`, `anam`

---

## 🔑 Environment Variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude LLM access |
| `MODEL_NAME` | Claude model (default: `claude-haiku-4-5-20251001`) |
| `VECTOR_DB_DIR` | ChromaDB path (default: `./chroma_db`) |
| `UPLOAD_DIR` | Temp upload staging path |
| `KB_STORE_DIR` | Persistent document + metadata store |
| `LIVEKIT_URL` | LiveKit cloud WSS URL |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `LIVEKIT_AGENT_NAME` | Worker registration name |
| `LIVEKIT_PLAYGROUND_URL` | LiveKit playground URL for frontend link |
| `DEEPGRAM_API_KEY` | (Optional) Deepgram STT key |
| `ELEVENLABS_API_KEY` | ElevenLabs STT key |
| `CARTESIA_API_KEY` | Cartesia TTS key |
| `VOICE_STT_PROVIDER` | STT provider selection (`elevenlabs`) |
| `VOICE_TTS_PROVIDER` | TTS provider selection (`cartesia`) |

---

## 🔄 Key Data Flows

### 1. Document Upload & Indexing
```
Admin uploads PDF/TXT/MD
  → FastAPI validates file type
  → DocumentStore saves file to kb_store/{module_id}/
  → RAGEngine.process_document():
      → loads & splits text into overlapping chunks
      → generates embeddings (all-MiniLM-L6-v2)
      → stores vectors in ChromaDB with module_id + document_id metadata
  → DocumentStore marks document as "indexed"
```

### 2. AI Chat Assistant
```
Rep submits message + module_id
  → RAGEngine.retrieve_context(message, module_id)  [top-k similarity search]
  → If module_id set and no context found → "insufficient information" response
  → Fetch active agent persona (if set)
  → Build system + user prompt with KB context + CRM context
  → LLMClient.generate() → Claude response
  → Return grounded answer
```

### 3. Voice Mock Call — Full Lifecycle
```
Rep clicks "Start Mock Call"
  → POST /api/mock-call/start
      → LiveKitService creates room + participant token
      → Fetches KB context for module
      → Saves session to livekit_session_store
      → Returns room_name + token to frontend

Frontend opens LiveKit Playground
  → LiveKit dispatches job to voice_agent_worker.py
  → Worker reads kb_context from job metadata
  → Initialises SalesTrainerAgent with 5-phase prompt + KB context
  → AgentSession starts: Silero VAD detects speech → ElevenLabs STT → Claude → Cartesia TTS
  → Real-time voice conversation begins

On call end:
  → Worker shutdown callback fires
  → Transcript saved to livekit_session_store

Rep submits transcript for evaluation:
  → POST /api/mock-call/evaluate
  → RAGEngine.get_all_context_for_module() [full KB pull]
  → Evaluator.evaluate_full_session(chat_transcript, voice_transcript, context)
  → Scores: product_accuracy, discovery, objection_handling, empathy, closing_clarity
  → combine_scores() → final_score + hiring_decision (≥7.0 = "Hire")
  → Result saved to mock_call_history_store
  → Dashboard renders with animated score cards
```

### 4. Curriculum Generation
```
Rep clicks "Generate Curriculum"
  → GET /api/learn/curriculum?module_id=...
  → RAGEngine.get_all_context_for_module() [up to 15,000 chars]
  → Claude prompted as "Sales Training Manager"
  → Generates structured guide:
      1. Core Concepts & Value Proposition
      2. Product Features & Specs
      3. Target Audience & Personas
      4. Common Objections & Handling
      5. Key Discovery Questions
  → Returned as Markdown, rendered in frontend
```

---

## 🚀 Quick Start

```bash
# Terminal 1 — FastAPI Backend
cd backend
pip install -r requirements.txt
python main.py
# → http://localhost:8000

# Terminal 2 — LiveKit Voice Worker
cd backend
python voice_agent_worker.py start

# Access UI
# Sales Rep:  http://localhost:8000
# Admin:      http://localhost:8000/admin
```

---

## 📊 Scoring Rubric

| Dimension | Description |
|---|---|
| **Product Accuracy** | Does rep's knowledge match the uploaded KB documents? |
| **Discovery** | Did rep ask probing questions to uncover needs? |
| **Objection Handling** | Did rep address objections with empathy + KB-grounded answers? |
| **Empathy** | Was rep listening and adapting to the prospect's cues? |
| **Closing Clarity** | Did rep confidently propose a clear next step? |
| **Voice Score** | Composite of above from voice call transcript |
| **Chat Score** | Composite from text Q&A evaluation |
| **Final Score** | Weighted average of voice + chat scores (0–10) |
| **Hiring Decision** | `Hire` if final ≥ 7.0, else `Do Not Hire` |

---

## 🛠️ Python Dependencies

| Package | Role |
|---|---|
| `fastapi` + `uvicorn` | Web server |
| `pydantic` + `pydantic-settings` | Data validation & config |
| `anthropic` | Claude API client |
| `langchain` + `langchain-community` | Document loaders, text splitter |
| `langchain-huggingface` + `sentence-transformers` | Embedding model |
| `langchain-chroma` + `chromadb` | Vector database |
| `pypdf2` + `pypdf` | PDF parsing |
| `python-dotenv` | `.env` loading |
| `python-multipart` | File upload support |
| `livekit-api` | Token generation, REST API |
| `livekit-agents` | Voice agent worker framework |
| `livekit-plugins-anthropic` | Claude plugin for agents |
| `livekit-plugins-elevenlabs` | ElevenLabs STT plugin |
| `livekit-plugins-silero` | VAD plugin |

---

*Generated by project analysis — June 2026*
