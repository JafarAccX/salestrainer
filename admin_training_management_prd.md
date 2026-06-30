# 🛠️ Sales Trainer — Admin Training Management Module
## Product Requirements Document (PRD)

**Author:** Training Platform Team  
**Version:** 1.0  
**Date:** June 2026  
**Status:** Draft — awaiting approval  

---

## 1. Overview

### 1.1 Problem Statement

The current Sales Trainer admin experience (`/admin`) is a minimal single-page interface that only allows:
- Creating knowledge base modules
- Uploading documents
- Selecting an active module
- Creating a custom AI agent persona

This is insufficient for running a real training programme at scale. Managers have no way to:
- Define structured training **courses** with multi-tier progression
- Control **who can access** which courses
- See **real-time evaluation scores** across all trainees
- Configure **how the AI agent behaves** per course
- Set **call duration and token limits** to control costs
- Approve trainees before they advance to the next tier
- Push new product knowledge to the AI without touching code

### 1.2 Goal

Build a comprehensive **Admin Training Management Console** that gives admins full, code-free control over the entire training lifecycle — from course creation to evaluation sign-off.

### 1.3 Scope

| In Scope | Out of Scope |
|---|---|
| Course CRUD and configuration | Learner-facing UI redesign |
| Agent behaviour settings per course | Payment or billing integration |
| Live evaluation dashboard | Mobile app |
| KB / LLM data management | Multi-language support (v1) |
| Evaluation sequence rules | Calendar scheduling |
| Voice call settings | Video recordings |
| Token limiter and cost controls | SSO / LDAP |
| Approval workflows | |
| User & role management | |

---

## 2. User Roles

| Role | Description |
|---|---|
| **Super Admin** | Full access to all settings. Can create admins. |
| **Admin** | Can manage courses, agents, KB, approvals. Cannot change billing or create other admins. |
| **Manager** | Read-only access to evaluation scores for their team. Can approve tier advancement. |
| **Trainer (Learner)** | No admin access. Accesses the learner portal only. |

---

## 3. Feature Areas

---

## 3.1 — Course Management

### 3.1.1 Description
Admins create and manage **Courses**. Each course is an independent training programme centred on one product, service, or skill. Courses contain the 3-tier training progression.

### 3.1.2 Course Object

```json
{
  "id": "uuid",
  "name": "Generative AI Program — Sales Pitch",
  "description": "Train reps to pitch the GenAI programme to corporate HR teams.",
  "thumbnail_url": "...",
  "status": "draft | active | archived",
  "kb_module_id": "uuid",           // linked knowledge base module
  "target_audience": "SDRs, AEs",
  "passing_score": 7.0,             // minimum score to pass each tier
  "tier_sequence": ["tier1", "tier2", "tier3"],  // configurable order
  "tier_config": { ... },           // per-tier settings (see §3.5)
  "agent_id": "uuid",               // which AI agent persona to use
  "voice_settings_id": "uuid",      // which voice profile to use
  "token_policy_id": "uuid",        // which token limit policy to apply
  "approval_required": true,        // must manager approve to advance tiers?
  "assigned_users": ["uuid", ...],  // which trainers are enrolled
  "assigned_teams": ["team_id"],    // or by team
  "created_by": "uuid",
  "created_at": "iso8601",
  "updated_at": "iso8601"
}
```

### 3.1.3 UI — Course Management Page (`/admin/courses`)

**Course List View:**
- Table of all courses with columns: Name, Status badge (Draft/Active/Archived), Enrolled learners count, Avg score, Last updated
- Filters: Status, KB Module, Agent, Date range
- Actions: Create New, Edit, Archive, Duplicate, Preview (see as learner)

**Course Editor (drawer/modal):**
- **General tab:** Name, description, thumbnail upload, target audience text, status toggle
- **Content tab:** Select/link a KB Module (dropdown of existing modules), or create a new one inline
- **Training Flow tab:** Drag-and-drop tier sequencer — enable/disable tiers, set order (Tier 1 → 2 → 3 or custom)
- **Assignment tab:** Assign individual users or entire teams. Set enrollment deadline. Set course deadline.
- **Settings tab:** Passing score slider (0–10), approval required toggle, link to agent/voice/token policy

### 3.1.4 API — Course Endpoints

```
GET    /api/admin/courses                    # List all courses
POST   /api/admin/courses                    # Create course
GET    /api/admin/courses/{id}               # Get course detail
PUT    /api/admin/courses/{id}               # Update course
DELETE /api/admin/courses/{id}               # Archive course
POST   /api/admin/courses/{id}/publish       # Draft → Active
POST   /api/admin/courses/{id}/duplicate     # Clone a course
GET    /api/admin/courses/{id}/enrollments   # List enrolled learners
POST   /api/admin/courses/{id}/enroll        # Enroll users/teams
DELETE /api/admin/courses/{id}/enroll/{uid}  # Remove learner
```

---

## 3.2 — Agent Behaviour Configuration

### 3.2.1 Description
Each course can be linked to a custom **AI Agent Persona**. Admins control the agent's personality, difficulty level, objections it raises, speaking style, and the LLM model it uses.

### 3.2.2 Agent Config Object

```json
{
  "id": "uuid",
  "name": "Sceptical Corporate HR Manager",
  "description": "Challenging prospect persona for senior sales reps",
  "base_instructions": "You are a demanding corporate HR manager...",
  "difficulty": "easy | medium | hard | custom",
  "prospect_profile": {
    "role": "VP of HR",
    "company_size": "500-2000 employees",
    "pain_points": ["high attrition", "slow onboarding"],
    "objections": ["budget", "timing", "competitor", "trust"],
    "warmup_threshold": 2
  },
  "llm_settings": {
    "model": "claude-haiku-4-5-20251001",
    "temperature": 0.7,
    "max_tokens": 512,
    "top_p": 0.95
  },
  "conversation_rules": {
    "max_turns_before_decision": 12,
    "allow_hints": false,
    "auto_end_on_poor_performance": true,
    "poor_performance_threshold": 3
  },
  "tier3_round1_enabled": true,      // can this agent do the demo round?
  "tier3_round2_enabled": true,      // can this agent do the eval round?
  "status": "draft | active",
  "created_by": "uuid",
  "created_at": "iso8601"
}
```

### 3.2.3 Difficulty Presets

| Level | Behaviour |
|---|---|
| **Easy** | Friendly prospect, asks only 1 objection, very open to product info, warms up after 1 good question |
| **Medium** | Neutral, raises 2 objections, needs 2 good discovery answers to warm up |
| **Hard** | Guarded, raises 3 objections, pushes back on everything, will not warm up unless objections are handled with KB-backed proof |
| **Custom** | Admin writes custom instructions directly |

### 3.2.4 UI — Agent Configuration (`/admin/agents`)

- **Agent List:** Cards showing name, difficulty badge, linked courses count, status
- **Agent Editor:**
  - **Persona tab:** Name, description, prospect profile fields (role, company size, pain points)
  - **Difficulty tab:** Easy/Medium/Hard radio buttons OR custom textarea for instructions
  - **Objections tab:** Checkbox list of objection types (Budget, Timing, Competitor, Trust, ROI, Security). Drag to set priority order.
  - **LLM Settings tab:** Model selector, temperature slider (0-1), max_tokens input
  - **Conversation Rules tab:** Max turns, auto-end toggle, hint-allowed toggle
  - **Preview tab:** Chat with the agent live before publishing (sends to `/api/chat` with a test prompt)

### 3.2.5 API — Agent Endpoints

```
GET    /api/admin/agents                     # List agents
POST   /api/admin/agents                     # Create agent
GET    /api/admin/agents/{id}                # Get agent detail
PUT    /api/admin/agents/{id}                # Update agent
DELETE /api/admin/agents/{id}                # Delete agent
POST   /api/admin/agents/{id}/preview        # Test chat with agent
POST   /api/admin/agents/{id}/publish        # Draft → Active
```

---

## 3.3 — Live Evaluation Dashboard

### 3.3.1 Description
Real-time view of all trainees' scores across all courses. Admins and managers can watch evaluation results come in as trainees complete sessions, and drill into individual sessions.

### 3.3.2 Dashboard Sections

#### A. Overview Tiles (top of page)
| Tile | Data |
|---|---|
| Active Sessions | Count of trainees currently in a live voice call (Tier 3) |
| Sessions Today | Total training sessions started today |
| Avg Score Today | Mean final score across all completed evaluations today |
| Hire Rate | % of trainees scoring ≥ passing_score |
| Pending Approvals | Count of tier advancements waiting for manager sign-off |

#### B. Live Activity Feed
Real-time auto-refreshing (every 10s) table showing:
- Trainee name
- Course name
- Current tier (Tier 1 / 2 / 3 Round 1 / 3 Round 2)
- Status (In Progress / Completed / Awaiting Approval)
- Score (appears when evaluation is complete)
- Actions: View Transcript, Review, Approve Advancement

#### C. Score Leaderboard
- Ranked table of trainees by final score (highest → lowest)
- Filterable by: Course, Team, Date range, Tier
- Columns: Rank, Trainee Name, Course, Tier 3 Score, Product Accuracy, Discovery, Objection Handling, Empathy, Closing Clarity, Decision (Hire/Not Ready)
- Export to CSV

#### D. Score Breakdown Charts
- Radar chart: Average scores per dimension (ProductAccuracy, Discovery, etc.)
- Line chart: Score trend per trainee over multiple attempts
- Bar chart: Score distribution across all trainees (histogram)

#### E. Session Detail Drawer
Click any row → drawer opens showing:
- Session metadata (trainee, course, timestamp, round)
- Full voice call transcript (turn by turn)
- Score breakdown with individual dimension scores
- AI-generated feedback (Strengths, Improvement Areas, Priority Focus)
- Fact-check list (VERIFIED vs NOT IN KB claims)
- Admin override: manually adjust score + add note

### 3.3.3 API — Evaluation Dashboard Endpoints

```
GET  /api/admin/evaluations                  # List all evaluations (paginated)
GET  /api/admin/evaluations/live             # Live sessions (SSE stream or polling)
GET  /api/admin/evaluations/{session_id}     # Single session detail
PUT  /api/admin/evaluations/{session_id}/score  # Override score
GET  /api/admin/evaluations/stats            # Aggregate stats (tiles + charts)
GET  /api/admin/evaluations/leaderboard      # Ranked leaderboard
GET  /api/admin/evaluations/export           # CSV export
```

---

## 3.4 — Knowledge Base & LLM Data Management

### 3.4.1 Description
Full admin control over the product knowledge that the AI uses during all tiers. Admins can upload, preview, version, and approve KB documents before they go live to trainees.

### 3.4.2 Features

#### Document Management
- Upload PDF, TXT, MD files to a module
- View all uploaded documents with status: `pending_approval | indexing | active | failed | archived`
- Download original document
- View chunk preview: see exactly how the RAG engine split the document and what vectors were stored
- Delete document (removes from ChromaDB)

#### KB Preview (Test What the AI Knows)
- Input box: "Ask the AI a question about this module"
- Response shows: AI answer + "Grounded by:" list of the exact chunks that were retrieved
- This lets admin verify the AI answers correctly before enrolling trainees

#### Document Approval Workflow
When a new document is uploaded:
1. Status = `pending_approval`
2. Admin reviewer sees a diff/preview of the document content
3. Admin clicks Approve → status = `indexing` → RAG processes it → `active`
4. OR Reject → document is marked `rejected` with a rejection note

#### Version History
- Every module has a version history
- Each approved document upload creates a new version snapshot
- Admin can rollback to a previous version

### 3.4.3 KB Module Object (extended)

```json
{
  "id": "uuid",
  "name": "GenAI Programme — Sales KB",
  "description": "...",
  "version": 3,
  "documents": [
    {
      "id": "uuid",
      "filename": "product_overview.pdf",
      "status": "active",
      "chunk_count": 47,
      "uploaded_by": "uuid",
      "approved_by": "uuid",
      "uploaded_at": "iso8601",
      "approved_at": "iso8601"
    }
  ],
  "last_tested_at": "iso8601",
  "test_pass": true
}
```

### 3.4.4 API — KB Admin Endpoints

```
GET    /api/admin/kb/modules                         # List modules
POST   /api/admin/kb/modules                         # Create module
GET    /api/admin/kb/modules/{id}                    # Module detail + docs
PATCH  /api/admin/kb/modules/{id}                    # Update name/desc
DELETE /api/admin/kb/modules/{id}                    # Delete module + vectors
POST   /api/admin/kb/modules/{id}/documents          # Upload document (→ pending_approval)
GET    /api/admin/kb/modules/{id}/documents/{doc_id} # Document detail + chunks
DELETE /api/admin/kb/modules/{id}/documents/{doc_id} # Delete document
POST   /api/admin/kb/modules/{id}/documents/{doc_id}/approve  # Approve → index
POST   /api/admin/kb/modules/{id}/documents/{doc_id}/reject   # Reject with note
POST   /api/admin/kb/modules/{id}/test               # Run KB preview test
GET    /api/admin/kb/modules/{id}/chunks             # List indexed chunks
GET    /api/admin/kb/modules/{id}/history            # Version history
POST   /api/admin/kb/modules/{id}/rollback/{version} # Rollback to version
```

---

## 3.5 — Evaluation Sequence Configuration

### 3.5.1 Description
Admins define the exact rules for how a trainee progresses through the 3 tiers — which tiers are mandatory, minimum scores to advance, retake limits, timer settings, and what happens when they fail.

### 3.5.2 Tier Config Object (per-course)

```json
{
  "tier1": {
    "enabled": true,
    "mode": "chat_only | reading_only | both",
    "chat_settings": {
      "max_messages": 20,
      "require_completion_acknowledgment": true  // trainee must click "I'm ready to advance"
    },
    "reading_required": true,
    "reading_completion_tracking": true,    // track scroll/time-on-page
    "passing_score": null,                  // Tier 1 has no score — it's learning-only
    "requires_approval_to_advance": false
  },
  "tier2": {
    "enabled": true,
    "min_exchanges_before_advance": 5,       // must have at least 5 back-and-forth exchanges
    "require_all_phases_covered": true,      // AI must have covered all 4 phases (§ Prompt 2A)
    "passing_score": null,                   // Tier 2 also no formal score — learning
    "timer_minutes": null,                   // no hard time limit for learning tiers
    "requires_approval_to_advance": false
  },
  "tier3": {
    "enabled": true,
    "round1_enabled": true,                  // demo round (AI as counsellor)
    "round2_enabled": true,                  // eval round (user as counsellor)
    "timer_minutes": 10,                     // max call duration for round 2
    "max_attempts": 3,                       // max retakes of round 2
    "cooldown_minutes_between_attempts": 30, // wait time before retake
    "passing_score": 7.0,
    "auto_fail_on_hallucination": true,      // if LLM detects fabrication, score capped at 4
    "requires_approval_to_pass": true        // manager must sign off on Hire decision
  }
}
```

### 3.5.3 UI — Sequence Builder (`/admin/courses/{id}/sequence`)

Visual timeline editor:
```
[Tier 1: Product Training] → [Tier 2: Deep Learning] → [Tier 3: Mock Call]
       ↓ configure                    ↓ configure              ↓ configure
```

Each tier node is clickable and opens a side panel with:
- Enable/disable toggle
- Score threshold (slider 0–10 or "No score required")
- Timer setting (input + unit selector)
- Retake policy (max attempts + cooldown)
- Approval gate toggle
- Pass/fail action (Advance / Retake / Notify manager / Block)

**Failure Actions:**
| Failure Action | Behaviour |
|---|---|
| `retake` | Trainee sees their score + feedback and can try again (within max_attempts) |
| `retake_after_review` | Trainee must re-read Tier 1/2 before retaking |
| `notify_manager` | Manager gets an alert; they decide what happens |
| `block` | Trainee cannot proceed until admin manually unlocks |

### 3.5.4 API — Sequence Config Endpoints

```
GET  /api/admin/courses/{id}/sequence        # Get current sequence config
PUT  /api/admin/courses/{id}/sequence        # Update sequence config
POST /api/admin/courses/{id}/sequence/reset  # Reset to defaults
```

---

## 3.6 — Voice Call Settings

### 3.6.1 Description
Admin controls all parameters of the voice pipeline used in Tier 3 mock calls.

### 3.6.2 Voice Settings Object

```json
{
  "id": "uuid",
  "name": "Standard English (Indian Accent)",
  "stt_provider": "elevenlabs | deepgram | assemblyai",
  "stt_language": "en-IN | en-US | en-GB",
  "stt_noise_suppression": true,
  "tts_provider": "cartesia | elevenlabs | lmnt",
  "tts_voice_id": "f786b574-...",
  "tts_voice_name": "Sarah — Professional Female",
  "tts_speed": 1.0,           // 0.5 – 2.0
  "tts_emotion": "neutral | warm | professional",
  "vad_provider": "silero",
  "vad_sensitivity": "low | medium | high",
  "call_settings": {
    "max_duration_seconds": 600,       // 10 min hard cutoff
    "silence_timeout_seconds": 20,     // auto-end if no speech for 20s
    "greeting_message": "Hello, this is Sarah from AcceleratorX...",
    "end_message": "Thank you for your time. We'll review your performance now.",
    "room_prefix": "mock-call-tier3"
  }
}
```

### 3.6.3 UI — Voice Settings (`/admin/voice-settings`)

- **Voice Profile List:** Cards showing provider, voice name, sample play button
- **Voice Profile Editor:**
  - STT tab: Provider dropdown, language selector, noise suppression toggle
  - TTS tab: Provider dropdown, voice browser (with play-sample button), speed slider, emotion selector
  - VAD tab: Sensitivity selector with explanation of what each level does
  - Call Behaviour tab: Max duration, silence timeout, greeting/closing message editor
- **Test Call button:** Launch a test LiveKit session using this voice profile to hear how it sounds

### 3.6.4 API — Voice Settings Endpoints

```
GET    /api/admin/voice-settings                # List voice profiles
POST   /api/admin/voice-settings                # Create profile
GET    /api/admin/voice-settings/{id}           # Get profile
PUT    /api/admin/voice-settings/{id}           # Update profile
DELETE /api/admin/voice-settings/{id}           # Delete profile
POST   /api/admin/voice-settings/{id}/test      # Launch test call
GET    /api/admin/voice-settings/providers      # Available STT/TTS providers + voices
```

---

## 3.7 — Token Limiter & Cost Control

### 3.7.1 Description
Controls how many LLM tokens can be used per trainee, per session, and per course — preventing runaway API costs. Includes a usage dashboard and alerts.

### 3.7.2 Token Policy Object

```json
{
  "id": "uuid",
  "name": "Standard Training Policy",
  "limits": {
    "per_session_tokens": 50000,        // max tokens for one training session
    "per_user_per_day_tokens": 200000,  // daily cap per trainee
    "per_course_total_tokens": 2000000, // total tokens across all users for this course
    "tier1_chat_max_messages": 25,      // cap message count in Tier 1 chat
    "tier2_chat_max_messages": 30,      // cap message count in Tier 2 chat
    "tier3_max_call_minutes": 10,       // voice call duration (feeds into livekit_service.py)
    "tier3_max_attempts": 3             // voice call retakes allowed
  },
  "on_limit_reached": {
    "action": "warn | soft_stop | hard_stop",
    "warn_at_percent": 80,              // show warning when 80% of limit used
    "message": "You've used most of your token allowance. Please complete soon."
  },
  "cost_tracking": {
    "llm_cost_per_1k_tokens_usd": 0.00025,   // claude haiku pricing
    "tts_cost_per_char_usd": 0.00001,
    "stt_cost_per_minute_usd": 0.005
  }
}
```

### 3.7.3 Usage Dashboard (`/admin/token-usage`)

**Tiles:**
- Total API spend this month (INR + USD)
- LLM tokens used today
- Voice minutes used today
- Top 5 cost drivers (by course)

**Usage Table:**
- Per-trainee usage: tokens used, cost, sessions count, last active
- Per-course aggregate: total tokens, total cost, avg per trainee

**Alerts Configuration:**
- Set daily spend alert threshold (e.g., alert when daily cost exceeds ₹500)
- Set per-user alert (e.g., alert when a single user exceeds 100K tokens in a day)
- Notification via: in-app banner, email (future)

### 3.7.4 API — Token/Cost Endpoints

```
GET    /api/admin/token-policies             # List policies
POST   /api/admin/token-policies             # Create policy
GET    /api/admin/token-policies/{id}        # Get policy
PUT    /api/admin/token-policies/{id}        # Update policy
GET    /api/admin/usage                      # Usage summary (tiles)
GET    /api/admin/usage/by-user              # Per-user breakdown
GET    /api/admin/usage/by-course            # Per-course breakdown
GET    /api/admin/usage/sessions             # Per-session cost log
GET    /api/admin/usage/alerts               # Alert config
PUT    /api/admin/usage/alerts               # Update alert thresholds
```

---

## 3.8 — Approval Workflows

### 3.8.1 Description
Admins and managers can gate certain actions behind an explicit approval step. Three types of approvals are supported.

### 3.8.2 Approval Types

#### Type A — Document Approval (KB)
- **Trigger:** New document uploaded to a KB module
- **Approver:** Admin or designated KB reviewer
- **Action:** Review document content → Approve (indexes) or Reject (with note)
- **Urgency:** Low — no trainee is blocked

#### Type B — Tier Advancement Approval
- **Trigger:** Trainee completes a tier and the course has `requires_approval_to_advance: true`
- **Approver:** Manager (for their team) or Admin
- **Payload:** Trainee's tier score, transcript link, AI feedback
- **Actions:**
  - **Approve** → trainee unlocks next tier
  - **Reject** → trainee must retake current tier
  - **Request Review** → admin/manager adds a note asking trainee to review specific material before retaking
- **SLA:** 48 hours — if no action taken, auto-approve

#### Type C — Hire/Pass Decision Approval
- **Trigger:** Trainee scores ≥ passing_score on Tier 3 and course has `requires_approval_to_pass: true`
- **Approver:** Manager
- **Payload:** Full session transcript, all 5 dimension scores, AI feedback, previous attempt history
- **Actions:**
  - **Approve (Hire)** → trainee is marked as certified for this course
  - **Approve (Conditional)** → certified but with mandatory follow-up review in 30 days
  - **Reject (Not Ready Yet)** → sent back, must do 1 more Tier 2 + Tier 3 attempt

### 3.8.3 Approval Queue UI (`/admin/approvals`)

- **Pending tab:** All open approvals sorted by urgency/SLA deadline
  - Each row: Type badge (KB Doc / Tier Advance / Hire Decision), Trainee/Document name, Course, Submitted at, SLA countdown, Action buttons (Approve/Reject/View)
  - Expand row to see full context without leaving the page
- **Completed tab:** History of all processed approvals with outcome and approver name
- **Settings tab:** Configure which approval types are enabled, SLA durations, auto-approve fallback

### 3.8.4 API — Approval Endpoints

```
GET    /api/admin/approvals                  # List pending approvals
GET    /api/admin/approvals/{id}             # Single approval detail
POST   /api/admin/approvals/{id}/approve     # Approve with optional note
POST   /api/admin/approvals/{id}/reject      # Reject with required note
POST   /api/admin/approvals/{id}/request-review # Request trainee review with note
GET    /api/admin/approvals/history          # Completed approvals log
GET    /api/admin/approvals/settings         # Approval settings
PUT    /api/admin/approvals/settings         # Update settings
```

---

## 3.9 — User & Enrolment Management

### 3.9.1 Description
Admins manage which trainees are enrolled in which courses, view their progress, and manually advance or block them.

### 3.9.2 Trainee Progress Object

```json
{
  "user_id": "uuid",
  "user_name": "Priya Sharma",
  "course_id": "uuid",
  "course_name": "GenAI Sales Pitch",
  "enrolled_at": "iso8601",
  "deadline": "iso8601",
  "current_tier": "tier2",
  "tier_progress": {
    "tier1": { "status": "completed", "completed_at": "...", "approved_by": "..." },
    "tier2": { "status": "in_progress", "messages_count": 12 },
    "tier3": { "status": "locked" }
  },
  "attempts": [
    {
      "tier": "tier3_round2",
      "attempt_number": 1,
      "score": 6.2,
      "decision": "Not Ready Yet",
      "session_id": "...",
      "created_at": "..."
    }
  ],
  "final_score": null,
  "certified": false,
  "tokens_used": 32400
}
```

### 3.9.3 UI — Trainee Management (`/admin/trainees`)

- **Trainee List:** Search by name, filter by course/team/status
- **Trainee Detail:** Full progress timeline, all attempt scores, transcript links
- **Admin Actions:**
  - Manually advance a trainee to next tier (bypass score requirement)
  - Manually block a trainee from advancing
  - Reset a specific tier (wipe their progress for that tier only)
  - Extend their course deadline
  - View their token usage

---

## 4. Admin Navigation Structure

```
/admin
├── /dashboard          ← Overview: active sessions, scores, pending approvals
├── /courses            ← Course list + editor
│   └── /{id}/sequence  ← Evaluation sequence builder
├── /agents             ← AI agent persona manager
├── /knowledge-base     ← KB modules + document management
│   └── /{id}           ← Module detail, chunks, test tool
├── /evaluations        ← Live evaluation dashboard + leaderboard
│   └── /{session_id}   ← Session detail + transcript + scoring
├── /approvals          ← Approval queue
├── /voice-settings     ← Voice profile manager
├── /token-usage        ← Cost dashboard + policies
└── /trainees           ← Trainee management + progress tracking
```

---

## 5. Data Model Summary

```
courses
  ├── id, name, description, status, passing_score
  ├── kb_module_id → kb_modules
  ├── agent_id → agents
  ├── voice_settings_id → voice_settings
  └── token_policy_id → token_policies

tier_configs
  ├── course_id → courses
  └── tier, settings (JSONB)

enrollments
  ├── user_id, course_id
  ├── enrolled_at, deadline, certified
  └── final_score, certified_at

tier_progress
  ├── enrollment_id → enrollments
  ├── tier, status, completed_at
  └── approved_by, approved_at

training_sessions
  ├── id, user_id, course_id, tier, round
  ├── session_type (chat | voice_round1 | voice_round2)
  ├── tokens_used, cost_usd
  ├── transcript (JSONB)
  └── score, dimension_scores (JSONB), feedback, created_at

approvals
  ├── id, type (kb_doc | tier_advance | hire_decision)
  ├── subject_id (document_id or session_id)
  ├── requested_by, assigned_to
  ├── status (pending | approved | rejected | review_requested)
  ├── note, resolved_at
  └── created_at

token_usage_log
  ├── user_id, session_id, course_id
  ├── tokens_input, tokens_output
  ├── tts_chars, stt_seconds
  └── estimated_cost_usd, created_at
```

---

## 6. Implementation Plan

### Phase 1 — Foundation (Week 1–2)
- [ ] Data model migrations (courses, enrollments, tier_progress, training_sessions)
- [ ] Course CRUD API (`/api/admin/courses/*`)
- [ ] KB Admin API (document approval workflow, version history)
- [ ] Enrollment API
- [ ] Admin auth middleware

### Phase 2 — Configuration (Week 3–4)
- [ ] Agent behaviour config API (extend existing `/api/agents` with new fields)
- [ ] Tier sequence config API
- [ ] Voice settings API
- [ ] Token policy API
- [ ] Wire tier configs into `/api/chat` (Tier 1/2) and `/api/mock-call/start` (Tier 3)

### Phase 3 — Evaluation Dashboard (Week 5)
- [ ] Training sessions log (persist all chat + voice sessions with cost data)
- [ ] Evaluation stats API (tiles, leaderboard, charts)
- [ ] Score override API
- [ ] CSV export

### Phase 4 — Approvals & Token Control (Week 6)
- [ ] Approval queue API + notification hooks
- [ ] Token usage log (middleware that counts tokens on every LLM call)
- [ ] Cost dashboard API
- [ ] Alert system (in-app for now)

### Phase 5 — Admin Frontend (Week 7–8)
- [ ] Admin React/HTML SPA with all pages
- [ ] Real-time evaluation feed (polling or SSE)
- [ ] Course sequence drag-and-drop builder
- [ ] Approval queue UI

### Estimated Effort
| Phase | Backend | Frontend | Total |
|---|---|---|---|
| Foundation | 5 days | — | 5 days |
| Configuration | 5 days | — | 5 days |
| Evaluation Dashboard | 3 days | — | 3 days |
| Approvals & Token Control | 4 days | — | 4 days |
| Admin Frontend | — | 10 days | 10 days |
| **Total** | **17 days** | **10 days** | **~6 weeks** |

---

## 7. Open Questions

> [!IMPORTANT]
> **Q1:** Should the admin frontend be part of the existing `admin.html` single-file SPA, or should it be rebuilt as a proper React app?

> [!IMPORTANT]
> **Q2:** Is the approval notification delivery channel in-app only for now, or should email/WhatsApp notifications be in scope for v1?

> [!IMPORTANT]
> **Q3:** Token limits — are these hard limits (LLM calls fail/stop) or soft limits (session continues but logs a flag and alerts admin)?

> [!IMPORTANT]
> **Q4:** Is there a multi-tenant requirement? (i.e., different companies with isolated KB modules and users) — this impacts the data model significantly.

> [!IMPORTANT]
> **Q5:** For Tier 3 Round 1 (AI demonstrates the call), who is the simulated customer the AI talks to — another AI, or does the AI just deliver a scripted monologue?

---

## 8. Success Metrics

| Metric | Target |
|---|---|
| Admin can create a complete course (KB + agent + sequence + voice) | < 15 minutes end-to-end |
| Live evaluation score visible after call ends | < 30 seconds latency |
| Approval response time (SLA) | < 48 hours (enforced) |
| Token cost visibility | Real-time within admin dashboard |
| Course completion rate across trainees | Baseline measurement in first 30 days |
| Average Tier 3 score improvement (attempt 1 → attempt 2) | Target +1.5 points |
