from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from bokeh.embed import components
from bokeh.plotting import figure
from bokeh.models import Tabs, TabPanel
from bokeh.resources import CDN
import re
import pandas as pd

from ..database import get_db, Project
from ..services.plotting import plot

# from ..services.plotting import alignment_viewer
from ..services.bokeh_logo import generate_logo
from ..services.ddl import (
    load_project,
    merge_data,
    lazy_classifier,
    compute_alignment_and_consensus,
    best_translation,
)
from ..dependencies import get_project, get_project_data, get_template_context
from ..schemas.forms import GeneSelect

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


def alignment_to_fasta(seqs):
    # seqs: list of strings
    return "\n".join([f">Seq{i + 1}\n{seq}" for i, seq in enumerate(seqs)])


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
    """
    Show details for a selected HC/LC gene pair.
    Heavy-chain AA comes from IGH; light-chain AA comes from IGK / IGL,
    translated from nucleotide to amino-acid with best_translation().
    """
    vdj, _ = project_data
    merged = merge_data(vdj)

    # ---------------- filter rows for this HC / LC pair ----------------
    filtered = merged[
        (merged["v_call_VDJ"] == hc_gene) & (merged["v_call_VJ"] == lc_gene)
    ].copy()

    # translate the chain-specific NT columns in-place
    for col in ("IGH", "IGK", "IGL"):
        filtered[col] = filtered[col].apply(best_translation)

    # Prepare tables with amino acid sequences
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

    print(f"[DEBUG] HC table length: {len(hc_table)}")
    print(f"[DEBUG] LC table length: {len(lc_table)}")
    print(f"[DEBUG] LC column: {lc_col}")
    print(
        f"[DEBUG] LC values: {[row.get(lc_col) for row in lc_table] if lc_col else []}"
    )

    # Get sequences for alignment, filtering out empty/None
    hc_seqs = [
        row["IGH"]
        for row in hc_table
        if row["IGH"] and isinstance(row["IGH"], str) and row["IGH"].strip()
    ]
    lc_seqs = [
        row[lc_col]
        for row in lc_table
        if lc_col
        and row.get(lc_col)
        and isinstance(row[lc_col], str)
        and row[lc_col].strip()
    ]

    print(f"[DEBUG] HC sequences length: {len(hc_seqs)}")
    print(f"[DEBUG] LC sequences length: {len(lc_seqs)}")

    # Compute alignments or use original sequences if too few
    hc_alignment, hc_consensus, hc_match_matrix = compute_alignment_and_consensus(
        hc_seqs
    )
    lc_alignment, lc_consensus, lc_match_matrix = compute_alignment_and_consensus(
        lc_seqs
    )

    print(f"[DEBUG] HC alignment length: {len(hc_alignment)}")
    print(f"[DEBUG] LC alignment length: {len(lc_alignment)}")

    # Convert alignments to FASTA for msa.js
    hc_fasta = alignment_to_fasta(hc_alignment)
    lc_fasta = alignment_to_fasta(lc_alignment)

    print(f"[DEBUG] HC FASTA length: {len(hc_fasta)}")
    print(f"[DEBUG] LC FASTA length: {len(lc_fasta)}")

    return templates.TemplateResponse(
        "analyze/hc_lc_detail.html",
        get_template_context(
            request=request,
            project=project,
            project_id=project_id,
            hc_gene=hc_gene,
            lc_gene=lc_gene,
            hc_table=hc_table,
            lc_table=lc_table,
            hc_alignment=hc_alignment,
            hc_consensus=hc_consensus,
            hc_match_matrix=hc_match_matrix,
            lc_alignment=lc_alignment,
            lc_consensus=lc_consensus,
            lc_match_matrix=lc_match_matrix,
            hc_fasta=hc_fasta,
            lc_fasta=lc_fasta,
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
