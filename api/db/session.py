from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from common.config import POSTGRES_DSN

engine = create_engine(POSTGRES_DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
