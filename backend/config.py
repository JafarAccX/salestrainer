import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

class Config:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    MODEL_NAME = os.getenv("MODEL_NAME", "claude-haiku-4-5-20251001")

    # Resolve paths relative to the project root, regardless of where script is run
    VECTOR_DB_DIR = str(PROJECT_ROOT / os.getenv("VECTOR_DB_DIR", "./chroma_db").lstrip("./\\"))
    UPLOAD_DIR = str(PROJECT_ROOT / os.getenv("UPLOAD_DIR", "./uploads").lstrip("./\\"))
    KB_STORE_DIR = str(PROJECT_ROOT / os.getenv("KB_STORE_DIR", "./kb_store").lstrip("./\\"))

    LIVEKIT_URL = os.getenv("LIVEKIT_URL")
    LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
    LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
    LIVEKIT_AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "sales-trainer-agent")
    LIVEKIT_PLAYGROUND_URL = os.getenv("LIVEKIT_PLAYGROUND_URL", "https://agents-playground.livekit.io/")

    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
    VOICE_STT_PROVIDER = os.getenv("VOICE_STT_PROVIDER", "elevenlabs")
    VOICE_TTS_PROVIDER = os.getenv("VOICE_TTS_PROVIDER", "cartesia")

config = Config()

# Ensure directories exist
os.makedirs(config.VECTOR_DB_DIR, exist_ok=True)
os.makedirs(config.UPLOAD_DIR, exist_ok=True)
os.makedirs(config.KB_STORE_DIR, exist_ok=True)
