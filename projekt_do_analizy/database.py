from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from logging_config import logger
import os

# Get database URL from environment variable or use default SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./spizarnia.db")

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

# Create all tables
def create_db_and_tables():
    try:
        SQLModel.metadata.create_all(engine)
        logger.info("Database tables created successfully")
    except SQLAlchemyError as e:
        logger.error(f"Error creating database tables: {str(e)}", exc_info=True)
        raise

# Dependency to get database session
def get_session():
    with Session(engine) as session:
        try:
            yield session
        except SQLAlchemyError as e:
            logger.error(f"Database session error: {str(e)}", exc_info=True)
            raise

def SessionLocal():
    return Session(engine) 