"""Quick test: can the ElevenLabs STT websocket connect?"""
import asyncio
import json
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

async def test_elevenlabs_stt():
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        print("ERROR: ELEVENLABS_API_KEY not set")
        return

    print(f"Key: {key[:12]}...{key[-6:]}")

    try:
        import websockets
    except ImportError:
        print("Installing websockets...")
        os.system("pip install websockets")
        import websockets

    ws_url = (
        "wss://api.elevenlabs.io/v1/speech-to-text/stream"
        "?model_id=scribe_v2_realtime&language_code=en"
    )
    print(f"Connecting to ElevenLabs STT WebSocket...")
    
    try:
        async with websockets.connect(
            ws_url,
            additional_headers={"xi-api-key": key},
            close_timeout=5,
        ) as ws:
            print("✅ WebSocket connected successfully!")
            
            # Send a begin message
            await ws.send(json.dumps({"type": "start"}))
            print("Sent start message, waiting for response...")
            
            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=5)
                print(f"✅ Response: {resp}")
            except asyncio.TimeoutError:
                print("⚠️ No response in 5s (may be normal - waiting for audio)")
            except Exception as e:
                print(f"❌ Receive error: {type(e).__name__}: {e}")
                
    except Exception as e:
        print(f"❌ Connection failed: {type(e).__name__}: {e}")

    # Also test Deepgram as alternative
    dg_key = os.getenv("DEEPGRAM_API_KEY")
    if dg_key:
        print(f"\nDeepgram key present: {dg_key[:10]}...")
        import requests
        r = requests.get(
            "https://api.deepgram.com/v1/projects",
            headers={"Authorization": f"Token {dg_key}"}
        )
        print(f"Deepgram API status: {r.status_code}")
        if r.status_code != 200:
            print(f"Deepgram response: {r.text[:200]}")
    else:
        print("\nNo DEEPGRAM_API_KEY set")

if __name__ == "__main__":
    asyncio.run(test_elevenlabs_stt())
