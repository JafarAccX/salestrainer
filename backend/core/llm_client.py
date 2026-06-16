from anthropic import Anthropic
from config import config


class ClaudeClient:
    def __init__(self):
        self.api_key = config.ANTHROPIC_API_KEY
        self.model = config.MODEL_NAME
        self.client = Anthropic(api_key=self.api_key) if self.api_key else None

    def generate(self, messages, system=None, temperature=0.4, max_tokens=1024):
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
            return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        except Exception as e:
            print(f"Error calling Claude API: {e}")
            return "Sorry, there was an error connecting to the AI model."


llm_client = ClaudeClient()
