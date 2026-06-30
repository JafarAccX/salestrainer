# How to Add and Test a Sales Trainer Course

This guide walks you through the end-to-end process of creating a new training scenario in the Admin Panel and testing it as a Sales Rep on the frontend.

---

## Part 1: Adding a New Training Course (Admin)

To create a new training scenario, you need three components: a **Knowledge Base Module** (what the AI knows), an **AI Agent Persona** (how the AI acts), and a **Course** (the wrapper that links them together with a passing score).

### 1. Open the Admin Console
Open your browser and navigate to the admin console:
`http://localhost:8000/admin-console.html` *(assuming the backend is running on port 8000)*
### 2. Create a Knowledge Base (KB) Module
1. Navigate to the **Knowledge Base** tab.
2. Click **+ New Module**.
3. Give it a descriptive name (e.g., *Enterprise Security Pitch*).
4. Paste the factual information the AI prospect needs to know in the text area. This should include company details, pain points, budget, and features.
5. Click **Save Module**.

### 3. Create an AI Agent Persona
1. Navigate to the **AI Agents** tab.
2. Click **+ New Agent**.
3. Fill out the persona details:
   - **Name:** (e.g., *Skeptical CISO*)
   - **Difficulty:** Select Easy, Medium, Hard, or Custom.
   - **Base Instructions:** Tell the AI how to behave (e.g., *"You are a busy CISO who is highly skeptical of new software tools."*)
4. *(Optional)* Add specific objections you want the AI to raise during the call.
5. Click **Create Agent**.

### 4. Create the Course
1. Navigate to the **Courses** tab.
2. Click **+ New Course**.
3. Fill out the form:
   - **Name:** The title the sales reps will see (e.g., *Security Product Pitch Certification*).
   - **Description:** A short brief on what the rep needs to accomplish.
   - **Knowledge Base Module:** Select the module you created in Step 2.
   - **AI Agent Persona:** Select the persona you created in Step 3.
   - **Passing Score:** Set the minimum score required to pass (e.g., `7.0`).
4. Click **Create Course**.
5. **Publish the Course:** In the courses table, click the **Publish** button next to your new course so it becomes visible to the sales reps.

---

## Part 2: Testing the Course (Sales Rep)

Now, switch to the trainee perspective to test the flow.

### 1. Open the Trainee Portal
Open a new browser tab and navigate to:
`http://localhost:8000/index.html`

### 2. Start the Training
1. In the top right corner, use the **Course Dropdown** to select your newly published course.
2. Enter a **Sales Rep ID** (e.g., your name or email) to track your progress.
3. Click the button to **Begin Training**.

### 3. Run Through the Tiers
The training is broken into three sequential steps:
- **Tier 1 (Text Chat):** Warm up by chatting with the AI. Ensure the AI responds according to the persona and KB module you configured. Click *Mark Complete* when done.
- **Tier 2 (Practice Call):** Start the voice call. Speak into your microphone and verify the AI voice agent responds naturally. Click *Mark Complete* when done.
- **Tier 3 (Evaluation Call):** This is the graded run. Conduct a full sales pitch. The AI will evaluate your performance based on Product Accuracy, Discovery, Objection Handling, Empathy, and Closing Clarity.
- **Submit Evaluation:** Once the call is finished, click **Run Evaluation**. The LLM will score your call and submit it to the admin queue.

---

## Part 3: Reviewing the Results (Admin)

Switch back to the Admin Console to review the trainee's performance.

### 1. Review and Approve
1. Go to the **Approvals** tab in the Admin Console.
2. You should see the recent attempt listed under the rep's ID. 
3. Review the individual metric scores, the final score out of 10, and the AI's hiring recommendation.
4. Click **Transcript** to read the exact conversation the rep had with the AI.
5. Click **Approve** (to certify the rep) or **Reject** (to force them to retake the evaluation).

### 2. Check the Leaderboard
1. Go to the **Evaluations & Leaderboard** tab.
2. Use the **Filter by Course** dropdown to select your test course.
3. Verify that your test run appears on the leaderboard with the correct scores and Sales Rep ID.

### 3. Monitor Token Usage
1. Go to the **Token Usage & Cost** tab.
2. Use the **Filter by Course** dropdown.
3. Review how many LLM tokens were consumed during your test run and the estimated cost.
