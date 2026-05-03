from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/llm_wiki.db")

os.makedirs(os.path.dirname(DATABASE_URL.replace("sqlite:///", "")), exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_size=10,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class PDFFile(Base):
    __tablename__ = "pdf_files"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True)
    path = Column(String)
    size = Column(Integer)
    status = Column(String, default="pending")
    markdown_path = Column(String, nullable=True)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    converted_at = Column(DateTime, nullable=True)
    error_message = Column(String, nullable=True)


class MarkdownFile(Base):
    __tablename__ = "markdown_files"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True)
    path = Column(String)
    status = Column(String, default="pending")
    wiki_path = Column(String, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    error_message = Column(String, nullable=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
