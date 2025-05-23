from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pathlib import Path

from database import create_db_and_tables
from routes import paragony
from logging_config import logger

# Create FastAPI app
app = FastAPI(
    title="Webowy Asystent Spiżarni",
    description="Aplikacja do zarządzania produktami w spiżarni",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configure templates
templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(paragony.router)

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    try:
        # Create database tables
        create_db_and_tables()
        logger.info("Application started successfully")
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}", exc_info=True)
        raise

@app.get("/")
async def root(request: Request):
    """Root endpoint - redirects to receipts list"""
    return templates.TemplateResponse(
        "paragony/lista.html",
        {"request": request}
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # Enable auto-reload during development
    ) 