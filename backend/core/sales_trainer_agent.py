"""
SalesTrainerAgent
=================
Defines the LiveKit Agent personality for mock sales call training.
This module is imported by voice_agent_worker.py — plugin instances
are created at the worker's module level (main thread) and injected
into AgentSession there.
"""
from livekit.agents import Agent


class SalesTrainerAgent(Agent):
    """
    Acts as a demanding-but-fair customer prospect during a mock sales call.
    Personalised with knowledge-base context retrieved from the selected module.
    """

    def __init__(self, kb_context: str = "") -> None:
        instructions = (
            "You are an AI sales trainer running a realistic mock sales call. "
            "Act as a potential customer (prospect) asking about a product or service. "
            "Ask discovery questions, raise realistic objections (price, implementation "
            "time, trust, competing solutions), and keep the conversation focused on "
            "business value — not technical details. "
            "Use the company knowledge base context provided to stay grounded in the "
            "actual product. If the context does not contain the answer, say you do "
            "not have enough information. "
            "IMPORTANT: Speak naturally and conversationally. Do NOT include stage "
            "directions, sound effects, or bracketed text like [Phone rings] in your "
            "responses. Keep each reply concise (1-3 sentences)."
        )
        if kb_context.strip():
            instructions += (
                f"\n\nCompany knowledge base context:\n{kb_context.strip()}"
            )
        else:
            instructions += (
                "\n\nNo company knowledge base context is available for this session."
            )

        super().__init__(instructions=instructions)
