from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError
from .models import Base
import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL environment variable is not set. "
        "Please set it in your .env file or environment."
    )

# Create SQLAlchemy engine with connection pool settings for cloud databases
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True to see SQL queries in logs (useful for debugging)
    future=True,
    pool_pre_ping=True,  # Test connections before using them
    pool_recycle=3600,   # Recycle connections after 1 hour
    pool_size=10,        # Connection pool size
    max_overflow=20,     # Max overflow connections
    connect_args={
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    Dependency function for FastAPI or other frameworks.
    Yields a database session and ensures it's closed after use.

    Usage in FastAPI:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db)):
            return db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except OperationalError as e:
            # Handle SSL connection closed errors during cleanup
            # This can happen after long-running operations when the connection times out
            if "SSL connection has been closed unexpectedly" in str(e):
                logger.warning("Database connection already closed during cleanup (SSL timeout). This is expected after long operations.")
            else:
                # Re-raise other operational errors
                raise


def init_db():
    """
    Initialize the database by creating all tables.
    Call this function once when setting up your application.

    Usage:
        from portable_db_module import init_db
        init_db()
    """
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")


def drop_all_tables():
    """
    WARNING: This will delete all tables and data!
    Only use this in development/testing environments.
    """
    Base.metadata.drop_all(bind=engine)
    print("All tables dropped!")
