# AI Sales Trainer Agent

An AI-powered sales training and evaluation platform with voice mock calls, structured learning paths, and real-time performance scoring.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [Frontend Interfaces](#frontend-interfaces)
- [Backend API Reference](#backend-api-reference)
- [Core Modules](#core-modules)
- [Training Flow](#training-flow)
- [Admin Operations](#admin-operations)
- [Troubleshooting](#troubleshooting)

---

## Overview

Sales Trainer Agent is a fully integrated platform that trains sales representatives through a 4-step structured program:

1. **Learn** — AI generates a study guide from uploaded product documents
2. **Deep-Dive Coaching** — Interactive AI tutor provides scenario-based coaching
3. **Voice Mock Call** — Live voice conversation with an AI prospect via LiveKit
4. **Evaluation** — AI scores performance across 5 dimensions with hire/no-hire decision

The platform supports multi-tenant courses, customizable AI prospect personas, sequential gating (learners must complete each step before advancing), admin approval workflows, and token usage tracking.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        Frontend (HTML/JS)                      │
│  ┌──────────────┐  ┌───────────────────┐  ┌────────────────┐  │
│  │ index.html   │  │ admin-console.html│  │ admin.html     │  │
│  │ Learner      │  │ Full Admin Console│  │ (Legacy Admin) │  │
│  └──────┬───────┘  └────────┬──────────┘  └────────────────┘  │
└─────────┼──────────────────┼──────────────────────────────────┘
          │ HTTP REST        │
┌─────────▼──────────────────▼──────────────────────────────────┐
│              FastAPI Backend (main.py :8000)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ RAG      │ │ LLM      │ │ Evaluator│ │ LiveKit Service  │  │
│  │ Engine   │ │ Client   │ │          │ │ (dispatch agent) │  │
│  └────┬─────┘ └────┬─────┘ └──────────┘ └────────┬─────────┘  │
│       │             │                              │            │
│  ChromaDB      Anthropic Claude              LiveKit Cloud      │
│  (local)       (API)                         (WebRTC)           │
└─────────────────────────────────────────────────────────────────┘
          ║ (Separate Process)
┌─────────╨─────────────────────────────────────────────────────┐
│         Voice Agent Worker (voice_agent_worker.py :8081)       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Silero   │ │ ElevenL. │ │ Cartesia │ │ Anthropic Claude │ │
│  │ VAD      │ │ STT      │ │ TTS      │ │ LLM              │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend Framework** | FastAPI + Uvicorn |
| **LLM** | Anthropic Claude (claude-haiku-4-5) |
| **Voice Pipeline** | LiveKit Agents SDK |
| **Speech-to-Text** | ElevenLabs STT |
| **Text-to-Speech** | Cartesia TTS (Sonic 3) |
| **Voice Activity Detection** | Silero VAD |
| **Vector Database** | ChromaDB (local) |
| **Embeddings** | sentence-transformers/all-MiniLM-L6-v2 |
| **Document Parsing** | PyMuPDF, PyPDF2, python-docx |
| **Frontend** | Vanilla HTML/CSS/JS (single-file apps) |

---

## Quick Start

### Prerequisites

- Python 3.11+
- API keys: Anthropic, ElevenLabs, Cartesia, LiveKit

### 1. Setup Environment

```bash
cd backend
cp .env.example .env   # Edit with your API keys
pip install -r requirements.txt
```

### 2. Start the Backend Server

```bash
# Terminal 1
cd backend
python main.py
# → Runs on http://localhost:8000
```

### 3. Start the Voice Agent Worker

```bash
# Terminal 2 (must run alongside main.py)
cd backend
python voice_agent_worker.py start
# → Registers with LiveKit Cloud, HTTP server on :8081
```

### 4. Access the Application

| URL | Description |
|-----|-------------|
| `http://localhost:8000` | Learner Portal (index.html) |
| `http://localhost:8000/admin/console` | Admin Console (admin-console.html) |
| `http://localhost:8000/admin` | Legacy Admin Panel (admin.html) |

> **Note:** If you get `OSError: [Errno 10048] port 8081 already in use`, kill the existing worker process before starting a new one.

---

## Environment Variables

Create a `backend/.env` file:

```env
# ── AI Models ──────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...
MODEL_NAME=claude-haiku-4-5-20251001

# ── Storage Paths ──────────────────────────────────────
VECTOR_DB_DIR=./chroma_db
UPLOAD_DIR=./uploads
KB_STORE_DIR=./kb_store

# ── LiveKit (Voice) ────────────────────────────────────
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxx
LIVEKIT_API_SECRET=your-secret
LIVEKIT_AGENT_NAME=sales-trainer-agent
LIVEKIT_PLAYGROUND_URL=https://agents-playground.livekit.io/

# ── Voice Providers ────────────────────────────────────
DEEPGRAM_API_KEY=your-deepgram-key
ELEVENLABS_API_KEY=sk_...
CARTESIA_API_KEY=sk_car_...
VOICE_STT_PROVIDER=elevenlabs
VOICE_TTS_PROVIDER=cartesia
```

---

## Project Structure

```
salestrainer/
├── backend/
│   ├── main.py                     # FastAPI app (all REST endpoints)
│   ├── voice_agent_worker.py       # LiveKit voice agent worker (separate process)
│   ├── config.py                   # Environment variable loading
│   ├── requirements.txt            # Python dependencies
│   ├── .env                        # API keys and config (git-ignored)
│   ├── test_backend_apis.py        # API tests
│   └── core/
│       ├── agent_store.py          # AI agent persona CRUD + prompt compilation
│       ├── atomic_json.py          # Thread-safe JSON file I/O
│       ├── config_store.py         # Global admin config (module, agent, timer)
│       ├── course_store.py         # Course CRUD (create, publish, archive, duplicate)
│       ├── document_store.py       # KB module + document file management
│       ├── evaluator.py            # LLM-based scoring (5 dimensions + hire decision)
│       ├── livekit_service.py      # LiveKit room/token creation + agent dispatch
│       ├── livekit_session_store.py# Voice session metadata + transcript storage
│       ├── llm_client.py           # Anthropic Claude API wrapper
│       ├── mock_call_history_store.py # Evaluation result persistence
│       ├── progress_store.py       # Sequential step gating + approval workflow
│       ├── prompts.py              # All system prompts (Tier 1/2/3, Round 1/2)
│       ├── rag_engine.py           # ChromaDB + document chunking + retrieval
│       ├── rate_limiter.py         # IP-based rate limiting
│       ├── sales_trainer_agent.py  # Agent class for voice worker
│       └── token_tracker.py        # LLM token usage + cost tracking
├── frontend/
│   ├── index.html                  # Learner Portal (4-step training flow)
│   ├── admin-console.html          # Full Admin Console (10 tabs)
│   ├── admin.html                  # Legacy admin panel (to be deprecated)
│   └── widget/                     # Embeddable widget assets
├── chroma_db/                      # ChromaDB vector storage (git-ignored)
├── kb_store/                       # Uploaded documents (git-ignored)
├── uploads/                        # Temporary upload staging (git-ignored)
├── README.md                       # This file
├── BACKEND_LLD.md                  # Backend low-level design document
├── HOW_TO_OPERATE.md               # Step-by-step operating guide
└── .gitignore
```

---

## Frontend Interfaces

### Learner Portal (`index.html` → `/`)

The 4-step sequential training flow for sales reps:

| Step | Tab | Description |
|------|-----|-------------|
| 1 | Learn the Product | AI-generated study guide + Tier 1 Q&A chat tutor |
| 2 | Deep-Dive Coaching | Proactive Tier 2 structured walkthrough + follow-ups |
| 3 | Voice Mock Call | Round 1 (demo) + Round 2 (scored practice) via LiveKit |
| 4 | Get Evaluated | Submit transcript → AI scores → admin approval |

Steps are **sequentially gated** — each must be completed before the next unlocks.

### Admin Console (`admin-console.html` → `/admin/console`)

Full admin management interface with 10 tabs:

| Tab | Function |
|-----|----------|
| 📖 Guide | Step-by-step setup guide for managers |
| 📊 Dashboard | Performance overview, dimension averages, token cost |
| 🎓 Courses | CRUD courses (link KB modules + AI agents, set passing scores) |
| 📁 Materials | Create KB modules, upload/index/delete documents |
| 🤖 AI Agents | Create prospect personas (difficulty, objections, LLM params) |
| 📞 Transcripts | Review voice call transcripts with chat-bubble UI |
| ✅ Approvals | Approve/reject learner certifications |
| 🏆 Evaluations | Leaderboard with per-dimension scores + hire decisions |
| 📈 Token Usage | Per-session token consumption + cost tracking |
| ⚙️ Settings | Global config (active module, persona, assessment timer) |

---

## Backend API Reference

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Service health check with subsystem status |

### Knowledge Base

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/kb/modules` | List all KB modules |
| POST | `/api/kb/modules` | Create a new module |
| GET | `/api/kb/modules/{id}` | Get module details + documents |
| PATCH | `/api/kb/modules/{id}` | Update module name/description |
| POST | `/api/kb/modules/{id}/documents` | Upload & index a document (PDF/DOCX/TXT/MD) |
| DELETE | `/api/kb/modules/{id}/documents/{doc_id}` | Delete document + vectors |

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Multi-turn RAG chat (Tier 1 or Tier 2) |

### Learning

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/learn/curriculum?module_id=...` | Generate study curriculum from KB |

### Text Evaluation

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/test/start?module_id=...` | Generate discovery questions |
| POST | `/api/test/evaluate` | Score a text answer |

### Voice Mock Call

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/mock-call/start` | Create LiveKit room + dispatch agent |
| POST | `/api/mock-call/evaluate` | Score a transcript (5 dimensions + hire decision) |
| GET | `/api/mock-call/history` | List evaluation records |

### Global Config

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config` | Get global admin settings |
| POST | `/api/config` | Update global admin settings |

### Simple Agent Personas (legacy)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/agents` | List simple agent personas |
| POST | `/api/agents` | Create a simple agent persona |
| DELETE | `/api/agents/{id}` | Delete a simple agent persona |

### Admin: Courses

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/courses` | List all courses |
| POST | `/api/admin/courses` | Create a course |
| GET | `/api/admin/courses/{id}` | Get course details |
| PUT | `/api/admin/courses/{id}` | Update a course |
| DELETE | `/api/admin/courses/{id}` | Delete a course |
| POST | `/api/admin/courses/{id}/publish` | Set status to active |
| POST | `/api/admin/courses/{id}/archive` | Set status to archived |
| POST | `/api/admin/courses/{id}/duplicate` | Clone a course |
| POST | `/api/admin/courses/{id}/enroll` | Enroll a user |
| DELETE | `/api/admin/courses/{id}/enroll/{user_id}` | Unenroll a user |

### Admin: AI Agents (full)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/agents` | List all agent behaviours |
| POST | `/api/admin/agents` | Create a new agent |
| GET | `/api/admin/agents/{id}` | Get agent details |
| PUT | `/api/admin/agents/{id}` | Update agent config |
| DELETE | `/api/admin/agents/{id}` | Delete agent |
| GET | `/api/admin/agents/presets` | Get difficulty presets + objection list |
| POST | `/api/admin/agents/{id}/preview` | Preview compiled agent instructions |

### Admin: Evaluations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/evaluations` | List all evaluations |
| GET | `/api/admin/evaluations/stats` | Summary tiles (avg score, hire rate, dimensions) |
| GET | `/api/admin/evaluations/leaderboard` | Ranked trainee scores |

### Admin: Session Transcripts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/sessions` | List all voice sessions |
| GET | `/api/admin/sessions/{room}/transcript` | Get full call transcript |
| POST | `/api/sessions/{room}/transcript` | Save transcript (called by voice worker) |

### Admin: Token Usage

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/usage` | Token + cost summary |
| GET | `/api/admin/usage/by-session` | Per-session breakdown |
| GET | `/api/admin/usage/by-course` | Per-course breakdown |

### Admin: Approvals

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/approvals` | List pending approvals |
| POST | `/api/admin/approvals/decide` | Approve or reject a learner |

### Learner Progress

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/progress?sales_rep_id=...&course_id=...` | Get step completion status |
| POST | `/api/progress/complete` | Mark a step as completed |

---

## Core Modules

### RAG Engine (`core/rag_engine.py`)

- Loads PDF, DOCX, TXT, and MD documents
- Splits text into overlapping chunks (1000 chars, 200 overlap)
- Generates embeddings via `sentence-transformers/all-MiniLM-L6-v2`
- Stores vectors in ChromaDB with `module_id` + `document_id` metadata
- Retrieval scoped by module for multi-tenant isolation

### Evaluator (`core/evaluator.py`)

Scores mock call transcripts across 5 dimensions (each out of 10):

| Dimension | What It Measures |
|-----------|-----------------|
| **Product Accuracy** | Correct product knowledge from KB |
| **Discovery** | Quality of qualifying questions asked |
| **Objection Handling** | Response to prospect pushback |
| **Empathy / Communication** | Active listening, tone, rapport |
| **Closing Clarity** | Clear next steps with timeline |

Final score ≥ 7.0 → **Hire**, < 7.0 → **Do Not Hire**

### Voice Agent Worker (`voice_agent_worker.py`)

Separate process that:
- Registers with LiveKit Cloud as agent worker
- Receives dispatched jobs when a learner starts a mock call
- Runs a 5-phase prospect conversation protocol
- Captures transcript via event hooks
- Saves transcript back to backend via HTTP callback on shutdown

---

## Training Flow

### Manager Setup

```
Upload Documents → Create KB Module → Create Course → Link Module + Agent → Publish
```

### Learner Journey

```
Select Course → Step 1: Study Guide + Q&A → Step 2: Deep-Dive Coaching
  → Step 3: Voice Mock Call (Round 1 Demo, Round 2 Practice)
  → Step 4: Submit Transcript → AI Scores → Admin Reviews → Certified ✅
```

---

## Admin Operations

### Creating a Training Program

1. Go to **Admin Console** → **Materials** tab
2. Click **+ New Module**, give it a name
3. Select the module, upload product PDFs/docs
4. Go to **AI Agents** tab → **+ New Agent**
5. Configure difficulty, prospect role, objections
6. Go to **Courses** tab → **+ New Course**
7. Link the KB module and AI agent
8. Click **Publish** to make it available to learners

### Reviewing Learner Performance

1. **Transcripts** tab → View any call transcript
2. **Evaluations** tab → Leaderboard with scores
3. **Approvals** tab → Approve/reject certifications
4. **Token Usage** tab → Monitor API costs

### Global Settings

In the **Settings** tab, configure:
- **Active Training Module** — Forces all reps to use this module
- **Active AI Persona** — Default persona for chat and voice
- **Assessment Timer** — Time limit in minutes for assessments

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `OSError: port 8081 already in use` | Kill the existing voice worker process: `netstat -ano \| findstr 8081` then `taskkill /PID <pid> /F` |
| `ChromaDB errors` | Delete `chroma_db/` folder to reset the vector database |
| Voice calls not connecting | Verify `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` in `.env` |
| STT/TTS not working | Check `ELEVENLABS_API_KEY` and `CARTESIA_API_KEY` in `.env` |
| Documents not indexing | Ensure file is PDF, DOCX, TXT, or MD. Check backend logs for parsing errors |
| Admin console shows "offline" | Make sure `python main.py` is running on port 8000 |

---

## License

Proprietary — Internal use only.
