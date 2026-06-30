# CRM & Sales Trainer Compatibility Test Plan

This document outlines the testing strategy to ensure the `salestrainer` application integrates cleanly into the `CRM_main` environment without regressions, data collisions, or UX confusion.

---

## 1. Environment & Network Testing

### Test Case 1.1: Port Conflict Check
- **Objective:** Ensure both backends and frontends can run simultaneously on the same machine/server.
- **Steps:**
  1. Start `CRM_main` backend (NestJS, usually port 3000/3001) and frontend (Vite, usually port 5173).
  2. Start `salestrainer` backend (`main.py` on port 8000).
- **Expected Result:** Both systems start successfully without `EADDRINUSE` port conflict errors.

### Test Case 1.2: CORS & Widget Embedding
- **Objective:** Verify the CRM frontend can securely render the Sales Trainer widget.
- **Steps:**
  1. Embed the Sales Trainer `widget.js` or `<iframe>` in a new CRM React component (e.g., `/training-hub`).
  2. Attempt to open the trainer from within the CRM.
- **Expected Result:** The widget loads successfully. No Cross-Origin Resource Sharing (CORS) errors or iframe blocking policies (`X-Frame-Options`) appear in the browser console.

---

## 2. Authentication & Context Syncing

### Test Case 2.1: Identity Passthrough
- **Objective:** Ensure the CRM user's ID is automatically passed to the Sales Trainer to avoid double-login.
- **Steps:**
  1. Log into the CRM as a Sales Rep (e.g., `Rep_ID_001`).
  2. Launch the embedded Sales Trainer.
  3. Complete a training evaluation.
  4. Open the Sales Trainer Admin Console.
- **Expected Result:** The leaderboard and approval queues show the evaluation tied exactly to `Rep_ID_001`. The rep was not prompted to manually type their name/ID.

### Test Case 2.2: JWT Validation (If implemented)
- **Objective:** Verify the Sales Trainer backend correctly rejects unauthorized access from the CRM frontend.
- **Steps:**
  1. Attempt to call `/api/mock-call/start` on the Trainer backend from the CRM without a valid CRM Auth Token.
- **Expected Result:** The API returns a `401 Unauthorized` or `403 Forbidden` error.

---

## 3. LiveKit Audio & Hardware Conflicts

### Test Case 3.1: Microphone Access Collision
- **Objective:** Ensure the browser does not lock the microphone when switching between the CRM's production dialer and the training agent.
- **Steps:**
  1. Open the CRM's Outbound Voice Dialer and initiate a test call.
  2. End the CRM call.
  3. Immediately open the Sales Trainer widget and start a Tier 2/Tier 3 mock call.
- **Expected Result:** The Sales Trainer successfully connects to the microphone. No "Device in use" errors occur.

### Test Case 3.2: Concurrent WebSockets
- **Objective:** Verify LiveKit WebSocket stability.
- **Steps:**
  1. Run the Sales Trainer mock call.
  2. Leave the tab idle or navigate to other CRM tabs.
- **Expected Result:** The WebSocket connection remains stable and reconnects gracefully if the user minimizes the browser.

---

## 4. UI/UX & Terminology De-confliction

### Test Case 4.1: Navigation Clarity
- **Objective:** Prevent user confusion between "Live Calls" and "Training Calls".
- **Steps:**
  1. Have a test user navigate the CRM sidebar.
  2. Ask them to find the "Outbound Dialer" and the "Sales Trainer".
- **Expected Result:** The sidebar clearly separates the two modules. The labels do not overlap (e.g., using "Production Dialer" vs. "AI Training Hub").

### Test Case 4.2: Styling Isolation
- **Objective:** Ensure CRM Tailwind styles do not break the Sales Trainer vanilla CSS, and vice versa.
- **Steps:**
  1. Inspect the embedded Sales Trainer inside the CRM.
- **Expected Result:** Fonts, button paddings, and colors in the Sales Trainer remain intact and do not inherit unintended global CSS from the CRM's Tailwind configuration.

---

## 5. Knowledge Base (KB) Separation

### Test Case 5.1: File Upload Isolation
- **Objective:** Ensure training KBs and production KBs remain logically separate so the production AI does not hallucinate training scenarios.
- **Steps:**
  1. Upload a dummy training document (e.g., "Mock Pricing 2026") into the Sales Trainer Admin panel.
  2. Start a production call via the CRM Voice Dialer.
  3. Ask the production agent about the "Mock Pricing".
- **Expected Result:** The production agent has no knowledge of the mock pricing document. The local ChromaDB (Trainer) and production S3/VectorDB (CRM) are properly isolated.
