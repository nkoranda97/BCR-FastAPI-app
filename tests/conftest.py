import os
import sys
from pathlib import Path

# Add the project root directory to Python path
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, Base, engine
from sqlalchemy.orm import Session
import pandas as pd
import numpy as np
import tempfile
import json

@pytest.fixture(scope="session")
def test_client():
    return TestClient(app)

@pytest.fixture(scope="session")
def test_db():
    # Create test database tables
    Base.metadata.create_all(bind=engine)
    
    # Create a test session
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()
        # Clean up test database
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="session")
def test_project(test_db):
    """Create a test project with sample data."""
    # Create test data
    test_data = {
        "sequence_id": ["seq1", "seq2", "seq3"],
        "v_call_VDJ": ["IGHV1-2*01", "IGHV1-2*01", "IGHV1-2*01"],
        "v_call_VJ": ["IGKV1-5*01", "IGKV1-5*01", "IGKV1-5*01"],
        "locus_VDJ": ["IGH", "IGH", "IGH"],
        "IGH": ["MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT", "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT", "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT"],
        "IGK": ["DIVMTQSPDSLAVSLGERATINC", "DIVMTQSPDSLAVSLGERATINC", "DIVMTQSPDSLAVSLGERATINC"],
        "isotype": ["IgG", "IgG", "IgG"],
        "clone_id": ["clone1", "clone1", "clone1"]
    }
    
    # Create project directory structure
    project_name = "test_project"
    project_dir = os.path.join("instance", "uploads", project_name, project_name, "alignments")
    os.makedirs(project_dir, exist_ok=True)
    
    # Create alignment cache file
    cache_file = os.path.join(project_dir, "alignment_IGHV1-2_01_IGKV1-5_01.json")
    
    # Create alignment data
    alignment_data = {
        "hc_table": [
            {"sequence_id": "seq1", "IGH": "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT", "isotype": "IgG", "clone_id": "clone1"},
            {"sequence_id": "seq2", "IGH": "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT", "isotype": "IgG", "clone_id": "clone1"},
            {"sequence_id": "seq3", "IGH": "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT", "isotype": "IgG", "clone_id": "clone1"}
        ],
        "lc_table": [
            {"sequence_id": "seq1", "IGK": "DIVMTQSPDSLAVSLGERATINC", "isotype": "IgG", "clone_id": "clone1"},
            {"sequence_id": "seq2", "IGK": "DIVMTQSPDSLAVSLGERATINC", "isotype": "IgG", "clone_id": "clone1"},
            {"sequence_id": "seq3", "IGK": "DIVMTQSPDSLAVSLGERATINC", "isotype": "IgG", "clone_id": "clone1"}
        ],
        "hc_alignment": [
            ["seq1", "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT"],
            ["seq2", "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT"],
            ["seq3", "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT"]
        ],
        "lc_alignment": [
            ["seq1", "DIVMTQSPDSLAVSLGERATINC"],
            ["seq2", "DIVMTQSPDSLAVSLGERATINC"],
            ["seq3", "DIVMTQSPDSLAVSLGERATINC"]
        ],
        "hc_label_map": {"seq1": "HC-1", "seq2": "HC-2", "seq3": "HC-3"},
        "lc_label_map": {"seq1": "LC-1", "seq2": "LC-2", "seq3": "LC-3"}
    }
    
    # Write alignment data to cache file
    with open(cache_file, 'w') as f:
        json.dump(alignment_data, f)
    
    # Create project dictionary
    project = {
        "project_name": project_name,
        "species": "human",
        "id": 1
    }
    
    return project

@pytest.fixture(scope="session")
def test_project_id(test_project):
    """Return the test project ID."""
    return test_project["id"] 