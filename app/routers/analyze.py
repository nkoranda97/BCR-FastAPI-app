from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi import Response as FastAPIResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, Dict
import re
import pandas as pd
import os
import json
from Bio import Phylo
from Bio.Phylo.TreeConstruction import DistanceTreeConstructor, DistanceMatrix
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio.Align import MultipleSeqAlignment
from Bio.Phylo.Newick import Tree as NewickTree

from ..database import get_db, Project

from ..services.ddl import (
    load_project,
    merge_data,
    lazy_classifier,
    compute_alignment_and_consensus,
    best_translation,
)
from ..dependencies import (
    get_project,
    get_project_data,
    get_template_context,
    get_project_or_404,
)
from ..schemas.forms import GeneSelect
from app.services.germline_annotation import get_germline_and_annotation

router = APIRouter(prefix="/analyze", tags=["analyze"])

templates = Jinja2Templates(directory="app/templates")

# Track alignment computation status
alignment_status: Dict[str, Dict] = {}


def get_alignment_key(project_name: str, hc_gene: str, lc_gene: str) -> str:
    """Generate a unique key for alignment status tracking."""
    return f"{project_name}_{hc_gene}_{lc_gene}"


def safe_gene(g: str) -> str:
    """Convert gene name to safe filename."""
    return g.replace("/", "_").replace("*", "_").replace("|", "_").replace(" ", "_")


@router.get(
    "/alignment_status/{project_id}/{hc_gene}/{lc_gene}",
    response_class=JSONResponse,
    name="analyze.alignment_status",
)
async def get_alignment_status(
    project_id: int,
    hc_gene: str,
    lc_gene: str,
    project: Project = Depends(get_project),
):
    """Get the status of alignment computation."""
    key = get_alignment_key(project.project_name, hc_gene, lc_gene)
    status = alignment_status.get(key, {"status": "not_started"})
    return JSONResponse(content=status)


@router.get("/graphs/{project_id}", response_class=HTMLResponse, name="analyze.graphs")
async def graphs(
    request: Request,
    project_id: int,
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    """Generate graphs for a project."""
    vdj, adata = project_data
    df = vdj.metadata

    # Prepare data for Chart.js
    def prepare_chart_data(column):
        counts = df[column].value_counts()
        return {"labels": counts.index.tolist(), "values": counts.values.tolist()}

    chart_data = {
        # Heavy chain data
        "v_call": prepare_chart_data("v_call_VDJ"),
        "c_call": prepare_chart_data("c_call_VDJ"),
        "j_call": prepare_chart_data("j_call_VDJ"),
        "isotype": prepare_chart_data("isotype"),
        # Light chain data
        "lc_v_call": prepare_chart_data("v_call_VJ"),
        "lc_c_call": prepare_chart_data("c_call_VJ"),
        "lc_j_call": prepare_chart_data("j_call_VJ"),
    }
    print(f"Debug chart_data: {chart_data}")
    return templates.TemplateResponse(
        "analyze/graphs.html",
        get_template_context(
            request=request,
            project=project,
            project_id=project_id,
            chart_data=chart_data,
            active_tab="graphs",
        ),
    )


@router.get(
    "/lc_aggregation/{project_id}/{hc_gene}",
    response_class=JSONResponse,
    name="analyze.lc_aggregation",
)
async def lc_aggregation(
    project_id: int,
    hc_gene: str,
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    """Return LC gene aggregation for a selected HC gene."""
    vdj, adata = project_data
    df = vdj.metadata
    # Filter for the selected HC gene (v_call_VDJ)
    filtered = df[df["v_call_VDJ"] == hc_gene]
    # Count LC genes (v_call_VJ)
    lc_counts = filtered["v_call_VJ"].value_counts().reset_index()
    lc_counts.columns = ["gene", "count"]
    result = lc_counts.to_dict(orient="records")
    return JSONResponse(content={"lc_genes": result})


def alignment_to_fasta(seqs, label_map):
    # seqs: list of (orig_id, sequence) tuples; label_map: dict orig_id -> user label
    return "\n".join([f">{label_map[orig_id]}\n{seq}" for orig_id, seq in seqs])


@router.get(
    "/hc_lc_alignment_data/{project_id}/{hc_gene}/{lc_gene}",
    response_class=JSONResponse,
    name="analyze.hc_lc_alignment_data",
)
async def hc_lc_alignment_data(
    project_id: int,
    hc_gene: str,
    lc_gene: str,
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    """Generate and cache alignment data."""
    key = get_alignment_key(project.project_name, hc_gene, lc_gene)
    alignment_status[key] = {"status": "computing"}

    try:
        # --- File-based cache setup ---
        project_name = project.project_name
        align_dir = os.path.join(
            "instance", "uploads", project_name, project_name, "alignments"
        )
        os.makedirs(align_dir, exist_ok=True)
        cache_file = os.path.join(
            align_dir, f"alignment_{safe_gene(hc_gene)}_{safe_gene(lc_gene)}.json"
        )

        # Try to load from cache
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                result = json.load(f)
                alignment_status[key] = {"status": "ready"}
                return JSONResponse(content=result)

        # Otherwise, compute and cache
        vdj, _ = project_data
        merged = merge_data(vdj)
        filtered = merged[
            (merged["v_call_VDJ"] == hc_gene) & (merged["v_call_VJ"] == lc_gene)
        ].copy()

        for col in ("IGH", "IGK", "IGL"):
            filtered[col] = filtered[col].apply(best_translation)

        hc_table = (
            filtered[filtered["locus_VDJ"] == "IGH"][
                ["IGH", "sequence_id", "isotype", "clone_id"]
            ]
            .drop_duplicates()
            .to_dict(orient="records")
        )

        if lc_gene.startswith("IGK"):
            lc_col = "IGK"
        elif lc_gene.startswith("IGL"):
            lc_col = "IGL"
        else:
            lc_col = None

        lc_table = (
            filtered[[lc_col, "sequence_id", "isotype", "clone_id"]]
            .drop_duplicates()
            .to_dict(orient="records")
            if lc_col
            else []
        )

        hc_ids = [
            row["sequence_id"]
            for row in hc_table
            if row["IGH"] and isinstance(row["IGH"], str) and row["IGH"].strip()
        ]
        hc_seqs = [
            row["IGH"]
            for row in hc_table
            if row["IGH"] and isinstance(row["IGH"], str) and row["IGH"].strip()
        ]
        lc_ids = [
            row["sequence_id"]
            for row in lc_table
            if lc_col
            and row.get(lc_col)
            and isinstance(row[lc_col], str)
            and row[lc_col].strip()
        ]
        lc_seqs = [
            row[lc_col]
            for row in lc_table
            if lc_col
            and row.get(lc_col)
            and isinstance(row[lc_col], str)
            and row[lc_col].strip()
        ]

        hc_label_map = {orig_id: f"HC-{i + 1}" for i, orig_id in enumerate(hc_ids)}
        lc_label_map = {orig_id: f"LC-{i + 1}" for i, orig_id in enumerate(lc_ids)}

        hc_alignment, hc_consensus, hc_match_matrix = compute_alignment_and_consensus(
            hc_seqs, hc_ids
        )
        lc_alignment, lc_consensus, lc_match_matrix = compute_alignment_and_consensus(
            lc_seqs, lc_ids
        )

        species = project.species
        germ_anno = get_germline_and_annotation(hc_gene, species, "hc")
        hc_json = []
        hc_region_blocks = None
        if germ_anno:
            germ_seq, region_arr, region_blocks = germ_anno
            hc_region_blocks = region_blocks
            if region_arr:
                region_str = "".join(region_arr)
                hc_json.append({"name": "Region", "seq": region_str})
            hc_json.append({"name": "Germline", "seq": germ_seq})

        hc_json.extend(
            [
                {"name": hc_label_map[orig_id], "seq": seq}
                for orig_id, seq in hc_alignment
            ]
        )
        if hc_consensus:
            hc_json.append({"name": "Consensus", "seq": hc_consensus})

        lc_region_blocks = None
        germ_anno_lc = get_germline_and_annotation(lc_gene, species, "lc")
        lc_json = []
        if germ_anno_lc:
            lc_seq, lc_region_arr, lc_blocks = germ_anno_lc
            lc_region_blocks = lc_blocks
            if lc_region_arr:
                region_str = "".join(lc_region_arr)
                lc_json.append({"name": "Region", "seq": region_str})
            lc_json.append({"name": "Germline", "seq": lc_seq})

        lc_json.extend(
            [
                {"name": lc_label_map[orig_id], "seq": seq}
                for orig_id, seq in lc_alignment
            ]
        )
        if lc_consensus:
            lc_json.append({"name": "Consensus", "seq": lc_consensus})

        result = {
            "hc_table": hc_table,
            "lc_table": lc_table,
            "hc_alignment": hc_alignment,
            "hc_consensus": hc_consensus,
            "hc_match_matrix": hc_match_matrix,
            "lc_alignment": lc_alignment,
            "lc_consensus": lc_consensus,
            "lc_match_matrix": lc_match_matrix,
            "hc_json": hc_json,
            "lc_json": lc_json,
            "hc_label_map": hc_label_map,
            "lc_label_map": lc_label_map,
            "hc_region_blocks": hc_region_blocks,
            "lc_region_blocks": lc_region_blocks,
        }

        with open(cache_file, "w") as f:
            json.dump(result, f)

        alignment_status[key] = {"status": "ready"}
        return JSONResponse(content=result)

    except Exception as e:
        alignment_status[key] = {"status": "error", "message": str(e)}
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/hc_lc_detail/{project_id}/{hc_gene}/{lc_gene}",
    response_class=HTMLResponse,
    name="analyze.hc_lc_detail",
)
async def hc_lc_detail(
    request: Request,
    project_id: int,
    hc_gene: str,
    lc_gene: str,
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    return templates.TemplateResponse(
        "analyze/hc_lc_detail.html",
        get_template_context(
            request=request,
            project=project,
            project_id=project_id,
            hc_gene=hc_gene,
            lc_gene=lc_gene,
            active_tab="hc_lc_detail",
        ),
    )


@router.get(
    "/gene_explorer/{project_id}",
    response_class=HTMLResponse,
    name="analyze.gene_explorer",
)
async def gene_explorer(
    request: Request,
    project_id: int,
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    """Gene Explorer: List V genes and their counts."""
    vdj, adata = project_data
    df = vdj.metadata
    v_counts = df["v_call_VDJ"].value_counts().reset_index()
    v_counts.columns = ["gene", "count"]
    v_genes = v_counts.to_dict(orient="records")
    return templates.TemplateResponse(
        "analyze/gene_explorer.html",
        get_template_context(
            request=request,
            project=project,
            project_id=project_id,
            v_genes=v_genes,
            active_tab="gene_explorer",
        ),
    )


async def get_hc_sequences(project_data: tuple, hc_gene: str):
    """Get heavy chain sequences for a project and gene."""
    vdj, _ = project_data
    merged = merge_data(vdj)

    # Filter for the HC gene and translate
    filtered = merged[
        (merged["v_call_VDJ"] == hc_gene) & (merged["locus_VDJ"] == "IGH")
    ].copy()

    filtered["IGH"] = filtered["IGH"].apply(best_translation)

    # Convert to list of dicts
    sequences = []
    for _, row in filtered.drop_duplicates(subset=["sequence_id"]).iterrows():
        if row["IGH"] and isinstance(row["IGH"], str) and row["IGH"].strip():
            sequences.append({"name": f"HC-{len(sequences) + 1}", "seq": row["IGH"]})

    return sequences


async def get_lc_sequences(project_data: tuple, lc_gene: str):
    """Get light chain sequences for a project and gene."""
    vdj, _ = project_data
    merged = merge_data(vdj)

    # Determine LC column based on gene prefix
    lc_col = "IGK" if lc_gene.startswith("IGK") else "IGL"

    # Filter for the LC gene and translate
    filtered = merged[(merged["v_call_VJ"] == lc_gene)].copy()

    filtered[lc_col] = filtered[lc_col].apply(best_translation)

    # Convert to list of dicts
    sequences = []
    for _, row in filtered.drop_duplicates(subset=["sequence_id"]).iterrows():
        if row[lc_col] and isinstance(row[lc_col], str) and row[lc_col].strip():
            sequences.append({"name": f"LC-{len(sequences) + 1}", "seq": row[lc_col]})

    return sequences


@router.get(
    "/phylo_tree_newick/{project_id}/{hc_gene}/{lc_gene}",
    response_class=FastAPIResponse,
    name="analyze.phylo_tree_newick",
)
async def phylo_tree_newick(
    project_id: int,
    hc_gene: str,
    lc_gene: str,
    chain: str = "hc",  # Query parameter: chain=hc or chain=lc
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    """
    Generate and return a Newick tree for the selected HC/LC gene pair using aligned sequences
    from the alignment cache. The cache stores alignments as lists of dictionaries, e.g.,
    `hc_alignment: [{"name": "Seq1", "seq": "ACGT..."}, ...]`. This function processes this structure.
    """
    key = get_alignment_key(project.project_name, hc_gene, lc_gene)
    status = alignment_status.get(key, {"status": "not_started"})

    if status["status"] == "not_started":
        # Start alignment computation and wait for it to complete
        try:
            await hc_lc_alignment_data(
                project_id, hc_gene, lc_gene, project, project_data
            )
            status = alignment_status.get(key, {"status": "not_started"})
        except Exception as e:
            print(f"Error computing alignment: {e}")
            return FastAPIResponse(content="(A,B);", media_type="text/plain")

    if status["status"] == "computing":
        return FastAPIResponse(content="(A,B);", media_type="text/plain")
    elif status["status"] == "error":
        return FastAPIResponse(content="(A,B);", media_type="text/plain")

    # Alignment is ready, proceed with tree generation
    project_name = project.project_name
    cache_dir = os.path.join(
        "instance", "uploads", project_name, project_name, "alignments"
    )
    cache_file_path = os.path.join(
        cache_dir, f"alignment_{safe_gene(hc_gene)}_{safe_gene(lc_gene)}.json"
    )

    try:
        with open(cache_file_path, "r") as f:
            cache_data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return FastAPIResponse(content="(A,B);", media_type="text/plain")

    source_alignment_list_of_dicts = []
    if chain == "lc":
        source_alignment_list_of_dicts = cache_data.get("lc_alignment", [])
    else:  # Default to hc
        source_alignment_list_of_dicts = cache_data.get("hc_alignment", [])

    if not isinstance(source_alignment_list_of_dicts, list):
        print(
            f"DEBUG: Expected list for '{chain}_alignment', got {type(source_alignment_list_of_dicts)}"
        )
        return FastAPIResponse(content="(A,B);", media_type="text/plain")

    # Step 1: Extract valid (original_name, sequence_string) tuples from the list of dicts.
    # Filter out entries like "Germline", "Consensus", "Region" by their 'name' field.
    # Ensure 'seq' is a non-empty string.
    valid_initial_sequences = []  # List of (original_name, sequence_string)
    for item_list in source_alignment_list_of_dicts:
        # Ensure item_list is a list and has exactly two elements (name, sequence)
        if not (isinstance(item_list, list) and len(item_list) == 2):
            # print(f"DEBUG: Skipping item, not a list of 2 elements: {item_list}") # Optional: for very detailed debugging
            continue

        name, sequence = item_list[0], item_list[1]  # Unpack name and sequence

        # Filter by name and ensure sequence is a non-empty string
        if (
            isinstance(name, str)
            and name not in ("Germline", "Consensus", "Region")
            and isinstance(sequence, str)
            and sequence
        ):
            valid_initial_sequences.append((name, sequence))
        # else: # Optional: for very detailed debugging
        # print(f"DEBUG: Skipping item due to name/sequence content: Name='{name}', Seq='{sequence[:10]}...' ({type(name)}, {type(sequence)})")

    # Step 2: Create new labels (e.g., "HC-1", "LC-1") for the valid sequences.
    labelled_sequences_for_tree = []  # List of (new_label, sequence_string)
    label_prefix = "LC" if chain == "lc" else "HC"
    for i, (original_name, seq_str) in enumerate(valid_initial_sequences):
        labelled_sequences_for_tree.append((f"{label_prefix}-{i + 1}", seq_str))

    # Step 3: Filter for unique sequences (based on sequence string), keeping the generated label.
    seen_sequence_strings = set()
    final_sequences_for_matrix = []  # List of (label, sequence_string)
    for label, sequence_string in labelled_sequences_for_tree:
        if sequence_string in seen_sequence_strings:
            continue  # Skip duplicate sequence string
        seen_sequence_strings.add(sequence_string)
        final_sequences_for_matrix.append((label, sequence_string))

    if len(final_sequences_for_matrix) < 2:
        print(f"DEBUG: Detailed trace for chain '{chain}':")
        print(
            f"DEBUG:   Source alignment data (from cache): {source_alignment_list_of_dicts}"
        )
        print(
            f"DEBUG:   Valid initial sequences (after name/empty filter): {valid_initial_sequences}"
        )
        print(
            f"DEBUG:   Labelled sequences for tree (with HC/LC prefix): {labelled_sequences_for_tree}"
        )
        print(
            f"DEBUG:   Final sequences for matrix (after unique string filter): {final_sequences_for_matrix}"
        )
        print(
            f"DEBUG: Not enough unique, valid sequences after filtering for chain '{chain}'. Count: {len(final_sequences_for_matrix)}"
        )
        return FastAPIResponse(content="(A,B);", media_type="text/plain")

    # Step 4: Ensure all sequences for the matrix are the same length and not zero-length.
    sequence_lengths = set(
        len(seq_str) for label, seq_str in final_sequences_for_matrix
    )
    if len(sequence_lengths) != 1:
        print(
            f"DEBUG: Sequence lengths not uniform for chain '{chain}': {sequence_lengths}. Sequences: {final_sequences_for_matrix}"
        )
        return FastAPIResponse(content="(A,B);", media_type="text/plain")

    current_seq_length = list(sequence_lengths)[0]
    if current_seq_length == 0:
        print(f"DEBUG: All sequences have length 0 for chain '{chain}'.")
        return FastAPIResponse(content="(A,B);", media_type="text/plain")

    # Step 5: Prepare for DistanceMatrix: list of labels, and lower-triangular matrix of distances.
    matrix_labels = [label for label, seq_str in final_sequences_for_matrix]
    matrix_sequence_strings = [seq_str for label, seq_str in final_sequences_for_matrix]
    num_sequences = len(matrix_sequence_strings)

    distance_matrix_rows = []
    for i in range(num_sequences):
        current_row = []  # Row i for the lower-triangular matrix
        for j in range(i):  # Columns 0 to i-1
            seq1_str = matrix_sequence_strings[i]
            seq2_str = matrix_sequence_strings[j]

            # Normalized Hamming distance: 1 - (matches / length)
            matches = sum(aa1 == aa2 for aa1, aa2 in zip(seq1_str, seq2_str))
            dist = 1.0 - (
                matches / current_seq_length
            )  # current_seq_length is uniform and non-zero
            current_row.append(dist)
        distance_matrix_rows.append(current_row)

    # --- STRICT lower-triangular matrix for Biopython ---
    n_labels = len(matrix_labels)
    # Build lower-triangular distance matrix: for n labels, n rows, row i has i elements
    strict_matrix = []
    for i in range(n_labels):
        row = []
        for j in range(i):
            seq1 = matrix_sequence_strings[i]
            seq2 = matrix_sequence_strings[j]
            matches = sum(aa1 == aa2 for aa1, aa2 in zip(seq1, seq2))
            dist = 1.0 - (matches / current_seq_length)
            row.append(float(dist))
        strict_matrix.append(row)
    distance_matrix_rows = strict_matrix
    # Assert correct shape
    assert len(distance_matrix_rows) == n_labels, (
        f"Distance matrix rows {len(distance_matrix_rows)} != #labels {n_labels}"
    )
    for i, row in enumerate(distance_matrix_rows):
        assert len(row) == i, f"Row {i} length {len(row)} != {i}"
    # Ensure all labels are strings and all values are floats
    matrix_labels = [str(l) for l in matrix_labels]
    # --- SIMPLIFIED PHYLOGENY USING BIOPYTHON WIKI EXAMPLE ---
    from Bio.Seq import Seq
    from Bio.SeqRecord import SeqRecord
    from Bio.Align import MultipleSeqAlignment
    from Bio.Phylo.TreeConstruction import DistanceCalculator, DistanceTreeConstructor
    from io import StringIO
    from Bio import Phylo

    try:
        alignment = MultipleSeqAlignment(
            [SeqRecord(Seq(seq), id=label) for label, seq in final_sequences_for_matrix]
        )
        if len(alignment) < 2:
            print(f"Not enough sequences for tree. Returning dummy tree.")
            return FastAPIResponse(content="(A,B);", media_type="text/plain")
        calculator = DistanceCalculator("identity")
        dm = calculator.get_distance(alignment)
        constructor = DistanceTreeConstructor()
        tree = constructor.nj(dm)
        handle = StringIO()
        Phylo.write(tree, handle, "newick")
        newick_tree_string = handle.getvalue().strip()
        if not newick_tree_string or newick_tree_string == "();":
            print(
                f"DEBUG: Biopython produced trivial tree for chain '{chain}': '{newick_tree_string}'"
            )
            return FastAPIResponse(content="(A,B);", media_type="text/plain")
        return FastAPIResponse(content=newick_tree_string, media_type="text/plain")
    except Exception as e:
        print(f"ERROR constructing tree for chain '{chain}': {e}")
        return FastAPIResponse(content="(A,B);", media_type="text/plain")

    except ValueError as e:  # Catch errors from DistanceMatrix or tree construction (e.g., matrix format)
        # Log the error along with the data that was passed to DistanceMatrix
        # matrix_for_biopython should be defined here if the error is from DistanceMatrix itself.
        # If the error was before its assignment (unlikely for this specific error), it falls back to distance_matrix_rows.
        print(f"ERROR constructing DistanceMatrix/Tree for chain '{chain}': {e}.")
        print(
            f"ERROR constructing DistanceMatrix/Tree for chain '{chain}': {e}. Labels: {matrix_labels}, Matrix PASSED to Biopython: {matrix_logged}"
        )
        return FastAPIResponse(content="(A,B);", media_type="text/plain")
    except Exception as e:  # Catch any other unexpected errors during tree construction
        matrix_logged = (
            matrix_for_biopython
            if "matrix_for_biopython" in locals()
            else distance_matrix_rows
        )
        print(
            f"UNEXPECTED ERROR during tree construction for chain '{chain}': {e}. Labels: {matrix_labels}, Matrix: {matrix_logged}"
        )
        return FastAPIResponse(content="(A,B);", media_type="text/plain")


@router.get(
    "/download_fasta/{project_id}/{hc_gene}/{lc_gene}/{chain_type}",
    response_class=Response,
    name="analyze.download_fasta",
)
async def download_fasta(
    request: Request,
    project_id: str,
    hc_gene: str,
    lc_gene: str,
    chain_type: str,
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    """Download FASTA file for HC/LC gene pair."""
    # Get sequences
    if chain_type == "hc":
        sequences = await get_hc_sequences(project_data, hc_gene)
        filename = f"{project.project_name}_HC_{hc_gene}.fasta"
    else:
        sequences = await get_lc_sequences(project_data, lc_gene)
        filename = f"{project.project_name}_LC_{lc_gene}.fasta"

    # Compute consensus
    if sequences:
        consensus = compute_consensus(sequences)
        # Add consensus as first sequence
        sequences.insert(0, {"name": "Consensus", "seq": consensus})

    # Convert to FASTA format
    fasta_content = "\n".join(f">{seq['name']}\n{seq['seq']}" for seq in sequences)

    return Response(
        content=fasta_content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def compute_consensus(sequences):
    """Compute consensus sequence from a list of sequences."""
    if not sequences:
        return ""

    # Get max length
    max_len = max(len(seq["seq"]) for seq in sequences)

    # For each position, count amino acids
    consensus = []
    for i in range(max_len):
        counts = {}
        for seq in sequences:
            aa = seq["seq"][i] if i < len(seq["seq"]) else "-"
            counts[aa] = counts.get(aa, 0) + 1

        # Get most common amino acid
        best_aa = max(counts.items(), key=lambda x: x[1])[0]
        consensus.append(best_aa)

    return "".join(consensus)


@router.get(
    "/download_data/{project_id}",
    response_class=HTMLResponse,
    name="analyze.download_data",
)
async def download_data(
    request: Request,
    project_id: int,
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    """Download data page for a project."""
    vdj, _ = project_data
    merged = merge_data(vdj)
    columns = merged.columns.tolist()

    return templates.TemplateResponse(
        "analyze/download_data.html",
        get_template_context(
            request=request,
            project=project,
            project_id=project_id,
            columns=columns,
            active_tab="download_data",
        ),
    )


@router.post(
    "/download_csv/{project_id}", response_class=Response, name="analyze.download_csv"
)
async def download_csv(
    project_id: int,
    columns: str = Form(...),
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    """Download selected columns as CSV."""
    vdj, _ = project_data
    merged = merge_data(vdj)

    # Parse selected columns
    selected_columns = columns.split(",")

    # Filter data to selected columns
    filtered_data = merged[selected_columns]

    # Convert to CSV
    csv_data = filtered_data.to_csv(index=False)

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{project.project_name}_data.csv"'
        },
    )
