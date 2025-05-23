from typing import Optional, Dict, Any
from config import get_settings
from logging_config import logger
from ollama import AsyncClient, Client, RequestError, ResponseError

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

async def ollama_generate(
    prompt: str,
    system: Optional[str] = None,
    stream: bool = False,
    timeout: Optional[float] = None
) -> str:
    """
    Generate text using Ollama API
    
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
        OllamaError: For other Ollama-related errors
    """
    # Use provided timeout or fall back to config
    timeout_value = timeout if timeout is not None else settings.OLLAMA_TIMEOUT
    
    try:
        client = AsyncClient(
            host=settings.OLLAMA_API_URL,
            timeout=timeout_value
        )
        
        logger.debug(f"Sending request to Ollama with timeout {timeout_value}s")
        
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
        else:
            logger.error(f"Ollama API error: {str(e)}")
            raise OllamaError(f"Ollama API error: {str(e)}")
            
    except Exception as e:
        logger.error(f"Unexpected error in Ollama request: {str(e)}")
        raise OllamaError(f"Unexpected error: {str(e)}") 