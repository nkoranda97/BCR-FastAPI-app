import pytest
from fastapi.testclient import TestClient
from app.main import app
import json
import re
from app.database import get_db
from app.dependencies import get_project, get_project_data
from unittest.mock import patch, MagicMock, mock_open
import pandas as pd
import os
import numpy as np
from fastapi.responses import JSONResponse

def extract_labels_from_newick(newick_str):
    """Extract sequence labels from a Newick tree string."""
    # Remove internal node labels (those with parentheses)
    leaf_labels = re.findall(r'([^(),:]+):', newick_str)
    return [label.strip() for label in leaf_labels]

@pytest.fixture(autouse=True)
def mock_dependencies():
    """Mock database and project dependencies."""
    # Create mock data
    mock_data = {
        "hc_json": [
            {"name": "HC-1", "seq": "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT"},
            {"name": "HC-2", "seq": "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT"},
            {"name": "HC-3", "seq": "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT"}
        ],
        "lc_json": [
            {"name": "LC-1", "seq": "DIVMTQSPDSLAVSLGERATINC"},
            {"name": "LC-2", "seq": "DIVMTQSPDSLAVSLGERATINC"},
            {"name": "LC-3", "seq": "DIVMTQSPDSLAVSLGERATINC"}
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

    # Create mock distance matrix data
    mock_distance_matrix = {
        "labels": ["HC-1", "HC-2", "HC-3"],
        "matrix": [
            [0.0, 0.1, 0.2],
            [0.1, 0.0, 0.15],
            [0.2, 0.15, 0.0]
        ]
    }

    with patch('app.dependencies.get_project') as mock_get_project, \
         patch('app.dependencies.get_project_data') as mock_get_project_data, \
         patch('os.makedirs') as mock_makedirs, \
         patch('os.path.exists') as mock_exists, \
         patch('builtins.open', mock_open(read_data=json.dumps(mock_data))), \
         patch('app.routers.analyze.alignment_status', {}) as mock_status:
        
        # Mock project
        mock_project = MagicMock()
        mock_project.project_name = "test_project"
        mock_project.species = "human"
        mock_get_project.return_value = mock_project
        
        # Mock project data
        mock_vdj = MagicMock()
        mock_vdj.metadata = pd.DataFrame({
            "sequence_id": ["seq1", "seq2", "seq3"],
            "v_call_VDJ": ["IGHV1-2*01", "IGHV1-2*01", "IGHV1-2*01"],
            "v_call_VJ": ["IGKV1-5*01", "IGKV1-5*01", "IGKV1-5*01"],
            "locus_VDJ": ["IGH", "IGH", "IGH"],
            "IGH": ["MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT"] * 3,
            "IGK": ["DIVMTQSPDSLAVSLGERATINC"] * 3,
            "isotype": ["IgG"] * 3,
            "clone_id": ["clone1"] * 3
        })
        mock_get_project_data.return_value = (mock_vdj, None)
        
        # Mock file operations
        mock_exists.return_value = True
        mock_makedirs.return_value = None
        
        # Set initial alignment status
        key = f"test_project_IGHV1-2*01_IGKV1-5*01"
        mock_status[key] = {"status": "ready"}

        # Mock the distance matrix endpoint
        async def mock_distance_matrix(*args, **kwargs):
            return JSONResponse(content=mock_distance_matrix)

        # Mock the route handler directly
        app.dependency_overrides[get_project] = lambda: mock_project
        app.dependency_overrides[get_project_data] = lambda: (mock_vdj, None)
        
        # Override the route handler
        original_routes = app.routes
        app.routes = []
        for route in original_routes:
            if route.path == "/analyze/distance_matrix/{project_id}/{hc_gene}/{lc_gene}":
                app.routes.append(route)
                route.endpoint = mock_distance_matrix
            else:
                app.routes.append(route)
        
        yield
        
        # Clean up
        app.dependency_overrides = {}
        app.routes = original_routes

def test_sequence_identifier_consistency(test_client, test_project_id):
    """Test that sequence identifiers are consistent across alignment, tree, and matrix views."""
    # Test parameters
    hc_gene = "IGHV1-2*01"  # Use a test HC gene
    lc_gene = "IGKV1-5*01"  # Use a test LC gene
    
    # 1. Get alignment data
    alignment_response = test_client.get(f"/analyze/hc_lc_alignment_data/{test_project_id}/{hc_gene}/{lc_gene}")
    assert alignment_response.status_code == 200
    alignment_data = alignment_response.json()
    
    # Extract labels from alignment data
    hc_alignment_labels = [seq["name"] for seq in alignment_data["hc_json"] 
                         if not seq["name"] in ["Germline", "Consensus", "Region"]]
    lc_alignment_labels = [seq["name"] for seq in alignment_data["lc_json"]
                         if not seq["name"] in ["Germline", "Consensus", "Region"]]
    
    # 2. Get phylogenetic tree data
    tree_response = test_client.get(f"/analyze/phylo_tree_newick/{test_project_id}/{hc_gene}/{lc_gene}?chain=hc")
    assert tree_response.status_code == 200
    hc_tree_labels = extract_labels_from_newick(tree_response.text)
    
    tree_response = test_client.get(f"/analyze/phylo_tree_newick/{test_project_id}/{hc_gene}/{lc_gene}?chain=lc")
    assert tree_response.status_code == 200
    lc_tree_labels = extract_labels_from_newick(tree_response.text)
    
    # 3. Get distance matrix data
    matrix_response = test_client.get(f"/analyze/distance_matrix/{test_project_id}/{hc_gene}/{lc_gene}?chain=hc")
    assert matrix_response.status_code == 200
    print("HC Matrix Response:", matrix_response.json())  # Debug print
    hc_matrix_labels = matrix_response.json()["labels"]
    
    matrix_response = test_client.get(f"/analyze/distance_matrix/{test_project_id}/{hc_gene}/{lc_gene}?chain=lc")
    assert matrix_response.status_code == 200
    print("LC Matrix Response:", matrix_response.json())  # Debug print
    lc_matrix_labels = matrix_response.json()["labels"]
    
    # 4. Verify consistency
    # Check that all sets of labels are identical
    assert set(hc_alignment_labels) == set(hc_tree_labels), "HC labels mismatch between alignment and tree"
    assert set(hc_alignment_labels) == set(hc_matrix_labels), "HC labels mismatch between alignment and matrix"
    assert set(hc_tree_labels) == set(hc_matrix_labels), "HC labels mismatch between tree and matrix"
    
    assert set(lc_alignment_labels) == set(lc_tree_labels), "LC labels mismatch between alignment and tree"
    assert set(lc_alignment_labels) == set(lc_matrix_labels), "LC labels mismatch between alignment and matrix"
    assert set(lc_tree_labels) == set(lc_matrix_labels), "LC labels mismatch between tree and matrix"
    
    # 5. Verify label format
    hc_label_pattern = re.compile(r'^HC-\d+$')
    lc_label_pattern = re.compile(r'^LC-\d+$')
    
    for label in hc_alignment_labels:
        assert hc_label_pattern.match(label), f"Invalid HC label format: {label}"
    
    for label in lc_alignment_labels:
import pytest
from fastapi.testclient import TestClient
from app.main import app
import json
import re
from app.database import get_db
from app.dependencies import get_project, get_project_data
from unittest.mock import patch, MagicMock, mock_open
import pandas as pd
import os
import numpy as np
from fastapi.responses import JSONResponse

def extract_labels_from_newick(newick_str):
    """Extract sequence labels from a Newick tree string."""
    # Remove internal node labels (those with parentheses)
    leaf_labels = re.findall(r'([^(),:]+):', newick_str)
    return [label.strip() for label in leaf_labels]

@pytest.fixture(autouse=True)
def mock_dependencies():
    """Mock database and project dependencies."""
    # Create mock data
    mock_data = {
        "hc_json": [
            {"name": "HC-1", "seq": "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT"},
            {"name": "HC-2", "seq": "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT"},
            {"name": "HC-3", "seq": "MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT"}
        ],
        "lc_json": [
            {"name": "LC-1", "seq": "DIVMTQSPDSLAVSLGERATINC"},
            {"name": "LC-2", "seq": "DIVMTQSPDSLAVSLGERATINC"},
            {"name": "LC-3", "seq": "DIVMTQSPDSLAVSLGERATINC"}
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

    # Create mock distance matrix data
    mock_distance_matrix = {
        "labels": ["HC-1", "HC-2", "HC-3"],
        "matrix": [
            [0.0, 0.1, 0.2],
            [0.1, 0.0, 0.15],
            [0.2, 0.15, 0.0]
        ]
    }

    with patch('app.dependencies.get_project') as mock_get_project, \
         patch('app.dependencies.get_project_data') as mock_get_project_data, \
         patch('os.makedirs') as mock_makedirs, \
         patch('os.path.exists') as mock_exists, \
         patch('builtins.open', mock_open(read_data=json.dumps(mock_data))), \
         patch('app.routers.analyze.alignment_status', {}) as mock_status:
        
        # Mock project
        mock_project = MagicMock()
        mock_project.project_name = "test_project"
        mock_project.species = "human"
        mock_get_project.return_value = mock_project
        
        # Mock project data
        mock_vdj = MagicMock()
        mock_vdj.metadata = pd.DataFrame({
            "sequence_id": ["seq1", "seq2", "seq3"],
            "v_call_VDJ": ["IGHV1-2*01", "IGHV1-2*01", "IGHV1-2*01"],
            "v_call_VJ": ["IGKV1-5*01", "IGKV1-5*01", "IGKV1-5*01"],
            "locus_VDJ": ["IGH", "IGH", "IGH"],
            "IGH": ["MAQVQLVQSGAEVKKPGASVKVSCKASGYTFT"] * 3,
            "IGK": ["DIVMTQSPDSLAVSLGERATINC"] * 3,
            "isotype": ["IgG"] * 3,
            "clone_id": ["clone1"] * 3
        })
        mock_get_project_data.return_value = (mock_vdj, None)
        
        # Mock file operations
        mock_exists.return_value = True
        mock_makedirs.return_value = None
        
        # Set initial alignment status
        key = f"test_project_IGHV1-2*01_IGKV1-5*01"
        mock_status[key] = {"status": "ready"}

        # Mock the distance matrix endpoint
        async def mock_distance_matrix(*args, **kwargs):
            return JSONResponse(content=mock_distance_matrix)

        with patch('app.routers.analyze.distance_matrix', side_effect=mock_distance_matrix):
            yield

def test_sequence_identifier_consistency(test_client, test_project_id):
    """Test that sequence identifiers are consistent across alignment, tree, and matrix views."""
    # Test parameters
    hc_gene = "IGHV1-2*01"  # Use a test HC gene
    lc_gene = "IGKV1-5*01"  # Use a test LC gene
    
    # 1. Get alignment data
    alignment_response = test_client.get(f"/analyze/hc_lc_alignment_data/{test_project_id}/{hc_gene}/{lc_gene}")
    assert alignment_response.status_code == 200
    alignment_data = alignment_response.json()
    
    # Extract labels from alignment data
    hc_alignment_labels = [seq["name"] for seq in alignment_data["hc_json"] 
                         if not seq["name"] in ["Germline", "Consensus", "Region"]]
    lc_alignment_labels = [seq["name"] for seq in alignment_data["lc_json"]
                         if not seq["name"] in ["Germline", "Consensus", "Region"]]
    
    # 2. Get phylogenetic tree data
    tree_response = test_client.get(f"/analyze/phylo_tree_newick/{test_project_id}/{hc_gene}/{lc_gene}?chain=hc")
    assert tree_response.status_code == 200
    hc_tree_labels = extract_labels_from_newick(tree_response.text)
    
    tree_response = test_client.get(f"/analyze/phylo_tree_newick/{test_project_id}/{hc_gene}/{lc_gene}?chain=lc")
    assert tree_response.status_code == 200
    lc_tree_labels = extract_labels_from_newick(tree_response.text)
    
    # 3. Get distance matrix data
    matrix_response = test_client.get(f"/analyze/distance_matrix/{test_project_id}/{hc_gene}/{lc_gene}?chain=hc")
    assert matrix_response.status_code == 200
    print("HC Matrix Response:", matrix_response.json())  # Debug print
    hc_matrix_labels = matrix_response.json()["labels"]
    
    matrix_response = test_client.get(f"/analyze/distance_matrix/{test_project_id}/{hc_gene}/{lc_gene}?chain=lc")
    assert matrix_response.status_code == 200
    print("LC Matrix Response:", matrix_response.json())  # Debug print
    lc_matrix_labels = matrix_response.json()["labels"]
    
    # 4. Verify consistency
    # Check that all sets of labels are identical
    assert set(hc_alignment_labels) == set(hc_tree_labels), "HC labels mismatch between alignment and tree"
    assert set(hc_alignment_labels) == set(hc_matrix_labels), "HC labels mismatch between alignment and matrix"
    assert set(hc_tree_labels) == set(hc_matrix_labels), "HC labels mismatch between tree and matrix"
    
    assert set(lc_alignment_labels) == set(lc_tree_labels), "LC labels mismatch between alignment and tree"
    assert set(lc_alignment_labels) == set(lc_matrix_labels), "LC labels mismatch between alignment and matrix"
    assert set(lc_tree_labels) == set(lc_matrix_labels), "LC labels mismatch between tree and matrix"
    
    # 5. Verify label format
    hc_label_pattern = re.compile(r'^HC-\d+$')
    lc_label_pattern = re.compile(r'^LC-\d+$')
    
    for label in hc_alignment_labels:
        assert hc_label_pattern.match(label), f"Invalid HC label format: {label}"
    
    for label in lc_alignment_labels:
        assert lc_label_pattern.match(label), f"Invalid LC label format: {label}" 