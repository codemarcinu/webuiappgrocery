from typing import Optional, Dict, Any
from config import get_settings
import logging
from ollama import AsyncClient, Client, RequestError, ResponseError
from user_activity_logger import user_activity_logger
import aiohttp
import asyncio
from models import LogBledow, PoziomLogu
from db_logger import log_to_db
from database import SessionLocal
import json
import os
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

class OllamaError(Exception):
    """Base exception for Ollama client errors"""
    pass

class OllamaConnectionError(OllamaError):
    """Exception raised when there are connection issues with Ollama"""
    pass

class OllamaTimeoutError(OllamaError):
    """Exception raised when Ollama request times out"""
    pass

class OllamaModelError(OllamaError):
    """Exception raised when there are issues with the Ollama model"""
    pass

class OllamaClient:
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.OLLAMA_API_URL
        self.model = self.settings.OLLAMA_MODEL
        self.timeout = self.settings.OLLAMA_TIMEOUT
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            verify=False  # Disable SSL verification for local development
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((OllamaConnectionError, OllamaTimeoutError))
    )
    async def generate(self, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
        """Generate text using Ollama model"""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False
            }
            if system:
                payload["system"] = system

            logger.debug(f"Sending request to Ollama with timeout {self.timeout}s")
            logger.debug(f"Using model: {self.model}")
            logger.debug(f"Prompt length: {len(prompt)}")
            if system:
                logger.debug(f"System prompt length: {len(system)}")

            response = await self.client.post("/api/generate", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as e:
            logger.error(f"Timeout while generating text: {str(e)}")
            raise OllamaTimeoutError(f"Request timed out after {self.timeout} seconds. The receipt may be too complex or the model may be overloaded.")
        except httpx.RequestError as e:
            logger.error(f"Connection error while generating text: {str(e)}")
            raise OllamaConnectionError(f"Failed to connect to Ollama: {str(e)}")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error while generating text: {str(e)}")
            if e.response.status_code == 404:
                raise OllamaModelError(f"Model {self.model} not found")
            raise OllamaError(f"HTTP error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error while generating text: {str(e)}")
            raise OllamaError(f"Unexpected error: {str(e)}")

async def verify_ollama_connection() -> bool:
    """
    Verify that Ollama service is running and accessible
    
    Returns:
        bool: True if Ollama is accessible, False otherwise
    """
    try:
        settings = get_settings()
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{settings.OLLAMA_API_URL}/api/tags", timeout=5) as response:
                return response.status == 200
    except Exception as e:
        logger.error(f"Failed to verify Ollama connection: {str(e)}")
        return False

async def verify_model_availability() -> bool:
    """
    Verify that the configured model is available in Ollama
    
    Returns:
        bool: True if model is available, False otherwise
    """
    try:
        settings = get_settings()
        client = Client(host=settings.OLLAMA_API_URL)
        models = client.list()
        is_available = any(model['name'] == settings.OLLAMA_MODEL for model in models['models'])
        
        user_activity_logger.log_ollama_operation(
            "verify_model_availability",
            {
                "model": settings.OLLAMA_MODEL,
                "available": is_available,
                "available_models": [model['name'] for model in models['models']]
            },
            "success" if is_available else "model_not_found"
        )
        
        return is_available
    except Exception as e:
        user_activity_logger.log_error(
            e,
            {
                "module": "ollama_client",
                "function": "verify_model_availability",
                "model": settings.OLLAMA_MODEL
            }
        )
        logger.error(f"Failed to verify model availability: {str(e)}")
        return False

def log_to_db(poziom: PoziomLogu, modul: str, funkcja: str, komunikat: str, szczegoly: str = None):
    """Helper function to log to database"""
    try:
        with SessionLocal() as db:
            log = LogBledow(
                poziom=poziom,
                modul_aplikacji=modul,
                funkcja=funkcja,
                komunikat_bledu=komunikat,
                szczegoly_techniczne=szczegoly
            )
            db.add(log)
            db.commit()
    except Exception as e:
        # Fallback to regular logging if database logging fails
        logger.error(f"Failed to log to database: {str(e)}")
        logger.error(f"Original log message: {komunikat}")
        if szczegoly:
            logger.error(f"Details: {szczegoly}")

async def ollama_generate(prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
    """Helper function to generate text using Ollama"""
    async with OllamaClient() as client:
        return await client.generate(prompt, system)

async def ollama_generate_old(
    prompt: str,
    system: Optional[str] = None,
    stream: bool = False,
    timeout: Optional[float] = None
) -> str:
    """
    Generate text using Ollama model
    
    Args:
        prompt: The input prompt
        system: Optional system prompt
        stream: Whether to stream the response
        timeout: Optional timeout in seconds
        
    Returns:
        str: Generated text
        
    Raises:
        OllamaError: Base exception for Ollama errors
        OllamaConnectionError: When connection fails
        OllamaTimeoutError: When request times out
        OllamaModelError: When model is not available or fails
    """
    settings = get_settings()
    timeout_value = timeout or settings.OLLAMA_TIMEOUT
    
    try:
        log_to_db(
            PoziomLogu.INFO,
            "ollama_client",
            "ollama_generate",
            f"Rozpoczęcie generowania tekstu z modelem {settings.OLLAMA_MODEL}",
            json.dumps({
                "model": settings.OLLAMA_MODEL,
                "prompt_length": len(prompt),
                "has_system_prompt": bool(system),
                "stream": stream,
                "timeout": timeout_value,
                "status": "started"
            })
        )
        
        logger.debug(f"Sending request to Ollama with timeout {timeout_value}s")
        logger.debug(f"Using model: {settings.OLLAMA_MODEL}")
        
        user_activity_logger.log_ollama_operation(
            "generate",
            {
                "model": settings.OLLAMA_MODEL,
                "prompt_length": len(prompt),
                "has_system_prompt": bool(system),
                "stream": stream,
                "timeout": timeout_value
            },
            "started"
        )
        
        client = AsyncClient(
            host=settings.OLLAMA_API_URL,
            timeout=timeout_value
        )
        
        response = await client.generate(
            model=settings.OLLAMA_MODEL,
            prompt=prompt,
            system=system,
            stream=stream
        )
        
        user_activity_logger.log_ollama_operation(
            "generate",
            {
                "model": settings.OLLAMA_MODEL,
                "response_length": len(response.response),
                "prompt_length": len(prompt)
            },
            "success"
        )
        
        log_to_db(
            PoziomLogu.INFO,
            "ollama_client",
            "ollama_generate",
            f"Generowanie tekstu zakończone pomyślnie dla modelu {settings.OLLAMA_MODEL}",
            json.dumps({
                "model": settings.OLLAMA_MODEL,
                "status": "completed"
            })
        )
        
        return response.response
            
    except (RequestError, ResponseError) as e:
        if "timeout" in str(e).lower():
            user_activity_logger.log_error(
                e,
                {
                    "module": "ollama_client",
                    "function": "ollama_generate",
                    "error_type": "OllamaTimeoutError",
                    "timeout": timeout_value
                }
            )
            logger.error(f"Ollama request timed out after {timeout_value}s: {str(e)}")
            raise OllamaTimeoutError(f"Request to Ollama timed out after {timeout_value}s")
        elif "connection" in str(e).lower():
            user_activity_logger.log_error(
                e,
                {
                    "module": "ollama_client",
                    "function": "ollama_generate",
                    "error_type": "OllamaConnectionError"
                }
            )
            logger.error(f"Failed to connect to Ollama: {str(e)}")
            raise OllamaConnectionError("Could not connect to Ollama service")
        elif "model" in str(e).lower():
            user_activity_logger.log_error(
                e,
                {
                    "module": "ollama_client",
                    "function": "ollama_generate",
                    "error_type": "OllamaModelError",
                    "model": settings.OLLAMA_MODEL
                }
            )
            logger.error(f"Model error: {str(e)}")
            raise OllamaModelError(f"Error with model '{settings.OLLAMA_MODEL}': {str(e)}")
        else:
            user_activity_logger.log_error(
                e,
                {
                    "module": "ollama_client",
                    "function": "ollama_generate",
                    "error_type": "OllamaError"
                }
            )
            logger.error(f"Ollama API error: {str(e)}")
            raise OllamaError(f"Ollama API error: {str(e)}")
            
    except Exception as e:
        user_activity_logger.log_error(
            e,
            {
                "module": "ollama_client",
                "function": "ollama_generate",
                "error_type": "UnexpectedError"
            }
        )
        logger.error(f"Unexpected error in Ollama request: {str(e)}")
        raise OllamaError(f"Unexpected error: {str(e)}") 