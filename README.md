# AI Sales Trainer Agent

Welcome to the **Sales Trainer Agent**. This application is a fully integrated, AI-powered roleplay and evaluation platform designed to onboard and train sales representatives.

---

## 1. Quick Start Guide

The platform requires both a FastAPI backend and a LiveKit Voice Worker to run simultaneously.

### A. Environment Variables
Before starting, ensure your `.env` file is present in the `backend/` directory with the following keys:
```env
# AI Models
ANTHROPIC_API_KEY=sk-ant-...
CARTESIA_API_KEY=sk_car_...
DEEPGRAM_API_KEY=your-deepgram-key

# LiveKit (Voice Provider)
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxx
LIVEKIT_API_SECRET=your-secret
LIVEKIT_AGENT_NAME=sales-trainer-agent
```

### B. The Backend Server (FastAPI)
This handles all API requests, file uploads, text chat, RAG (Retrieval-Augmented Generation), and Evaluation scoring.
1. Open a terminal and navigate to the `backend` folder:
   ```bash
   cd backend
   ```
2. Install requirements if you haven't already:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the server:
   ```bash
   python main.py
   ```
   *The server runs on `http://0.0.0.0:8000`.*

### C. The Voice Agent Worker (LiveKit)
This handles the real-time, low-latency voice mock calls. It connects directly to LiveKit and Cartesia/Anthropic APIs.
1. Open a **second, separate terminal** and navigate to the `backend` folder:
   ```bash
   cd backend
   ```
2. Run the background worker:
   ```bash
   python voice_agent_worker.py start
   ```

### D. The Frontend UI
1. Once both servers are running, access the application by navigating to the backend URL in your web browser:
   **http://localhost:8000**

---

## 2. Operation Workflow

### Step 1: Manager Setup (Knowledge Base)
1. Go to the **Knowledge Base** tab in the UI.
2. Create a New Module (e.g., "Enterprise Software Pitch").
3. Select your newly created module from the dropdown.
4. Upload relevant training PDFs, text files, or markdown files into the module. The backend will automatically parse, chunk, and save this data into the local ChromaDB database.

### Step 2: Rep Learning Phase
1. Go to the **Learning Hub** tab.
2. Ensure the correct module is still selected.
3. Click **Generate Curriculum from Documents**. The AI will synthesize the uploaded documents into a structured study guide.

### Step 3: Timed Assessments
To simulate real pressure, use the **Assessment Timer** at the bottom of the sidebar.
1. Set the time limit and click **Start**. 
2. Practice via the **AI Chat Assistant** or **Voice Mock Call** tabs.
3. **Voice Mock Call:** Click *Start Voice Mock Call*, then *Launch Playground Tab* to talk with the AI voice agent.

### Step 4: Final Evaluation & Hiring Decision
When the timer expires (or when you manually navigate to the **Evaluation Dashboard**):
1. Paste your mock call transcript into the text box.
2. Click **Generate Final Score & Hiring Decision**.
3. The AI generates a dashboard showing:
   - Final averaged score out of 10.
   - **Hire** (Green) or **Do Not Hire** (Red) badge (threshold is 7.0/10).
   - Granular feedback on Product Accuracy, Discovery, and Objection Handling based on the Knowledge Base.

---

## 3. Architecture & Directories
- `chroma_db/`: Vector database storing document embeddings.
- `kb_store/`: Original uploaded knowledge base documents.
- `backend/`: Core Python/FastAPI code and LiveKit worker.
- `frontend/`: Single-page HTML/JS/CSS application.
