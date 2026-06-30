import asyncio
from livekit.plugins import groq
from livekit.agents import llm

import os

async def main():
    l = groq.LLM(api_key=os.getenv("GROQ_API_KEY"))
    ctx = llm.ChatContext()
    ctx.add_message(role="user", content="hello")
    print("Starting chat request...")
    stream = l.chat(chat_ctx=ctx)
    async for chunk in stream:
        print(chunk)
    print("Done!")

asyncio.run(main())
