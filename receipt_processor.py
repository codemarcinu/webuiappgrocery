from pathlib import Path
from typing import Optional, Dict, Any, List
from PIL import Image, ImageFile, UnidentifiedImageError
import io
import magic
from fastapi import UploadFile, HTTPException
from tenacity import retry, stop_after_attempt, wait_exponential
import requests
from logging_config import logger
from config import get_settings
from models import StatusParagonu, LogBledow, PoziomLogu
from ollama_client import OllamaError, OllamaTimeoutError, OllamaConnectionError, ollama_generate
from pydantic import BaseModel, Field, ValidationError, ConfigDict
from datetime import date
import uuid
import pdf2image
import tempfile
import easyocr
import json
import multiprocessing
import os
from db_logger import log_to_db
from database import SessionLocal

# Set environment variables for CUDA
os.environ['CUDA_VISIBLE_DEVICES'] = ''  # Disable CUDA
os.environ['TORCH_MULTIPROCESSING_START_METHOD'] = 'spawn'

# Set multiprocessing start method to 'spawn' for CUDA compatibility
if __name__ == '__main__':
    multiprocessing.set_start_method('spawn', force=True)

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
        self.allowed_mime_types = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'application/pdf': '.pdf'  # Add PDF support
        }
        self.max_file_size = settings.MAX_CONTENT_LENGTH
        self._ocr_reader = None
        self.initialize_engines()

    @property
    def ocr_reader(self):
        if self._ocr_reader is None:
            logger.info("Initializing EasyOCR reader...")
            # Force CPU usage for EasyOCR
            self._ocr_reader = easyocr.Reader(['pl'], gpu=False, download_enabled=True)
            logger.info("EasyOCR reader initialized successfully")
        return self._ocr_reader

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
        """
        Extract text from image using EasyOCR
        """
        try:
            logger.info(f"Starting OCR for image: {image_path}")
            result = self.ocr_reader.readtext(str(image_path), detail=0, paragraph=True)
            extracted_text = "\n".join(result)
            logger.info(f"OCR completed successfully for {image_path}")
            logger.debug(f"Extracted text:\n{extracted_text}")
            return extracted_text
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
                    "status": "started"
                })
            )
            
            prompt = self._get_receipt_prompt_for_text_input(extracted_text)
            
            llm_response = await ollama_generate(
                prompt=prompt,
                system="Jesteś pomocnym asystentem specjalizującym się w analizie tekstu z paragonów sklepowych i strukturyzowaniu go w formacie JSON."
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
Przeanalizuj poniższy tekst z paragonu sklepowego i wyekstrahuj informacje w formacie JSON. Odpowiedź musi ściśle przestrzegać tej struktury:
{{
    "store_name": "Nazwa sklepu (wymagane, niepusty ciąg znaków)",
    "date": "Data zakupu w formacie YYYY-MM-DD (wymagane)",
    "total_amount": "Całkowita zapłacona kwota (wymagane, liczba dodatnia)",
    "items": [
        {{
            "name": "Nazwa produktu (wymagane, niepusty ciąg znaków)",
            "quantity": "Ilość (wymagane, liczba dodatnia, domyślnie 1 jeśli nie określono inaczej)",
            "price": "Cena za jednostkę (wymagane, liczba dodatnia)",
            "total": "Całkowita cena za ten produkt (wymagane, liczba dodatnia)",
            "category": "Sugerowana kategoria (opcjonalnie, np. Spożywcze, Chemia)"
        }}
    ],
    "tax_id": "NIP sklepu jeśli widoczny (opcjonalnie)",
    "payment_method": "Użyta metoda płatności (opcjonalnie)"
}}

Ważne zasady walidacji:
1. Wszystkie wartości numeryczne (total_amount, quantity, price, total) muszą być liczbami dodatnimi.
2. Data musi być w formacie YYYY-MM-DD.
3. Tablica 'items' musi zawierać przynajmniej jeden produkt.
4. Wszystkie wymagane pola muszą być obecne i niepuste.
5. Pola opcjonalne (tax_id, payment_method, category) mogą zostać pominięte, jeśli nie znaleziono.
6. Jeśli ilość (quantity) nie jest jawnie podana dla produktu, przyjmij wartość 1.

Oto tekst z paragonu do analizy:
--- POCZĄTEK TEKSTU Z PARAGONU ---
{receipt_text}
--- KONIEC TEKSTU Z PARAGONU ---

Zwróć tylko i wyłącznie kompletny obiekt JSON, bez żadnych dodatkowych komentarzy przed lub po nim.
"""

    def _parse_ollama_response(self, response: str) -> Dict[str, Any]:
        """Parse Ollama's response into structured data"""
        try:
            # Remove markdown code block if present
            if response.strip().startswith("```json"):
                response = response.strip()[7:-3].strip()
            elif response.strip().startswith("```"):
                response = response.strip()[3:-3].strip()

            # Parse JSON
            data = json.loads(response)
            
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