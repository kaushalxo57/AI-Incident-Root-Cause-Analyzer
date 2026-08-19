from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
    # Standard connection pooling
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)

# Create session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for SQLAlchemy models
Base = declarative_base()


# DB Session dependency to inject in routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
