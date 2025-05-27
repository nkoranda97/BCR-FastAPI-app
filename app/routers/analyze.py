from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import re
import pandas as pd
import os
import json

from ..database import get_db, Project

from ..services.ddl import (
    load_project,
    merge_data,
    lazy_classifier,
    compute_alignment_and_consensus,
    best_translation,
)
from ..dependencies import get_project, get_project_data, get_template_context, get_project_or_404
from ..schemas.forms import GeneSelect
from app.services.germline_annotation import get_germline_and_annotation

router = APIRouter(prefix="/analyze", tags=["analyze"])

templates = Jinja2Templates(directory="app/templates")


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
        return {
            'labels': counts.index.tolist(),
            'values': counts.values.tolist()
        }

    chart_data = {
        'v_call': prepare_chart_data('v_call_VDJ'),
        'c_call': prepare_chart_data('c_call_VDJ'),
        'j_call': prepare_chart_data('j_call_VDJ'),
        'isotype': prepare_chart_data('isotype')
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
    "/alignment/{project_id}", response_class=HTMLResponse, name="analyze.alignment"
)
async def alignment(
    request: Request,
    project_id: int,
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    """Generate alignment view for a project."""
    vdj, adata = project_data
    df = vdj.metadata

    p = alignment_viewer.view_alignment(vdj.data, "IGKV3-4*01", title="IGKV3-4*01")
    script, div = components([p])

    return templates.TemplateResponse(
        "analyze/alignment.html",
        get_template_context(
            request=request,
            project=project,
            project_id=project_id,
            script=script,
            div=div,
            active_tab="alignments",
        ),
    )


@router.get("/logo/{project_id}", response_class=HTMLResponse, name="analyze.logo")
@router.post("/logo/{project_id}", response_class=HTMLResponse, name="analyze.logo")
async def logo(
    request: Request,
    project_id: int,
    gene: Optional[str] = Form(None),
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    """Generate logo for a project."""
    vdj, adata = project_data
    genes = vdj.data["v_call"].unique()

    form = GeneSelect(genes)
    script = None
    div = None

    if gene:
        p = generate_logo(
            vdj.data, "seqlogo", color="proteinClustal", width=16, gene=gene
        )
        script, div = components([p])

    return templates.TemplateResponse(
        "analyze/logo.html",
        get_template_context(
            request=request,
            project=project,
            project_id=project_id,
            script=script,
            div=div,
            active_tab="logo",
            form=form,
        ),
    )


@router.get(
    "/gene_agg/{project_id}/{outer_gene}/{inner_gene}",
    response_class=HTMLResponse,
    name="analyze.gene_agg",
)
async def gene_agg(
    request: Request,
    project_id: int,
    outer_gene: str,
    inner_gene: str,
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    """Generate gene aggregation view for a project."""
    vdj, adata = project_data
    outer_gene_type = lazy_classifier(outer_gene)
    inner_gene_type = lazy_classifier(inner_gene)

    print(f"Gene types: {outer_gene_type}, {inner_gene_type}")  # Debug log

    if not outer_gene_type or not inner_gene_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not classify gene types for {outer_gene} and/or {inner_gene}",
        )

    data = merge_data(vdj)
    print(f"Original data shape: {data.shape}")  # Debug log
    print(f"Available columns: {data.columns.tolist()}")  # Debug log

    # For 'all' case, don't filter by inner gene
    if inner_gene.lower() == "all":
        data = data[data[outer_gene_type] == outer_gene]
    else:
        data = data[
            (data[outer_gene_type] == outer_gene)
            & (data[inner_gene_type] == inner_gene)
        ]

    print(f"Filtered data shape: {data.shape}")  # Debug log

    if data.empty:
        return templates.TemplateResponse(
            "analyze/agg_gene.html",
            get_template_context(
                request=request,
                project=project,
                project_id=project_id,
                outer_gene=outer_gene,
                inner_gene=inner_gene,
                resources=CDN.render(),
            ),
        )

    # Check if we have sequence data
    if "sequence" not in data.columns:
        print("No sequence column found in data")  # Debug log
        return templates.TemplateResponse(
            "analyze/agg_gene.html",
            get_template_context(
                request=request,
                project=project,
                project_id=project_id,
                outer_gene=outer_gene,
                inner_gene=inner_gene,
                resources=CDN.render(),
            ),
        )

    p = generate_logo(
        data, "seqlogo", chain="H", color="proteinClustal", width=16, gene="all"
    )
    script, div = components([p])
    resources = CDN.render()
    return templates.TemplateResponse(
        "analyze/agg_gene.html",
        get_template_context(
            request=request,
            project=project,
            project_id=project_id,
            script=script,
            div=div,
            outer_gene=outer_gene,
            inner_gene=inner_gene,
            resources=resources,
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
    # --- File-based cache setup ---
    def safe_gene(g):
        return g.replace('/', '_').replace('*', '_').replace('|', '_').replace(' ', '_')
    project_name = project.project_name
    align_dir = os.path.join('instance', 'uploads', project_name, project_name, 'alignments')
    os.makedirs(align_dir, exist_ok=True)
    cache_file = os.path.join(align_dir, f"alignment_{safe_gene(hc_gene)}_{safe_gene(lc_gene)}.json")
    # Try to load from cache
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            return JSONResponse(content=json.load(f))
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
    hc_ids = [row["sequence_id"] for row in hc_table if row["IGH"] and isinstance(row["IGH"], str) and row["IGH"].strip()]
    hc_seqs = [row["IGH"] for row in hc_table if row["IGH"] and isinstance(row["IGH"], str) and row["IGH"].strip()]
    lc_ids = [row["sequence_id"] for row in lc_table if lc_col and row.get(lc_col) and isinstance(row[lc_col], str) and row[lc_col].strip()]
    lc_seqs = [row[lc_col] for row in lc_table if lc_col and row.get(lc_col) and isinstance(row[lc_col], str) and row[lc_col].strip()]
    hc_label_map = {orig_id: f"HC-{i+1}" for i, orig_id in enumerate(hc_ids)}
    lc_label_map = {orig_id: f"LC-{i+1}" for i, orig_id in enumerate(lc_ids)}
    hc_alignment, hc_consensus, hc_match_matrix = compute_alignment_and_consensus(
        hc_seqs, hc_ids
    )
    lc_alignment, lc_consensus, lc_match_matrix = compute_alignment_and_consensus(
        lc_seqs, lc_ids
    )
    species = project.species
    germ_anno = get_germline_and_annotation(hc_gene, species, 'hc')
    hc_json = []
    hc_region_blocks = None
    if germ_anno:
        germ_seq, region_arr, region_blocks = germ_anno
        hc_region_blocks = region_blocks
        if region_arr:
            region_str = ''.join(region_arr)
            hc_json.append({"name": "Region", "seq": region_str})
        hc_json.append({"name": "Germline", "seq": germ_seq})
    hc_json.extend([
        {"name": hc_label_map[orig_id], "seq": seq}
        for orig_id, seq in hc_alignment
    ])
    if hc_consensus:
        hc_json.append({"name": "Consensus", "seq": hc_consensus})
    lc_region_blocks = None
    germ_anno_lc = get_germline_and_annotation(lc_gene, species, 'lc')
    lc_json = []
    if germ_anno_lc:
        lc_seq, lc_region_arr, lc_blocks = germ_anno_lc
        lc_region_blocks = lc_blocks
        if lc_region_arr:
            region_str = ''.join(lc_region_arr)
            lc_json.append({"name": "Region", "seq": region_str})
        lc_json.append({"name": "Germline", "seq": lc_seq})
    lc_json.extend([
        {"name": lc_label_map[orig_id], "seq": seq}
        for orig_id, seq in lc_alignment
    ])
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
        "lc_region_blocks": lc_region_blocks
    }
    with open(cache_file, 'w') as f:
        json.dump(result, f)
    return JSONResponse(content=result)


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


@router.get("/gene_explorer/{project_id}", response_class=HTMLResponse, name="analyze.gene_explorer")
async def gene_explorer(
    request: Request,
    project_id: int,
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data),
):
    """Gene Explorer: List V genes and their counts."""
    vdj, adata = project_data
    df = vdj.metadata
    v_counts = df['v_call_VDJ'].value_counts().reset_index()
    v_counts.columns = ['gene', 'count']
    v_genes = v_counts.to_dict(orient='records')
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
        (merged["v_call_VDJ"] == hc_gene) & 
        (merged["locus_VDJ"] == "IGH")
    ].copy()
    
    filtered["IGH"] = filtered["IGH"].apply(best_translation)
    
    # Convert to list of dicts
    sequences = []
    for _, row in filtered.drop_duplicates(subset=["sequence_id"]).iterrows():
        if row["IGH"] and isinstance(row["IGH"], str) and row["IGH"].strip():
            sequences.append({
                "name": f"HC-{len(sequences) + 1}",
                "seq": row["IGH"]
            })
    
    return sequences

async def get_lc_sequences(project_data: tuple, lc_gene: str):
    """Get light chain sequences for a project and gene."""
    vdj, _ = project_data
    merged = merge_data(vdj)
    
    # Determine LC column based on gene prefix
    lc_col = "IGK" if lc_gene.startswith("IGK") else "IGL"
    
    # Filter for the LC gene and translate
    filtered = merged[
        (merged["v_call_VJ"] == lc_gene)
    ].copy()
    
    filtered[lc_col] = filtered[lc_col].apply(best_translation)
    
    # Convert to list of dicts
    sequences = []
    for _, row in filtered.drop_duplicates(subset=["sequence_id"]).iterrows():
        if row[lc_col] and isinstance(row[lc_col], str) and row[lc_col].strip():
            sequences.append({
                "name": f"LC-{len(sequences) + 1}",
                "seq": row[lc_col]
            })
    
    return sequences

@router.get(
    "/download_fasta/{project_id}/{hc_gene}/{lc_gene}/{chain_type}",
    response_class=Response,
    name="analyze.download_fasta"
)
async def download_fasta(
    request: Request,
    project_id: str,
    hc_gene: str,
    lc_gene: str,
    chain_type: str,
    project: Project = Depends(get_project),
    project_data: tuple = Depends(get_project_data)
):
    """Download FASTA file for HC/LC gene pair."""
    # Get sequences
    if chain_type == 'hc':
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
    fasta_content = "\n".join(
        f">{seq['name']}\n{seq['seq']}"
        for seq in sequences
    )
    
    return Response(
        content=fasta_content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

def compute_consensus(sequences):
    """Compute consensus sequence from a list of sequences."""
    if not sequences:
        return ""
    
    # Get max length
    max_len = max(len(seq['seq']) for seq in sequences)
    
    # For each position, count amino acids
    consensus = []
    for i in range(max_len):
        counts = {}
        for seq in sequences:
            aa = seq['seq'][i] if i < len(seq['seq']) else '-'
            counts[aa] = counts.get(aa, 0) + 1
        
        # Get most common amino acid
        best_aa = max(counts.items(), key=lambda x: x[1])[0]
        consensus.append(best_aa)
    
    return ''.join(consensus)
