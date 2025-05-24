from sqlalchemy import create_engine, Column, Integer, String, Date, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import os
from pathlib import Path

# Create instance directory if it doesn't exist
instance_path = Path("instance")
instance_path.mkdir(exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{instance_path}/bcr.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Project model
class Project(Base):
    __tablename__ = "projects"

    project_id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String, unique=True, index=True)
    project_author = Column(String)
    creation_date = Column(Date)
    directory_path = Column(String)
    vdj_path = Column(String, nullable=True)
    adata_path = Column(String, nullable=True)
    species = Column(String)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
