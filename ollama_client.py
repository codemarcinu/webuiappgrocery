import httpx

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "bielik-local-q8:latest"

async def ollama_generate(prompt: str, system: str = None, stream: bool = False) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": stream
    }
    if system:
        payload["system"] = system

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "") 