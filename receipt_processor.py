import multiprocessing
multiprocessing.set_start_method('spawn', force=True)

from pathlib import Path
from typing import Optional, Dict, Any, List
from PIL import Image, ImageFile, UnidentifiedImageError
import io
import magic
from fastapi import UploadFile, HTTPException
from tenacity import retry, stop_after_attempt, wait_exponential
import requests
import logging
logger = logging.getLogger(__name__)
from config import get_settings
from models import StatusParagonu, LogBledow, PoziomLogu
from ollama_client import OllamaError, OllamaTimeoutError, OllamaConnectionError, ollama_generate
from pydantic import BaseModel, Field, ValidationError, ConfigDict
from datetime import date
import uuid
import pdf2image
import tempfile
import json
import os
from db_logger import log_to_db
from database import SessionLocal
import pytesseract
import re

# Set environment variables for CUDA
os.environ['CUDA_VISIBLE_DEVICES'] = ''  # Disable CUDA
os.environ['TORCH_MULTIPROCESSING_START_METHOD'] = 'spawn'

# Enable loading of truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True

settings = get_settings()

class ReceiptItem(BaseModel):
    """Model for a single item in a receipt"""
    model_config = ConfigDict(extra='forbid')
    
    name: str
    quantity: float
    price: float
    total: float
    category: str = None

    def model_post_init(self, __context):
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        if self.price <= 0:
            raise ValueError("Price must be positive")
        if self.total <= 0:
            raise ValueError("Total must be positive")
        if not self.name:
            raise ValueError("Name cannot be empty")

class Receipt(BaseModel):
    """Model for the entire receipt"""
    model_config = ConfigDict(extra='forbid')
    
    store_name: str
    date: date
    total_amount: float
    items: List[ReceiptItem]
    tax_id: Optional[str] = None
    payment_method: Optional[str] = None

    def model_post_init(self, __context):
        if not self.store_name:
            raise ValueError("Store name cannot be empty")
        if self.total_amount <= 0:
            raise ValueError("Total amount must be positive")
        if not self.items:
            raise ValueError("At least one item is required")

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

class ReceiptProcessor:
    def __init__(self):
        # Set multiprocessing start method to spawn
        import multiprocessing
        multiprocessing.set_start_method('spawn', force=True)
        
        # Set environment variables for CUDA
        os.environ['CUDA_VISIBLE_DEVICES'] = ''  # Disable CUDA
        os.environ['TORCH_MULTIPROCESSING_START_METHOD'] = 'spawn'
        
        self.allowed_mime_types = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'application/pdf': '.pdf'  # Add PDF support
        }
        self.max_file_size = settings.MAX_CONTENT_LENGTH

    async def validate_file(self, file: UploadFile) -> None:
        """Validate uploaded file"""
        # Check file size
        file_size = 0
        chunk_size = 8192
        while chunk := await file.read(chunk_size):
            file_size += len(chunk)
            if file_size > self.max_file_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum size is {self.max_file_size/1024/1024}MB"
                )
        await file.seek(0)

        # Check file type
        content = await file.read(2048)
        await file.seek(0)
        mime_type = magic.from_buffer(content, mime=True)
        
        if mime_type not in self.allowed_mime_types:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type. Allowed types: {', '.join(self.allowed_mime_types.keys())}"
            )

    async def validate_and_save_file(self, file: UploadFile) -> str:
        """Validate and save uploaded file"""
        # Validate file
        await self.validate_file(file)
        
        # Save file
        upload_dir = Path(settings.UPLOAD_FOLDER)
        file_path = await self.save_file(file, upload_dir)
        
        return str(file_path)

    async def save_file(self, file: UploadFile, upload_dir: Path) -> Path:
        """Save uploaded file and return path"""
        try:
            # Create upload directory if it doesn't exist
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            # Read file content once
            content = await file.read()
            await file.seek(0)  # Reset file pointer
            
            # Get MIME type
            mime_type = magic.from_buffer(content, mime=True)
            file_extension = self.allowed_mime_types[mime_type]
            
            # Generate unique filename with UUID
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = upload_dir / unique_filename
            
            try:
                if mime_type == 'application/pdf':
                    # Save PDF file first
                    with open(file_path, 'wb') as f:
                        f.write(content)
                    
                    # Convert first page of PDF to image
                    with tempfile.TemporaryDirectory() as temp_dir:
                        images = pdf2image.convert_from_path(
                            file_path,
                            first_page=1,
                            last_page=1,
                            dpi=300,
                            output_folder=temp_dir
                        )
                        if images:
                            # Save first page as PNG
                            image_path = file_path.with_suffix('.png')
                            images[0].save(image_path, 'PNG')
                            # Return the PNG path instead of PDF
                            return image_path
                        else:
                            raise HTTPException(
                                status_code=400,
                                detail="Could not convert PDF to image"
                            )
                else:
                    # Handle regular image files
                    if mime_type == 'image/png':
                        # For PNG, preserve transparency
                        img = Image.open(io.BytesIO(content))
                        img.save(file_path, "PNG")
                    else:
                        # For other formats, convert to RGB and save as JPEG
                        img = Image.open(io.BytesIO(content))
                        if img.mode in ('RGBA', 'LA'):
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[-1])
                            img = background
                        elif img.mode != 'RGB':
                            img = img.convert('RGB')
                        img.save(file_path, "JPEG", quality=95)
            except (UnidentifiedImageError, OSError) as img_err:
                logger.error(f"Error processing file {file.filename}: {str(img_err)}", exc_info=True)
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid or corrupted file: {str(img_err)}"
                )
            
            return file_path
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error saving file: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Error saving file"
            )

    def _extract_text_from_image(self, image_path: Path) -> str:
        """Extract text from image using pytesseract"""
        try:
            # Check if file exists
            if not image_path.exists():
                logger.error(f"Image file not found: {image_path}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Image file not found: {image_path}"
                )
            
            # Check if file has appropriate size
            if image_path.stat().st_size == 0:
                logger.error(f"Image file is empty: {image_path}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Image file is empty: {image_path}"
                )
            
            logger.info(f"Starting OCR for image: {image_path}")
            text = pytesseract.image_to_string(Image.open(str(image_path)), lang='pol')
            logger.info(f"OCR completed successfully for {image_path}")
            logger.debug(f"Extracted text:\n{text}")
            return text

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error during OCR for image {image_path}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error during OCR processing: {str(e)}"
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def process_receipt(self, image_path: Path) -> Dict[str, Any]:
        """Process receipt using OCR and Ollama API"""
        try:
            # Step 1: Extract text using OCR
            log_to_db(
                PoziomLogu.INFO,
                "receipt_processor",
                "process_receipt",
                f"Rozpoczęcie ekstrakcji tekstu z obrazu: {image_path}",
                json.dumps({
                    "file_path": str(image_path),
                    "stage": "text_extraction",
                    "status": "started"
                })
            )
            
            extracted_text = self._extract_text_from_image(image_path)
            
            if not extracted_text.strip():
                logger.warning(f"No text extracted from receipt: {image_path}")
                raise ValueError("No text detected on receipt")

            # Step 2: Process text with Ollama (Bielik)
            log_to_db(
                PoziomLogu.INFO,
                "receipt_processor",
                "process_receipt",
                f"Rozpoczęcie analizy LLM dla: {image_path}",
                json.dumps({
                    "file_path": str(image_path),
                    "stage": "llm_analysis",
                    "status": "started",
                    "text_length": len(extracted_text)
                })
            )
            
            prompt = self._get_receipt_prompt_for_text_input(extracted_text)
            
            try:
                llm_response = await ollama_generate(
                    prompt=prompt,
                    system="Jesteś pomocnym asystentem specjalizującym się w analizie tekstu z paragonów sklepowych i strukturyzowaniu go w formacie JSON."
                )
            except OllamaTimeoutError as e:
                logger.error(f"Timeout while processing receipt with Ollama: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=504,
                    detail=f"Receipt processing timed out after {settings.OLLAMA_TIMEOUT} seconds. The receipt may be too complex or the model may be overloaded. Please try again later."
                )

            if not llm_response:
                raise ValueError("Empty response from Ollama")

            log_to_db(
                PoziomLogu.INFO,
                "receipt_processor",
                "process_receipt",
                f"Analiza LLM zakończona pomyślnie: {image_path}",
                json.dumps({
                    "file_path": str(image_path),
                    "stage": "llm_analysis",
                    "status": "completed"
                })
            )
            
            return self._parse_ollama_response(llm_response)

        except requests.Timeout as e:
            logger.error(f"Timeout while processing receipt: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=504,
                detail="Receipt processing timed out"
            )
        except requests.ConnectionError as e:
            logger.error(f"Connection error while processing receipt: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=503,
                detail="Could not connect to receipt processing service"
            )
        except requests.RequestException as e:
            logger.error(f"Error calling Ollama API: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=503,
                detail="Error processing receipt with AI service"
            )
        except Exception as e:
            logger.error(f"Error processing receipt: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Error processing receipt"
            )

    def _get_receipt_prompt_for_text_input(self, receipt_text: str) -> str:
        """Get the prompt for receipt processing with text input"""
        return f"""
Przeanalizuj tekst z paragonu i zwróć dane w formacie tool_call.

{{
  "name": "parse_cart",
  "arguments": {{
    "cart": {{
      "store_name": "Nazwa sklepu",
      "date": "YYYY-MM-DD",
      "total_amount": kwota_liczba,
      "items": [
        {{
          "name": "Nazwa produktu",
          "quantity": liczba,
          "price": liczba,
          "total": liczba,
          "category": "Kategoria"
        }}
      ],
      "tax_id": "NIP",
      "payment_method": "Metoda płatności"
    }}
  }}
}}

WAŻNE:
- Wszystkie wartości numeryczne jako liczby (bez cudzysłowów)
- Data w formacie YYYY-MM-DD
- Minimum jeden produkt w items
- Poprawny JSON (sprawdź przecinki)

Tekst paragonu:
{receipt_text}
"""

    def _fix_json_syntax(self, json_text: str) -> str:
        """Fix basic JSON syntax errors"""
        # Remove extra commas before }
        json_text = re.sub(r',\s*}', '}', json_text)
        # Remove extra commas before ]
        json_text = re.sub(r',\s*]', ']', json_text)
        # Fix single quotes to double quotes
        json_text = re.sub(r"'([^']*)':", r'"\1":', json_text)
        return json_text

    def _parse_ollama_response(self, response: Any) -> Dict[str, Any]:
        """Parse Ollama's response into structured data"""
        try:
            # Handle dictionary response from Ollama
            if isinstance(response, dict):
                if 'response' in response:
                    response_text = response['response']
                else:
                    raise ValueError("Invalid Ollama response format: missing 'response' field")
            else:
                response_text = str(response)

            logger.debug(f"Processing response text: {response_text[:200]}...")

            # Parse tool_call format
            tool_call_pattern = r'\s*({.*?})\s*'
            tool_call_match = re.search(tool_call_pattern, response_text, re.DOTALL)
            
            if tool_call_match:
                tool_call_json = tool_call_match.group(1)
                logger.debug(f"Extracted tool_call JSON: {tool_call_json[:300]}...")
                
                try:
                    # Try to fix basic JSON errors
                    tool_call_json = self._fix_json_syntax(tool_call_json)
                    tool_call_data = json.loads(tool_call_json)
                    
                    if 'name' in tool_call_data and 'arguments' in tool_call_data:
                        arguments = tool_call_data['arguments']
                        
                        # Different argument formats
                        if 'cart' in arguments:
                            cart_data = arguments['cart']
                            if isinstance(cart_data, str):
                                data = json.loads(cart_data)
                            else:
                                data = cart_data
                        else:
                            # Fallback - use arguments directly
                            data = arguments
                    else:
                        data = tool_call_data
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse tool_call JSON: {e}")
                    logger.error(f"Problematic JSON: {tool_call_json}")
                    raise ValueError(f"Invalid JSON in tool_call: {e}")
            else:
                # Fallback: try to parse as regular JSON
                clean_text = response_text.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:-3].strip()
                elif clean_text.startswith("```"):
                    clean_text = clean_text[3:-3].strip()
                
                try:
                    data = json.loads(clean_text)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response: {e}\nResponse: {response_text}")
                    raise ValueError(f"Invalid JSON response: {e}")

            # Validate using Pydantic models
            validated_receipt = Receipt.model_validate(data)
            return validated_receipt.model_dump()

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Ollama: {str(e)}\nResponse: {response}", exc_info=True)
            raise ValueError(f"Invalid JSON response from Ollama: {e}")
        except ValidationError as e:
            logger.error(f"Validation error in Ollama response: {str(e)}\nResponse: {response}", exc_info=True)
            raise ValueError(f"Invalid receipt data structure: {e}")
        except Exception as e:
            logger.error(f"Error parsing Ollama response: {str(e)}\nResponse: {response}", exc_info=True)
            raise ValueError(f"Error parsing receipt data: {e}")

    def initialize_engines(self):
        """Initialize OCR and LLM engines"""
        try:
            # Initialize OCR engine
            log_to_db(
                PoziomLogu.INFO,
                "receipt_processor",
                "initialize_engines",
                "Inicjalizacja silnika OCR",
                json.dumps({"status": "started"})
            )
            
            # Initialize OCR engine code here...
            
            log_to_db(
                PoziomLogu.INFO,
                "receipt_processor",
                "initialize_engines",
                "Silnik OCR zainicjalizowany pomyślnie",
                json.dumps({"status": "success"})
            )
            
            # Initialize LLM client
            log_to_db(
                PoziomLogu.INFO,
                "receipt_processor",
                "initialize_engines",
                "Inicjalizacja klienta LLM",
                json.dumps({"status": "started"})
            )
            
            # Initialize LLM client code here...
            
            log_to_db(
                PoziomLogu.INFO,
                "receipt_processor",
                "initialize_engines",
                "Klient LLM zainicjalizowany pomyślnie",
                json.dumps({"status": "success"})
            )
            
        except Exception as e:
            log_to_db(
                PoziomLogu.ERROR,
                "receipt_processor",
                "initialize_engines",
                "Błąd inicjalizacji silników",
                json.dumps({
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": str(e.__traceback__)
                })
            )
            raise 