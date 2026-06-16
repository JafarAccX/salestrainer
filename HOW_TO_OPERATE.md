# Sales Trainer Agent: Complete Operating Guide

Welcome to the **Sales Trainer Agent**. This application is a fully integrated, AI-powered roleplay and evaluation platform for training sales representatives.

---

## 1. Starting the Application

The platform is split into three main pieces that must be running simultaneously for the full experience.

### A. The Backend Server (FastAPI)
This handles all API requests, file uploads, text chat, RAG (Retrieval-Augmented Generation), and Evaluation scoring.
1. Open a terminal and navigate to the `backend` folder:
   ```bash
   cd C:\Users\rmran\OneDrive\Desktop\salestrainer\backend
   ```
2. Activate your virtual environment (if you are using one).
3. Run the server:
   ```bash
   python main.py
   ```
   *The server runs on `http://0.0.0.0:8000`.*

### B. The Voice Agent Worker (LiveKit)
This handles the real-time, low-latency voice mock calls. It connects directly to LiveKit and Cartesia/Anthropic APIs.
1. Open a **second, separate terminal** and navigate to the `backend` folder:
   ```bash
   cd C:\Users\rmran\OneDrive\Desktop\salestrainer\backend
   ```
2. Run the background worker:
   ```bash
   python voice_agent_worker.py start
   ```
   *Note: If you get a "port 8081 already in use" error, it means an old worker is still running in the background. You must kill the old terminal process before starting a new one.*

### C. The Frontend UI
The entire frontend is contained within a single, beautifully designed HTML file.
1. You can access the frontend by navigating to the backend's root URL in your web browser:
   **http://localhost:8000**
2. (Alternatively, you can open `frontend/index.html` directly in your browser or run it via a Live Server extension).

---

## 2. How to Operate the Platform (The User Flow)

Once the application is running, here is the exact step-by-step workflow a Manager and a Sales Rep should follow.

### Step 1: The Manager Creates a Knowledge Base
Before any training can happen, the AI needs context.
1. Go to the **Knowledge Base** tab.
2. Under "Create New Module", type a name (e.g., "Enterprise Software Pitch") and click **Create Module**.
3. Select your newly created module from the "Active Context Module" dropdown at the top of the screen.
4. Upload relevant training PDFs, text files, or markdown files into the module. The backend will automatically parse, chunk, and save this data into the local ChromaDB database.

### Step 2: The Rep Learns the Material
1. Go to the **Learning Hub** tab.
2. Ensure the correct module is still selected in the top dropdown.
3. Click **Generate Curriculum from Documents**.
4. The AI will read *all* the uploaded documents and instantly generate a structured study guide (covering Core Concepts, Product Specs, Objection Handling, etc.) for the rep to study.

### Step 3: The Rep Takes the Assessment
There are two ways to practice: Text Chat and Voice Call. To simulate real pressure, use the **Assessment Timer**.
1. At the bottom of the left sidebar, set your desired time limit (e.g., 2 minutes) and click **Start**. 
2. A stopwatch will appear globally at the top of the sidebar.
3. **Voice Mock Call:** 
   - Go to the **Voice Mock Call** tab.
   - Click **Start Voice Mock Call**. 
   - Click **Launch Playground Tab** to open the LiveKit interface and actually talk with the AI voice agent.
4. **AI Chat Assistant:**
   - Go to the **AI Chat Assistant** tab to practice typing out email replies or text pitches to the AI prospect.

### Step 4: Final Evaluation & Hiring Decision
When the Assessment Timer hits `00:00`, the system will forcefully lock you out of testing and automatically switch you to the **Evaluation Dashboard**.
1. (If not using the timer, you can manually navigate to the **Evaluation Dashboard** tab).
2. The user pastes their Voice Mock Call transcript into the transcript box (and optionally provides a text-based Q&A answer).
3. Click **Generate Final Score & Hiring Decision**.
4. The AI compares the rep's performance strictly against the documents uploaded in Step 1. 
5. A beautiful Dashboard Grid will slide in showing:
   - A final averaged score out of 10.
   - A glowing **Hire** (Green) or **Do Not Hire** (Red) badge (threshold is 7.0/10).
   - Specific, granular feedback on Product Accuracy, Discovery, and Objection Handling.

---

## 3. Architecture & Keys
- **Memory / Database:** `salestrainer/chroma_db` stores the vector embeddings for the AI. Do not delete this folder unless you want to reset all knowledge base modules.
- **Keys:** Your API Keys (Anthropic, Cartesia, LiveKit, Deepgram) are stored securely in `backend/.env`. If you ever need to change voice providers or LLMs, update them there!
