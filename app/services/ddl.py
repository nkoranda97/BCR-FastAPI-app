import os
import re
from typing import Optional, Tuple, Union
import dandelion as ddl
import scanpy as sc
import pandas as pd
from collections import defaultdict
from fastapi import HTTPException
from Bio import AlignIO, SeqIO
from Bio.Align import MultipleSeqAlignment
from Bio.Align import AlignInfo
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio import pairwise2
from Bio.Seq import Seq
from Bio.Data.CodonTable import TranslationError

from app.core.config import settings


async def preprocess(
    upload_folder: str, samples: list, data_uploaded: str, species: str = "human"
) -> Union[Tuple[str, str], str]:
    """
    Preprocess the uploaded data using dandelion

    Args:
        upload_folder: Path to the upload folder
        samples: List of sample names
        data_uploaded: Type of data uploaded ('Both' or 'VDJ')
        species: Species of the data (default: 'human')

    Returns:
        Tuple of paths to processed files or single path for VDJ only
    """
    # Setup environment variables
    settings.setup_environment()

    # Fix path construction to prevent duplication
    sample_paths = []
    for sample in samples:
        # Ensure we don't duplicate the upload_folder in the path
        if sample.startswith(upload_folder):
            sample_paths.append(sample)
        else:
            sample_paths.append(os.path.join(upload_folder, sample))

    print(f"Sample paths: {sample_paths}")  # Debug log

    if data_uploaded == "Both":
        try:
            ddl.pp.format_fastas(sample_paths, filename_prefix="filtered")
            ddl.pp.reannotate_genes(
                sample_paths, org=species, filename_prefix="filtered"
            )
            ddl.pp.assign_isotypes(
                sample_paths, plot=False, org=species, filename_prefix="filtered"
            )

            adata_list = []
            for sample in sample_paths:
                h5_file = next(
                    (file for file in os.listdir(sample) if file.endswith(".h5")), None
                )
                if not h5_file:
                    raise HTTPException(
                        status_code=400, detail=f"No .h5 file found in {sample}"
                    )
                h5_file_path = os.path.join(sample, h5_file)
                adata = sc.read_10x_h5(h5_file_path, gex_only=True)
                adata.obs["sampleid"] = sample
                adata.obs_names = [
                    f"{sample}_{str(j).split('-')[0]}" for j in adata.obs_names
                ]
                adata.var_names_make_unique()
                adata_list.append(adata)

            if not adata_list:
                raise HTTPException(
                    status_code=400, detail="No valid .h5 files found in any sample"
                )

            adata = adata_list[0].concatenate(adata_list[1:], index_unique=None)
            vdj_list = []
            for sample in sample_paths:
                tsv_file = next(
                    (
                        file
                        for file in os.listdir(os.path.join(sample, "dandelion"))
                        if file.endswith(".tsv")
                    ),
                    None,
                )
                if not tsv_file:
                    raise HTTPException(
                        status_code=400,
                        detail=f"No .tsv file found in {sample}/dandelion",
                    )
                tsv_file_path = os.path.join(sample, "dandelion", tsv_file)
                vdj = ddl.read_10x_airr(tsv_file_path)
                vdj_list.append(vdj)

            if not vdj_list:
                raise HTTPException(
                    status_code=400, detail="No valid .tsv files found in any sample"
                )

            vdj = ddl.concat(vdj_list)
            sc.pp.filter_genes(adata, min_cells=3)
            sc.pp.normalize_total(adata, target_sum=1e4)
            sc.pp.log1p(adata)
            adata.raw = adata
            sc.pp.highly_variable_genes(
                adata, min_mean=0.0125, max_mean=3, min_disp=0.5
            )
            adata = adata[:, adata.var.highly_variable]
            sc.pp.scale(adata, max_value=10)
            sc.tl.pca(adata, svd_solver="arpack")
            sc.pp.neighbors(adata, n_pcs=20)
            sc.tl.umap(adata)
            sc.tl.leiden(adata, resolution=0.5)
            vdj, adata = ddl.pp.check_contigs(vdj, adata)
            ddl.tl.find_clones(vdj)
            ddl.tl.generate_network(vdj)
            ddl.tl.clone_size(vdj)

            adata_path = os.path.join(upload_folder, "processed_adata.h5ad")
            vdj_path = os.path.join(upload_folder, "processed_vdj.h5ddl")

            adata.write(adata_path)
            vdj.write(vdj_path)

            return adata_path, vdj_path

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error processing data: {str(e)}"
            )

    else:  # VDJ only
        try:
            ddl.pp.format_fastas(sample_paths, filename_prefix="filtered")

            ddl.pp.reannotate_genes(
                sample_paths, org=species, filename_prefix="filtered"
            )

            ddl.pp.assign_isotypes(
                sample_paths, plot=False, org=species, filename_prefix="filtered"
            )

            vdj_list = []
            for sample in sample_paths:
                tsv_file = next(
                    (
                        file
                        for file in os.listdir(os.path.join(sample, "dandelion"))
                        if file.endswith(".tsv")
                    ),
                    None,
                )
                if not tsv_file:
                    raise HTTPException(
                        status_code=400,
                        detail=f"No .tsv file found in {sample}/dandelion",
                    )
                tsv_file_path = os.path.join(sample, "dandelion", tsv_file)
                vdj = ddl.read_10x_airr(tsv_file_path)
                vdj_list.append(vdj)

            if not vdj_list:
                raise HTTPException(
                    status_code=400, detail="No valid .tsv files found in any sample"
                )

            vdj = ddl.concat(vdj_list)
            vdj = ddl.pp.check_contigs(vdj)
            ddl.tl.find_clones(vdj)
            ddl.tl.generate_network(vdj)
            ddl.tl.clone_size(vdj)

            vdj_path = os.path.join(upload_folder, "processed_vdj.h5ddl")
            try:
                vdj.write(vdj_path)
                return vdj_path
            except ValueError:
                vdj_path = os.path.join(upload_folder, "processed_vdj.pkl")
                vdj.write_pkl(vdj_path)
                return vdj_path

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error processing VDJ data: {str(e)}"
            )


async def load_project(project: dict) -> Tuple[ddl.Dandelion, Optional[sc.AnnData]]:
    """
    Load a project's data

    Args:
        project: Dictionary containing project information

    Returns:
        Tuple of (vdj data, adata) where adata may be None
    """
    try:
        vdj_path = project["vdj_path"]
        adata_path = project["adata_path"]

        if vdj_path.endswith(".h5ddl"):
            vdj = ddl.read_h5ddl(vdj_path)
        elif vdj_path.endswith(".pkl"):
            vdj = ddl.read_pkl(vdj_path)
        else:
            raise HTTPException(status_code=400, detail="Invalid VDJ file format")

        if adata_path != "NULL":
            adata = sc.read(adata_path)
            return vdj, adata
        else:
            return vdj, None

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading project: {str(e)}")


def merge_data(vdj: ddl.Dandelion) -> pd.DataFrame:
    """
    Merge VDJ data into a single DataFrame

    Args:
        vdj: Dandelion object containing VDJ data

    Returns:
        Merged DataFrame
    """
    try:

        def merge_dicts(lst):
            dct = defaultdict(list)
            for d in lst:
                for k, v in d.items():
                    dct[k].append(v)
            return dict(dct)

        data = vdj.data
        metadata = vdj.metadata

        # Ensure we have sequence data
        if (
            "sequence_alignment" not in data.columns
            or "sequence_alignment_aa" not in data.columns
        ):
            raise HTTPException(
                status_code=500, detail="No sequence alignment data found in VDJ data"
            )

        # Create locus dictionary with sequences
        data["locus_dict"] = data.apply(
            lambda row: {row["locus"]: row["sequence_alignment"]}, axis=1
        )
        data = data[
            ["locus_dict", "sequence_alignment", "sequence_alignment_aa"]
        ].reset_index()  # Include both nucleotide and amino acid sequences
        data["sequence_id"] = data["sequence_id"].str.replace(
            r"_contig_[12]", "", regex=True
        )
        data = data.groupby("sequence_id").agg(list).reset_index()
        data["locus_dict"] = data["locus_dict"].apply(merge_dicts)
        locus = pd.json_normalize(data["locus_dict"])
        data = pd.concat([data.drop(columns=["locus_dict"]), locus], axis=1)

        # Handle sequence data - ensure we get a single sequence string
        def extract_sequence(seq_list):
            if isinstance(seq_list, list):
                # Take the first sequence if multiple exist
                return seq_list[0] if seq_list else ""
            return seq_list if isinstance(seq_list, str) else ""

        data["sequence"] = data["sequence_alignment"].apply(extract_sequence)
        data["sequence_aa"] = data["sequence_alignment_aa"].apply(
            extract_sequence
        )  # Add amino acid sequence

        # Handle locus data
        data["IGK"] = data["IGK"].apply(
            lambda lst: ",".join(lst) if isinstance(lst, list) else lst
        )
        data["IGH"] = data["IGH"].apply(
            lambda lst: ",".join(lst) if isinstance(lst, list) else lst
        )
        data["IGL"] = data["IGL"].apply(
            lambda lst: ",".join(lst) if isinstance(lst, list) else lst
        )

        # Merge with metadata
        merged = metadata.merge(
            data, left_on=metadata.index, right_on=data["sequence_id"]
        )
        merged.drop(["key_0"], axis=1, inplace=True)

        # Ensure sequence columns are string type and not empty
        merged["sequence"] = merged["sequence"].astype(str)
        merged["sequence_aa"] = merged["sequence_aa"].astype(str)
        merged = merged[merged["sequence"].str.len() > 0]

        return merged

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error merging data: {str(e)}")


def lazy_classifier(gene: str) -> Optional[str]:
    """
    Classify a gene based on its prefix

    Args:
        gene: Gene name to classify

    Returns:
        Classification type or None if not recognized
    """
    if not gene:
        return None

    # Handle 'all' case
    if gene.lower() == "all":
        return "v_call_VDJ"  # Default to V gene for 'all'

    # Extract the prefix (e.g., 'IGHV' from 'IGHV1-80')
    prefix = "".join(c for c in gene if not c.isdigit() and c != "-")

    if prefix.startswith("IGHV"):
        return "v_call_VDJ"
    elif prefix.startswith("IGHD"):
        return "d_call_VDJ"
    elif prefix.startswith("IGHJ"):
        return "j_call_VDJ"
    elif (
        prefix.startswith("IGHG")
        or prefix.startswith("IGHA")
        or prefix.startswith("IGHD")
        or prefix.startswith("IGHE")
        or prefix.startswith("IGHM")
    ):
        return "c_call_VDJ"
    elif prefix.startswith("IGKV") or prefix.startswith("IGLV"):
        return "v_call_VJ"
    elif prefix.startswith("IGKJ") or prefix.startswith("IGLJ"):
        return "j_call_VJ"
    elif prefix.startswith("IGKC") or prefix.startswith("IGLC"):
        return "c_call_VJ"
    return None


def compute_alignment_and_consensus(seqs):
    """
    Aligns sequences and computes consensus. Returns:
    - alignment: list of aligned sequence strings
    - consensus: consensus string
    - match_matrix: list of bools (True if consensus, False if mismatch)
    """
    # Remove empty or None
    seqs = [s for s in seqs if s]
    if len(seqs) < 2:
        return seqs, seqs[0] if seqs else "", []
    # Convert to SeqRecord
    records = [SeqRecord(Seq(seq), id=str(i)) for i, seq in enumerate(seqs)]
    # For demo, align by padding to max length (real MSA would use Clustal/MAFFT)
    max_len = max(len(r.seq) for r in records)
    for r in records:
        r.seq = Seq(str(r.seq).ljust(max_len, "-"))
    alignment = MultipleSeqAlignment(records)
    summary_align = AlignInfo.SummaryInfo(alignment)
    consensus = str(summary_align.dumb_consensus())
    # Build match matrix
    align_strs = [str(r.seq) for r in alignment]
    match_matrix = []
    for i, c in enumerate(consensus):
        col = [seq[i] for seq in align_strs]
        match_matrix.append([base == c for base in col])
    return align_strs, consensus, match_matrix


def best_translation(nt) -> str:
    """
    Translate nucleotide → amino-acid, choosing the reading frame
    with the longest run that has no internal stop codons.

    Handles:
      • NaN / None  →  ""
      • list[str]   →  first entry
      • comma-joined strings (seq1,seq2,…) → use the longest chunk
    """
    # ---------- normalise input ----------
    if nt is None or (isinstance(nt, float) and pd.isna(nt)):
        return ""

    if isinstance(nt, list):
        nt = nt[0] if nt else ""

    if not isinstance(nt, str):
        return ""

    # pick longest part if multiple sequences are comma-joined
    if "," in nt:
        nt = max(nt.split(","), key=len)

    # keep only IUPAC nucleotide letters
    nt = re.sub(r"[^ACGTURYKMSWBDHVN]", "", nt.upper())
    if len(nt) < 3:
        return ""

    # ---------- translate all three frames ----------
    def translate(offset: int) -> str:
        try:
            return str(Seq(nt[offset:]).translate(to_stop=False))
        except TranslationError:
            return ""

    frames = [translate(f) for f in (0, 1, 2)]

    # prefer frames without internal stops
    full_orfs = [aa for aa in frames if "*" not in aa[:-1]]
    if full_orfs:
        return max(full_orfs, key=len)

    # otherwise pick frame with longest ORF fragment
    def longest_fragment(aa: str) -> int:
        return max((len(seg) for seg in aa.split("*")), default=0)

    return max(frames, key=longest_fragment)
