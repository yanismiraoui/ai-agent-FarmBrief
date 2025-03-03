import os
from typing import Optional
import httpx

class AudioGenerator:
    def __init__(self):
        self.api_key = os.getenv("ELEVEN_LABS_API_KEY")
        self.base_url = "https://api.elevenlabs.io/v1"
        self.voice_id = "21m00Tcm4TlvDq8ikWAM"  # Default voice ID (you can change this)
        
    async def generate_audio(self, text: str, voice_id: Optional[str] = None) -> bytes:
        """Generate audio from text using Eleven Labs API."""
        if not self.api_key:
            raise ValueError("Eleven Labs API key not found in environment variables. Please add ELEVEN_LABS_API_KEY to your .env file.")
        
        url = f"{self.base_url}/text-to-speech/{voice_id or self.voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, headers=headers)
                if response.status_code == 401:
                    raise ValueError("Invalid or expired ElevenLabs API key. Please check your API key in the .env file.")
                response.raise_for_status()
                return response.content
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise ValueError("ElevenLabs API rate limit exceeded. Please try again later or upgrade your plan.")
            elif e.response.status_code == 400:
                raise ValueError(f"Bad request to ElevenLabs API. Error: {e.response.text}")
            else:
                raise ValueError(f"Error from ElevenLabs API: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise ValueError(f"Failed to generate audio: {str(e)}")
    
    async def list_voices(self) -> list:
        """Get available voices from Eleven Labs API."""
        if not self.api_key:
            raise ValueError("Eleven Labs API key not found in environment variables")
        
        url = f"{self.base_url}/voices"
        headers = {"xi-api-key": self.api_key}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()["voices"] 