import re
import logging
from core.llm_client import llm_client
from core import prompts

logger = logging.getLogger(__name__)


class Evaluator:
    def generate_questions(self, context, num_questions=3):
        """Generates realistic sales discovery questions grounded in KB context."""
        system = (
            "You are an expert sales manager creating realistic mock-customer questions. "
            "Generate questions a REAL prospect would ask during a sales call. "
            "ONLY reference product information present in the provided context."
        )
        prompt = (
            f"Based on the company knowledge base below, generate {num_questions} realistic questions "
            "a potential customer would ask a sales rep.\n\n"
            "REQUIREMENTS:\n"
            "- Questions must be answerable using ONLY the provided context\n"
            "- Mix of: value/ROI questions, objections, and feature clarifications\n"
            "- Use natural business language (not technical architecture)\n"
            "- Each question on its own line, no numbering or bullets\n\n"
            f"Context:\n{context}\n\n"
            f"Generate exactly {num_questions} questions:"
        )
        response = llm_client.generate([{"role": "user", "content": prompt}], system=system)
        lines = [q.strip() for q in response.split("\n") if q.strip() and q.strip().endswith("?")]
        lines = [re.sub(r'^[\d\.\-\)\*\s]+', '', q) for q in lines]
        return [q for q in lines if len(q) > 10][:num_questions]

    def evaluate_answer(self, question, answer, context):
        """Evaluates a sales rep's answer with rubric-based scoring."""
        system = (
            "You are a strict sales evaluation AI. Score ONLY based on the rubric below. "
            "NEVER give credit for information not present in the Knowledge Base Context."
        )
        prompt = (
            "SCORING RUBRIC (each criterion 0-10):\n"
            "• Accuracy (40%): Does the answer match facts in the Knowledge Base? "
            "Fabricated facts = automatic cap at 4/10.\n"
            "• Sales Effectiveness (30%): Is the answer persuasive, benefit-focused, and concise?\n"
            "• Empathy & Rapport (30%): Does the rep acknowledge the prospect's concern?\n\n"
            "ANTI-HALLUCINATION CHECK:\n"
            "- List any claims the rep made that are NOT in the Knowledge Base\n"
            "- If hallucinations found, state them explicitly and reduce score\n\n"
            "SCORING EXAMPLES:\n"
            "- Score 9-10: Accurate, persuasive, empathetic, all claims grounded in KB\n"
            "- Score 6-8: Mostly accurate, decent sales approach, minor gaps\n"
            "- Score 3-5: Some accuracy but vague, fabricates minor details, weak pitch\n"
            "- Score 1-2: Mostly fabricated, no sales skill, ignores the prospect\n\n"
            f"══ Knowledge Base Context (ground truth) ══\n{context}\n\n"
            f"══ Customer Question ══\n{question}\n\n"
            f"══ Sales Rep Answer ══\n{answer}\n\n"
            "OUTPUT FORMAT (exact):\n"
            "Hallucinations: [list any fabricated claims, or 'None']\n"
            "Score: [integer 1-10]\n"
            "Feedback: [2-3 sentences of specific coaching]"
        )
        response = llm_client.generate([{"role": "user", "content": prompt}], system=system, max_tokens=1024)

        score = 0
        feedback = response
        try:
            score_match = re.search(r'Score:\s*(\d+)', response, re.IGNORECASE)
            if score_match:
                score = min(10, max(1, int(score_match.group(1))))
            feedback_match = re.search(r'Feedback:\s*(.*)', response, re.IGNORECASE | re.DOTALL)
            if feedback_match:
                feedback = feedback_match.group(1).strip()
        except Exception as e:
            logger.warning("Error parsing evaluation response: %s", e)

        return {"score": score, "feedback": feedback, "raw_response": response}

    def evaluate_mock_call(self, transcript, context):
        """Evaluates a single mock call transcript with detailed rubrics."""
        system = (
            "You are a calibrated AI sales evaluator. Score strictly against the rubric. "
            "Compare ALL rep claims against the Knowledge Base. Fabrications = heavy penalty."
        )
        prompt = (
            "RUBRIC — Score each dimension 1-10:\n\n"
            "ProductAccuracy (weight: HIGH):\n"
            "  10: All claims match KB exactly, deep product knowledge\n"
            "  7: Mostly accurate, minor omissions\n"
            "  4: Mix of correct and fabricated information\n"
            "  1: Mostly fabricated or completely wrong\n\n"
            "Discovery:\n"
            "  10: Asked 3+ targeted qualifying questions, uncovered real pain\n"
            "  7: Asked 1-2 good questions\n"
            "  4: Only surface-level questions\n"
            "  1: No discovery questions asked\n\n"
            "ObjectionHandling:\n"
            "  10: Acknowledged, empathized, reframed with KB-grounded proof\n"
            "  7: Addressed objections but missed empathy or proof\n"
            "  4: Dismissed or gave generic responses\n"
            "  1: Ignored objections entirely\n\n"
            "Empathy:\n"
            "  10: Active listening, adapted pitch to prospect's stated needs\n"
            "  7: Some adaptation, mostly scripted\n"
            "  4: Talked past the customer\n"
            "  1: Robotic, no acknowledgment of prospect\n\n"
            "ClosingClarity:\n"
            "  10: Clear next step proposed, confident ask\n"
            "  7: Vague suggestion of next steps\n"
            "  4: No close attempted\n"
            "  1: Ended abruptly or lost control\n\n"
            "ANTI-HALLUCINATION: List ALL claims by the rep not found in the KB.\n\n"
            f"══ Knowledge Base Context (ground truth) ══\n{context}\n\n"
            f"══ Mock Call Transcript ══\n{transcript}\n\n"
            "OUTPUT (exact format):\n"
            "Hallucinations: [list or 'None']\n"
            "ProductAccuracy: [1-10]\n"
            "Discovery: [1-10]\n"
            "ObjectionHandling: [1-10]\n"
            "Empathy: [1-10]\n"
            "ClosingClarity: [1-10]\n"
            "Feedback: [3-4 sentences of actionable coaching]"
        )
        response = llm_client.generate(
            [{"role": "user", "content": prompt}], system=system, max_tokens=1500
        )

        def _get(pattern):
            m = re.search(pattern, response, re.IGNORECASE)
            return min(10, max(1, int(m.group(1)))) if m else 0

        scores = {
            "product_accuracy": _get(r"ProductAccuracy:\s*(\d+)"),
            "discovery": _get(r"Discovery:\s*(\d+)"),
            "objection_handling": _get(r"ObjectionHandling:\s*(\d+)"),
            "empathy": _get(r"Empathy:\s*(\d+)"),
            "closing_clarity": _get(r"ClosingClarity:\s*(\d+)"),
        }
        valid = [v for v in scores.values() if v > 0]
        score = round(sum(valid) / len(valid), 2) if valid else 0

        fb_match = re.search(r"Feedback:\s*(.*)", response, re.IGNORECASE | re.DOTALL)
        feedback = fb_match.group(1).strip() if fb_match else response

        return {"score": score, "feedback": feedback, "raw_response": response}

    def evaluate_full_session(self, chat_transcript, voice_transcript, context):
        """Evaluates combined chat + voice performance with calibrated rubrics."""
        system = (
            "You are a calibrated AI sales evaluator performing a FINAL assessment. "
            "You MUST compare every factual claim against the Knowledge Base Context. "
            "If a claim is not in the KB, it is a hallucination — penalize heavily. "
            "Do NOT infer or assume information not explicitly stated in the KB."
        )
        prompt = (
            "EVALUATION RUBRIC — Score each 1-10:\n\n"
            "ChatScore: Overall quality of the text chat interaction\n"
            "VoiceScore: Overall quality of the voice mock call\n\n"
            "ProductKnowledge:\n"
            "  9-10: Every claim verified in KB, shows deep understanding\n"
            "  6-8: Mostly accurate, 1-2 minor gaps\n"
            "  3-5: Several fabrications or significant gaps\n"
            "  1-2: Mostly wrong or entirely fabricated\n\n"
            "Discovery:\n"
            "  9-10: 3+ insightful qualifying questions that reveal buyer's pain\n"
            "  6-8: 1-2 decent questions asked\n"
            "  3-5: Only surface questions or missed opportunities\n"
            "  1-2: Zero discovery attempted\n\n"
            "ObjectionHandling:\n"
            "  9-10: Acknowledged concern, empathized, provided KB-backed rebuttal\n"
            "  6-8: Addressed but lacked proof points or empathy\n"
            "  3-5: Generic deflection\n"
            "  1-2: Ignored or argued with prospect\n\n"
            "Communication:\n"
            "  9-10: Clear, concise, adapted to prospect, no jargon\n"
            "  6-8: Generally clear, minor jargon or over-talking\n"
            "  3-5: Confusing, too technical, or talked past customer\n"
            "  1-2: Incoherent or completely scripted without listening\n\n"
            "ClosingClarity:\n"
            "  9-10: Confidently proposed specific next step with timeline\n"
            "  6-8: Suggested vague next steps\n"
            "  3-5: Weak or no close\n"
            "  1-2: Lost control of conversation, no close\n\n"
            "═══ CALIBRATION EXAMPLES ═══\n\n"
            "EXAMPLE A — Strong Rep (scores ~8-9):\n"
            "Rep correctly names all product features from KB, asks 3 discovery questions "
            "(budget, timeline, current tools), handles price objection by referencing ROI from KB, "
            "closes with 'Let me schedule a 30-min demo for Thursday — does 2pm work?'\n"
            "→ ProductKnowledge:9, Discovery:9, ObjectionHandling:8, Communication:8, ClosingClarity:9\n\n"
            "EXAMPLE B — Average Rep (scores ~5-6):\n"
            "Rep describes product accurately but misses one key feature, asks only 1 surface question "
            "('How big is your team?'), responds to objection with generic 'we're the best value' "
            "without KB proof, closes with 'Let me know if you want to move forward.'\n"
            "→ ProductKnowledge:7, Discovery:5, ObjectionHandling:5, Communication:6, ClosingClarity:5\n\n"
            "EXAMPLE C — Weak Rep (scores ~2-3):\n"
            "Rep invents a feature not in KB, asks zero discovery questions, dismisses objection "
            "('that's not really an issue'), uses heavy jargon, never attempts a close.\n"
            "→ ProductKnowledge:2, Discovery:1, ObjectionHandling:3, Communication:3, ClosingClarity:1\n\n"
            "═══ END CALIBRATION ═══\n\n"
            "ANTI-HALLUCINATION STEP (required):\n"
            "Before scoring, list EVERY factual product claim the rep made. "
            "Mark each as [VERIFIED] or [NOT IN KB]. Use [NOT IN KB] claims to reduce ProductKnowledge score.\n\n"
            f"══ Knowledge Base Context (ground truth — ONLY score against this) ══\n{context}\n\n"
            f"══ Chat Transcript ══\n{chat_transcript}\n\n"
            f"══ Voice Mock Call Transcript ══\n{voice_transcript}\n\n"
            "OUTPUT FORMAT (exact):\n"
            "FactCheck: [list each claim with VERIFIED or NOT IN KB]\n"
            "ChatScore: [1-10]\n"
            "VoiceScore: [1-10]\n"
            "ProductKnowledge: [1-10]\n"
            "Discovery: [1-10]\n"
            "ObjectionHandling: [1-10]\n"
            "Communication: [1-10]\n"
            "ClosingClarity: [1-10]\n"
            "ChatFeedback: [2-3 sentences]\n"
            "VoiceFeedback: [2-3 sentences]"
        )
        response = llm_client.generate(
            [{"role": "user", "content": prompt}], system=system, max_tokens=2048
        )

        def _get(pattern):
            m = re.search(pattern, response, re.IGNORECASE)
            return min(10, max(1, int(m.group(1)))) if m else 0

        chat_score = _get(r"ChatScore:\s*(\d+)")
        voice_score = _get(r"VoiceScore:\s*(\d+)")

        chat_fb = re.search(r"ChatFeedback:\s*(.*?)(?=VoiceFeedback:|$)", response, re.IGNORECASE | re.DOTALL)
        voice_fb = re.search(r"VoiceFeedback:\s*(.*)", response, re.IGNORECASE | re.DOTALL)

        return {
            "chat_score": chat_score,
            "voice_score": voice_score,
            "product_accuracy": _get(r"ProductKnowledge:\s*(\d+)"),
            "discovery": _get(r"Discovery:\s*(\d+)"),
            "objection_handling": _get(r"ObjectionHandling:\s*(\d+)"),
            "empathy": _get(r"Communication:\s*(\d+)"),
            "closing_clarity": _get(r"ClosingClarity:\s*(\d+)"),
            "chat_feedback": chat_fb.group(1).strip() if chat_fb else "No chat feedback.",
            "voice_feedback": voice_fb.group(1).strip() if voice_fb else "No voice feedback.",
            "raw_response": response,
        }

    def evaluate_round2_call(self, voice_transcript, context):
        """
        Evaluates a Tier 3 Round 2 voice call (learner = counsellor, AI = prospect).
        Returns per-dimension scores plus strengths, improvement areas, priority focus,
        and a hiring decision (threshold VoiceScore >= 7.0).
        """
        system = prompts.tier3_eval_system()
        prompt = prompts.tier3_eval_prompt(context, voice_transcript)
        response = llm_client.generate(
            [{"role": "user", "content": prompt}], system=system, max_tokens=2048
        )

        def _get(pattern):
            m = re.search(pattern, response, re.IGNORECASE)
            return min(10, max(1, int(m.group(1)))) if m else 0

        def _section(label, next_labels):
            stop = "|".join(next_labels) if next_labels else "$"
            m = re.search(
                rf"{label}:\s*(.*?)(?=(?:{stop}):|$)",
                response,
                re.IGNORECASE | re.DOTALL,
            )
            return m.group(1).strip() if m else ""

        product_accuracy = _get(r"ProductAccuracy:\s*(\d+)")
        discovery = _get(r"Discovery:\s*(\d+)")
        objection_handling = _get(r"ObjectionHandling:\s*(\d+)")
        empathy = _get(r"Empathy:\s*(\d+)")
        closing_clarity = _get(r"ClosingClarity:\s*(\d+)")

        voice_score = _get(r"VoiceScore:\s*(\d+)")
        if voice_score == 0:
            dims = [product_accuracy, discovery, objection_handling, empathy, closing_clarity]
            valid = [d for d in dims if d > 0]
            voice_score = round(sum(valid) / len(valid), 2) if valid else 0

        strengths = _section("Strengths", ["ImprovementAreas", "PriorityFocus", "HiringDecision"])
        improvements = _section("ImprovementAreas", ["PriorityFocus", "HiringDecision"])
        priority = _section("PriorityFocus", ["HiringDecision"])

        hd_match = re.search(r"HiringDecision:\s*(.*)", response, re.IGNORECASE)
        if hd_match and hd_match.group(1).strip():
            hiring_decision = hd_match.group(1).strip().splitlines()[0].strip()
        else:
            hiring_decision = "Hire" if float(voice_score) >= 7.0 else "Not Ready Yet"

        return {
            "voice_score": voice_score,
            "product_accuracy": product_accuracy,
            "discovery": discovery,
            "objection_handling": objection_handling,
            "empathy": empathy,
            "closing_clarity": closing_clarity,
            "strengths": strengths or "No specific strengths captured.",
            "improvement_areas": improvements or "No specific improvements captured.",
            "priority_focus": priority or "No priority focus captured.",
            "hiring_decision": hiring_decision,
            "raw_response": response,
        }

    def combine_scores(self, voice_score, text_score):
        voice = float(voice_score or 0)
        text = float(text_score or 0)

        if voice <= 0:
            final_score = round(text, 2)
        elif text <= 0:
            final_score = round(voice, 2)
        else:
            final_score = round((voice + text) / 2, 2)

        hiring_decision = "Hire" if final_score >= 7.0 else "Do Not Hire"
        return final_score, hiring_decision


evaluator = Evaluator()
