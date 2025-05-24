from typing import Optional, Dict, Any
from config import get_settings
from logging_config import logger
from ollama import AsyncClient, Client, RequestError, ResponseError
from user_activity_logger import user_activity_logger
import aiohttp
import asyncio
from models import LogBledow, PoziomLogu
from database import SessionLocal
import json

settings = get_settings()

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

async def verify_ollama_connection() -> bool:
    """
    Verify that Ollama service is running and accessible
    
    Returns:
        bool: True if Ollama is accessible, False otherwise
    """
    try:
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

async def ollama_generate(
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