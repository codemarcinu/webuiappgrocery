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
from models import StatusParagonu
from ollama_client import OllamaError, OllamaTimeoutError, OllamaConnectionError
from pydantic import BaseModel, Field, ValidationError, ConfigDict
from datetime import date
import uuid
import pdf2image
import tempfile

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

class ReceiptProcessor:
    def __init__(self):
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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def process_receipt(self, image_path: Path) -> Dict[str, Any]:
        """Process receipt using Ollama API"""
        try:
            # Read image file
            with open(image_path, "rb") as f:
                image_data = f.read()

            # Prepare request to Ollama
            headers = {"Content-Type": "application/json"}
            data = {
                "model": settings.OLLAMA_MODEL,
                "prompt": self._get_receipt_prompt(),
                "images": [image_data.hex()]
            }

            # Send request to Ollama
            response = requests.post(
                f"{settings.OLLAMA_API_URL}/api/generate",
                json=data,
                headers=headers,
                timeout=settings.OLLAMA_TIMEOUT
            )
            response.raise_for_status()

            # Parse response
            result = response.json()
            if not result.get("response"):
                raise ValueError("Empty response from Ollama")

            return self._parse_ollama_response(result["response"])

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

    def _get_receipt_prompt(self) -> str:
        """Get the prompt for receipt processing"""
        return """
        Analyze this receipt image and extract the following information in JSON format. The response must strictly follow this structure:
        {
            "store_name": "Name of the store (required, non-empty string)",
            "date": "Date of purchase in YYYY-MM-DD format (required)",
            "total_amount": "Total amount paid (required, positive number)",
            "items": [
                {
                    "name": "Product name (required, non-empty string)",
                    "quantity": "Quantity (required, positive number)",
                    "price": "Price per unit (required, positive number)",
                    "total": "Total price for this item (required, positive number)"
                }
            ],
            "tax_id": "Store's tax ID if visible (optional)",
            "payment_method": "Payment method used (optional)"
        }

        Important validation rules:
        1. All numeric values (total_amount, quantity, price, total) must be positive numbers
        2. The date must be in YYYY-MM-DD format
        3. The items array must contain at least one item
        4. All required fields must be present and non-empty
        5. Optional fields (tax_id, payment_method) can be omitted if not found
        """

    def _parse_ollama_response(self, response: str) -> Dict[str, Any]:
        """Parse Ollama's response into structured data using Pydantic models"""
        try:
            # Basic JSON parsing
            import json
            data = json.loads(response)
            
            # Validate and convert data using Pydantic model
            validated_receipt = Receipt.model_validate(data)
            
            # Convert to dict for return
            return validated_receipt.model_dump()
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Ollama: {str(e)}", exc_info=True)
            raise ValueError("Invalid JSON response from Ollama")
        except ValidationError as e:
            logger.error(f"Validation error in Ollama response: {str(e)}", exc_info=True)
            raise ValueError(f"Invalid receipt data structure: {str(e)}")
        except Exception as e:
            logger.error(f"Error parsing Ollama response: {str(e)}", exc_info=True)
            raise ValueError("Error parsing receipt data") 