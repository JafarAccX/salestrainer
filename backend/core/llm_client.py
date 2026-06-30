from anthropic import Anthropic
from config import config
from core.token_tracker import token_tracker
import logging

logger = logging.getLogger(__name__)


class ClaudeClient:
    def __init__(self):
        self.api_key = config.ANTHROPIC_API_KEY
        self.model = config.MODEL_NAME
        self.client = Anthropic(api_key=self.api_key) if self.api_key else None

    def generate(
        self,
        messages,
        system=None,
        temperature=0.4,
        max_tokens=1024,
        session_id=None,
        course_id=None,
        user_id=None,
    ):
        if not self.client:
            return "ANTHROPIC_API_KEY is not configured."
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages,
            )

            # Record token usage (soft tracking — never blocks the call).
            try:
                usage = getattr(response, "usage", None)
                if usage is not None:
                    token_tracker.record(
                        session_id=session_id,
                        input_tokens=getattr(usage, "input_tokens", 0) or 0,
                        output_tokens=getattr(usage, "output_tokens", 0) or 0,
                        course_id=course_id,
                        user_id=user_id,
                    )
            except Exception as track_err:
                logger.warning("Token tracking failed (non-fatal): %s", track_err)

            return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        except Exception as e:
            logger.error("LLM API call failed: %s", e)
            raise RuntimeError(f"LLM API error: {e}") from e


llm_client = ClaudeClient()
