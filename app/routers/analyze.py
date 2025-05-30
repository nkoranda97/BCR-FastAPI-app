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

from Bio import AlignIO
import numpy as np
from scipy.spatial.distance import pdist, squareform

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

import subprocess
from io import StringIO

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


async def get_hc_sequences(project_data: tuple, hc_gene: str, lc_gene: str):
    """Get heavy chain sequences for a project and gene pair."""
    vdj, _ = project_data
    merged = merge_data(vdj)

    # Filter for the HC/LC gene pair and translate
    filtered = merged[
        (merged["v_call_VDJ"] == hc_gene) & (merged["v_call_VJ"] == lc_gene)
    ].copy()

    filtered["IGH"] = filtered["IGH"].apply(best_translation)

    # Convert to list of dicts, using the same labeling scheme as alignment data
    sequences = []
    for i, (_, row) in enumerate(filtered.drop_duplicates(subset=["sequence_id"]).iterrows()):
        if row["IGH"] and isinstance(row["IGH"], str) and row["IGH"].strip():
            sequences.append({"name": f"HC-{i + 1}", "seq": row["IGH"]})

    return sequences


async def get_lc_sequences(project_data: tuple, hc_gene: str, lc_gene: str):
    """Get light chain sequences for a project and gene pair."""
    vdj, _ = project_data
    merged = merge_data(vdj)

    # Determine LC column based on gene prefix
    lc_col = "IGK" if lc_gene.startswith("IGK") else "IGL"

    # Filter for the HC/LC gene pair and translate
    filtered = merged[
        (merged["v_call_VDJ"] == hc_gene) & (merged["v_call_VJ"] == lc_gene)
    ].copy()

    filtered[lc_col] = filtered[lc_col].apply(best_translation)

    # Convert to list of dicts, using the same labeling scheme as alignment data
    sequences = []
    for i, (_, row) in enumerate(filtered.drop_duplicates(subset=["sequence_id"]).iterrows()):
        if row[lc_col] and isinstance(row[lc_col], str) and row[lc_col].strip():
            sequences.append({"name": f"LC-{i + 1}", "seq": row[lc_col]})

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
    """Generate and return a Newick tree for the selected HC/LC gene pair using aligned sequences."""
    key = get_alignment_key(project.project_name, hc_gene, lc_gene)
    status = alignment_status.get(key, {"status": "not_started"})

    if status["status"] == "not_started":
        try:
            await hc_lc_alignment_data(project_id, hc_gene, lc_gene, project, project_data)
            status = alignment_status.get(key, {"status": "not_started"})
        except Exception:
            return FastAPIResponse(content="(A,B);", media_type="text/plain")

    if status["status"] != "ready":
        return FastAPIResponse(content="(A,B);", media_type="text/plain")

    project_name = project.project_name
    cache_dir = os.path.join("instance", "uploads", project_name, project_name, "alignments")
    cache_file_path = os.path.join(cache_dir, f"alignment_{safe_gene(hc_gene)}_{safe_gene(lc_gene)}.json")

    try:
        with open(cache_file_path, "r") as f:
            cache_data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return FastAPIResponse(content="(A,B);", media_type="text/plain")

    source_alignment_list_of_dicts = []
    label_map = {}
    if chain == "lc":
        source_alignment_list_of_dicts = cache_data.get("lc_alignment", [])
        label_map = cache_data.get("lc_label_map", {})
    else:
        source_alignment_list_of_dicts = cache_data.get("hc_alignment", [])
        label_map = cache_data.get("hc_label_map", {})

    if not isinstance(source_alignment_list_of_dicts, list):
        return FastAPIResponse(content="(A,B);", media_type="text/plain")

    valid_initial_sequences = []
    for item_list in source_alignment_list_of_dicts:
        if not (isinstance(item_list, list) and len(item_list) == 2):
            continue

        name, sequence = item_list[0], item_list[1]

        if (isinstance(name, str) and name not in ("Germline", "Consensus", "Region") 
            and isinstance(sequence, str) and sequence):
            valid_initial_sequences.append((name, sequence))

    labelled_sequences_for_tree = []
    for original_name, seq_str in valid_initial_sequences:
        if original_name in label_map:
            labelled_sequences_for_tree.append((label_map[original_name], seq_str))

    if len(labelled_sequences_for_tree) < 2:
        return FastAPIResponse(content="(A,B);", media_type="text/plain")

    sequence_lengths = set(len(seq_str) for label, seq_str in labelled_sequences_for_tree)
    if len(sequence_lengths) != 1 or list(sequence_lengths)[0] == 0:
        return FastAPIResponse(content="(A,B);", media_type="text/plain")

    # --- SIMPLIFIED PHYLOGENY USING BIOPYTHON WIKI EXAMPLE ---
    from Bio.Seq import Seq
    from Bio.SeqRecord import SeqRecord
    from Bio.Align import MultipleSeqAlignment
    from Bio.Phylo.TreeConstruction import DistanceCalculator, DistanceTreeConstructor
    from io import StringIO
    from Bio import Phylo

    try:
        alignment = MultipleSeqAlignment(
            [SeqRecord(Seq(seq), id=label) for label, seq in labelled_sequences_for_tree]
        )
        if len(alignment) < 2:
            return FastAPIResponse(content="(A,B);", media_type="text/plain")

        temp_input = os.path.join("instance", "temp", f"temp_input_{chain}.fasta")
        temp_output = os.path.join("instance", "temp", f"temp_output_{chain}.fasta")
        os.makedirs(os.path.dirname(temp_input), exist_ok=True)
        
        with open(temp_input, "w") as f:
            for record in alignment:
                f.write(f">{record.id}\n{record.seq}\n")

        subprocess.run(["muscle", "-align", temp_input, "-output", temp_output], check=True)
        aligned = AlignIO.read(temp_output, "fasta")
        
        os.remove(temp_input)
        os.remove(temp_output)

        calculator = DistanceCalculator("blosum62")
        distance_matrix = calculator.get_distance(aligned)
        constructor = DistanceTreeConstructor(calculator, method="nj")
        tree = constructor.nj(distance_matrix)
        
        handle = StringIO()
        Phylo.write(tree, handle, "newick")
        newick_tree_string = handle.getvalue().strip()
        
        if not newick_tree_string or newick_tree_string == "();":
            return FastAPIResponse(content="(A,B);", media_type="text/plain")
        return FastAPIResponse(content=newick_tree_string, media_type="text/plain")
    except Exception:
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
        sequences = await get_hc_sequences(project_data, hc_gene, lc_gene)
        filename = f"{project.project_name}_HC_{hc_gene}.fasta"
    else:
        sequences = await get_lc_sequences(project_data, hc_gene, lc_gene)
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


@router.get(
    "/distance_matrix/{project_id}/{hc_gene}/{lc_gene}",
    response_class=JSONResponse,
    name="analyze.distance_matrix",
)
async def distance_matrix(
    project_id: int,
    hc_gene: str,
    lc_gene: str,
    chain: str = "hc",  # Query parameter: chain=hc or chain=lc
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    """Generate a distance matrix for sequences using cached alignment data."""
    try:
        # Get the alignment key and check status
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
                return JSONResponse(
                    status_code=500,
                    content={"error": f"Error computing alignment: {str(e)}"},
                )

        if status["status"] == "computing":
            return JSONResponse(
                status_code=202,
                content={"status": "computing", "message": "Alignment computation in progress"},
            )
        elif status["status"] == "error":
            return JSONResponse(
                status_code=500,
                content={"error": f"Error in alignment computation: {status.get('message', 'Unknown error')}"},
            )

        # Load cached alignment data
        project_name = project.project_name
        cache_dir = os.path.join(
            "instance", "uploads", project_name, project_name, "alignments"
        )
        cache_file = os.path.join(
            cache_dir, f"alignment_{safe_gene(hc_gene)}_{safe_gene(lc_gene)}.json"
        )

        try:
            with open(cache_file, "r") as f:
                cache_data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return JSONResponse(
                status_code=404,
                content={"error": "Alignment cache not found"},
            )

        # Get the appropriate alignment data based on chain type
        if chain == "hc":
            alignment_data = cache_data.get("hc_alignment", [])
            label_map = cache_data.get("hc_label_map", {})
        else:
            alignment_data = cache_data.get("lc_alignment", [])
            label_map = cache_data.get("lc_label_map", {})

        if not alignment_data:
            return JSONResponse(
                status_code=404,
                content={"error": f"No alignment data found for {chain.upper()} chain"},
            )

        # Convert alignment data to sequences
        sequences = []
        for orig_id, seq in alignment_data:
            if orig_id in label_map:
                sequences.append((label_map[orig_id], seq))

        if len(sequences) < 2:
            return JSONResponse(
                status_code=400,
                content={"error": f"Not enough sequences for {chain.upper()} chain"},
            )

        # Calculate distance matrix
        n_seqs = len(sequences)
        distances = np.zeros((n_seqs, n_seqs))
        
        for i in range(n_seqs):
            for j in range(i + 1, n_seqs):
                # Calculate percentage of mismatches
                seq1 = sequences[i][1]
                seq2 = sequences[j][1]
                mismatches = sum(1 for a, b in zip(seq1, seq2) if a != b and a != '-' and b != '-')
                total = sum(1 for a, b in zip(seq1, seq2) if a != '-' and b != '-')
                distance = (mismatches / total) * 100 if total > 0 else 0
                distances[i, j] = distance
                distances[j, i] = distance

        # Prepare response data
        labels = [seq[0] for seq in sequences]  # Use the mapped labels
        matrix_data = distances.tolist()

        return JSONResponse(
            content={
                "labels": labels,
                "matrix": matrix_data
            }
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error generating distance matrix: {str(e)}"},
        )
