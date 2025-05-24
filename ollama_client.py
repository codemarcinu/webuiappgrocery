from typing import Optional, Dict, Any
from config import get_settings
from logging_config import logger
from ollama import AsyncClient, Client, RequestError, ResponseError
import aiohttp
import asyncio

settings = get_settings()

class OllamaError(Exception):
    """Base exception for Ollama client errors"""
    pass

class OllamaTimeoutError(OllamaError):
    """Exception raised when Ollama request times out"""
    pass

class OllamaConnectionError(OllamaError):
    """Exception raised when connection to Ollama fails"""
    pass

class OllamaModelError(OllamaError):
    """Exception raised when model is not available or invalid"""
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
        return any(model['name'] == settings.OLLAMA_MODEL for model in models['models'])
    except Exception as e:
        logger.error(f"Failed to verify model availability: {str(e)}")
        return False

async def ollama_generate(
    prompt: str,
    system: Optional[str] = None,
    stream: bool = False,
    timeout: Optional[float] = None
) -> str:
    """
    Generate text using Ollama API with enhanced error handling and verification
    
    Args:
        prompt: The prompt to send to Ollama
        system: Optional system message
        stream: Whether to stream the response
        timeout: Optional timeout in seconds (overrides config)
        
    Returns:
        Generated text response
        
    Raises:
        OllamaTimeoutError: If the request times out
        OllamaConnectionError: If connection to Ollama fails
        OllamaModelError: If the configured model is not available
        OllamaError: For other Ollama-related errors
    """
    # Verify Ollama connection first
    if not await verify_ollama_connection():
        raise OllamaConnectionError("Ollama service is not accessible. Please check if Ollama is running.")
    
    # Verify model availability
    if not await verify_model_availability():
        raise OllamaModelError(f"Model '{settings.OLLAMA_MODEL}' is not available in Ollama. Please check your configuration.")
    
    # Use provided timeout or fall back to config
    timeout_value = timeout if timeout is not None else settings.OLLAMA_TIMEOUT
    
    try:
        client = AsyncClient(
            host=settings.OLLAMA_API_URL,
            timeout=timeout_value
        )
        
        logger.debug(f"Sending request to Ollama with timeout {timeout_value}s")
        logger.debug(f"Using model: {settings.OLLAMA_MODEL}")
        
        response = await client.generate(
            model=settings.OLLAMA_MODEL,
            prompt=prompt,
            system=system,
            stream=stream
        )
        
        return response.response
            
    except (RequestError, ResponseError) as e:
        if "timeout" in str(e).lower():
            logger.error(f"Ollama request timed out after {timeout_value}s: {str(e)}")
            raise OllamaTimeoutError(f"Request to Ollama timed out after {timeout_value}s")
        elif "connection" in str(e).lower():
            logger.error(f"Failed to connect to Ollama: {str(e)}")
            raise OllamaConnectionError("Could not connect to Ollama service")
        elif "model" in str(e).lower():
            logger.error(f"Model error: {str(e)}")
            raise OllamaModelError(f"Error with model '{settings.OLLAMA_MODEL}': {str(e)}")
        else:
            logger.error(f"Ollama API error: {str(e)}")
            raise OllamaError(f"Ollama API error: {str(e)}")
            
    except Exception as e:
        logger.error(f"Unexpected error in Ollama request: {str(e)}")
        raise OllamaError(f"Unexpected error: {str(e)}") 