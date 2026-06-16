import re
from core.llm_client import llm_client

class Evaluator:
    def generate_questions(self, context, num_questions=3):
        """Uses Cerebras to generate sales training questions based on the uploaded context."""
        system = "You are an expert sales manager creating realistic sales training prompts."
        prompt = (
            f"Based on the following company knowledge base context about our products and services, generate {num_questions} concise, conversational sales discovery questions, objections, or questions about product value.\n"
            f"The questions MUST be focused on:\n"
            f"1. How the product helps solve business problems or improves outcomes.\n"
            f"2. Objections regarding price, implementation time, or trust.\n"
            f"3. Understanding the product features and how they fit the client's needs.\n\n"
            f"DO NOT generate questions about:\n"
            f"- Technical architecture (e.g., LangChain, n8n, API structures, backend tools).\n"
            f"- Compliance standards, security implementation, or infrastructure.\n"
            f"- Complex workflow automation design or tool-stack comparisons.\n\n"
            f"Context:\n{context}\n\n"
            f"Output ONLY the questions, separated by newlines."
        )
        
        messages = [{"role": "user", "content": prompt}]
        response = llm_client.generate(messages, system=system)
        
        lines = [q.strip() for q in response.split("\n") if q.strip()]
        questions = [
            q
            for q in lines
            if q[0].isdigit() or q.startswith("-") or q.endswith("?")
        ]
        if not questions:
            questions = lines
        questions = [re.sub(r'^[\d\.\-\)\s]+', '', q) for q in questions]
        return [q for q in questions if q][:num_questions] # Fallback filter

    def evaluate_answer(self, question, answer, context):
        """Evaluates a sales rep's answer on a scale of 1-10."""
        system = "You are an expert sales manager evaluating a sales representative."
        prompt = (
            f"Evaluate the rep's answer to the client's question based on the provided company knowledge base context.\n"
            f"Rate the answer on a scale of 1 to 10 based on:\n"
            f"1. Accuracy of information regarding the product/service in the context.\n"
            f"2. Sales effectiveness, persuasion, and empathy.\n"
            f"3. Ability to clearly explain the value proposition to a business client.\n\n"
            f"DO NOT evaluate based on technical architectural details, backend implementation, or tool-stack discussions.\n"
            f"If the sales rep mentions technical details unnecessarily, coach them to focus on the business benefit instead.\n\n"
            f"Knowledge Base Context:\n{context}\n\n"
            f"Client Question: {question}\n"
            f"Sales Rep's Answer: {answer}\n\n"
            f"Provide your evaluation in the following EXACT format:\n"
            f"Score: [Insert number 1-10 here]\n"
            f"Feedback: [Provide 1-2 paragraphs of constructive sales coaching feedback here]"
        )
        
        messages = [{"role": "user", "content": prompt}]
        response = llm_client.generate(messages, system=system)
        
        # Parse the output
        score = 0
        feedback = response
        
        try:
            score_match = re.search(r'Score:\s*(\d+)', response, re.IGNORECASE)
            if score_match:
                score = int(score_match.group(1))
            
            feedback_match = re.search(r'Feedback:\s*(.*)', response, re.IGNORECASE | re.DOTALL)
            if feedback_match:
                feedback = feedback_match.group(1).strip()
        except Exception as e:
            print(f"Error parsing evaluation: {e}")
            
        return {
            "score": score,
            "feedback": feedback,
            "raw_response": response
        }

    def evaluate_mock_call(self, transcript, context):
        system = "You are a strict but constructive AI sales trainer scoring a mock sales call."
        prompt = (
            "Evaluate this mock sales call transcript using the company knowledge base context.\n"
            "Score the rep out of 10 on product accuracy, discovery quality, objection handling, empathy, and closing clarity.\n"
            "Return all scores as integers from 1 to 10.\n"
            "Return the exact format:\n"
            "ProductAccuracy: [number 1-10]\n"
            "Discovery: [number 1-10]\n"
            "ObjectionHandling: [number 1-10]\n"
            "Empathy: [number 1-10]\n"
            "ClosingClarity: [number 1-10]\n"
            "Feedback: [short coaching feedback]\n\n"
            f"Knowledge Base Context:\n{context}\n\n"
            f"Mock Call Transcript:\n{transcript}"
        )
        response = llm_client.generate([{"role": "user", "content": prompt}], system=system)
        product_accuracy = 0
        discovery = 0
        objection_handling = 0
        empathy = 0
        closing_clarity = 0
        feedback = response
        score_patterns = {
            "product_accuracy": r"ProductAccuracy:\s*(\d+)",
            "discovery": r"Discovery:\s*(\d+)",
            "objection_handling": r"ObjectionHandling:\s*(\d+)",
            "empathy": r"Empathy:\s*(\d+)",
            "closing_clarity": r"ClosingClarity:\s*(\d+)",
        }
        matches = {}
        for key, pattern in score_patterns.items():
            match = re.search(pattern, response, re.IGNORECASE)
            value = int(match.group(1)) if match else 0
            value = min(10, max(1, value)) if value else 0
            matches[key] = value
        product_accuracy = matches["product_accuracy"]
        discovery = matches["discovery"]
        objection_handling = matches["objection_handling"]
        empathy = matches["empathy"]
        closing_clarity = matches["closing_clarity"]
        feedback_match = re.search(r"Feedback:\s*(.*)", response, re.IGNORECASE | re.DOTALL)
        if feedback_match:
            feedback = feedback_match.group(1).strip()
        scores = [product_accuracy, discovery, objection_handling, empathy, closing_clarity]
        valid_scores = [score for score in scores if score > 0]
        score = round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else 0
        return {"score": score, "feedback": feedback, "raw_response": response}

    def evaluate_full_session(self, chat_transcript, voice_transcript, context):
        system = (
            "You are a strict but constructive AI sales trainer evaluating a sales representative's "
            "performance across FIVE competency dimensions. You must compare the rep's answers "
            "STRICTLY against the provided knowledge base document text. "
            "If the rep states product facts not found in the documents, deduct heavily."
        )
        prompt = (
            "Evaluate the sales representative's performance across TWO interactions: a Text Chat and a Voice Mock Call.\n\n"
            "SCORING RULES:\n"
            "1. Compare EVERY factual claim made by the rep against the Knowledge Base Context below.\n"
            "2. If the rep correctly references document content → reward points.\n"
            "3. If the rep fabricates product features, pricing, or facts NOT in the documents → penalize heavily (subtract 2-3 points).\n"
            "4. If the rep fails to ask discovery questions → low Discovery score.\n"
            "5. If the rep fails to handle objections → low ObjectionHandling score.\n"
            "6. If the rep uses heavy jargon or talks past the customer → low Communication score.\n"
            "7. If the rep cannot close or ask for next steps → low ClosingClarity score.\n\n"
            "Return EXACTLY this format. All scores must be integers from 1 to 10:\n"
            "ChatScore: [number 1-10]\n"
            "VoiceScore: [number 1-10]\n"
            "ProductKnowledge: [number 1-10]\n"
            "Discovery: [number 1-10]\n"
            "ObjectionHandling: [number 1-10]\n"
            "Communication: [number 1-10]\n"
            "ClosingClarity: [number 1-10]\n"
            "ChatFeedback: [2-3 sentences of specific coaching feedback for the chat]\n"
            "VoiceFeedback: [2-3 sentences of specific coaching feedback for the voice call]\n\n"
            f"══ Knowledge Base Context (ground truth) ══\n{context}\n\n"
            f"══ Chat Interaction Transcript ══\n{chat_transcript}\n\n"
            f"══ Voice Mock Call Transcript ══\n{voice_transcript}"
        )
        response = llm_client.generate([{"role": "user", "content": prompt}], system=system)

        def _get_score(pattern):
            match = re.search(pattern, response, re.IGNORECASE)
            return min(10, max(1, int(match.group(1)))) if match else 0

        chat_score = _get_score(r"ChatScore:\s*(\d+)")
        voice_score = _get_score(r"VoiceScore:\s*(\d+)")

        chat_fb_match = re.search(r"ChatFeedback:\s*(.*?)(?=VoiceFeedback:|$)", response, re.IGNORECASE | re.DOTALL)
        voice_fb_match = re.search(r"VoiceFeedback:\s*(.*)", response, re.IGNORECASE | re.DOTALL)

        chat_fb = chat_fb_match.group(1).strip() if chat_fb_match else "No chat feedback provided."
        voice_fb = voice_fb_match.group(1).strip() if voice_fb_match else "No voice feedback provided."

        return {
            "chat_score": chat_score,
            "voice_score": voice_score,
            "product_accuracy": _get_score(r"ProductKnowledge:\s*(\d+)"),
            "discovery": _get_score(r"Discovery:\s*(\d+)"),
            "objection_handling": _get_score(r"ObjectionHandling:\s*(\d+)"),
            "empathy": _get_score(r"Communication:\s*(\d+)"),   # reused 'empathy' key for compat
            "closing_clarity": _get_score(r"ClosingClarity:\s*(\d+)"),
            "chat_feedback": chat_fb,
            "voice_feedback": voice_fb,
            "raw_response": response
        }

    def combine_scores(self, voice_score, text_score):
        voice = float(voice_score or 0)
        text = float(text_score or 0)

        if voice <= 0:
            final_score = round(text, 2)
        elif text <= 0:
            final_score = round(voice, 2)
        else:
            # Equal weight: (Chat + Voice) / 2
            final_score = round((voice + text) / 2, 2)

        hiring_decision = "Hire" if final_score >= 7.0 else "Do Not Hire"
        return final_score, hiring_decision

evaluator = Evaluator()
