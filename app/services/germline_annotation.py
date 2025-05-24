import os
from typing import Tuple, Optional
from Bio import SeqIO
import re
import csv

# Map species to file paths
IMGT_FASTA_PATHS = {
    'human': 'app/database/igblast/fasta/imgt_aa_human_ig_v.fasta',
    'mouse': 'app/database/igblast/fasta/imgt_aa_mouse_ig_v.fasta',
}
ANNOTATION_CSV_PATHS = {
    'mouse': {
        'hc': 'app/database/annotations/mouse_aa_hc.csv',
        'lc': 'app/database/annotations/mouse_aa_lc.csv',
    },
    'human': {
        'hc': 'app/database/annotations/human_aa_hc.csv',  # placeholder
        'lc': 'app/database/annotations/human_aa_lc.csv',  # placeholder
    },
}

REGION_ORDER = {
    'hc': ['HFR1', 'CDR-H1', 'HFR2', 'CDR-H2', 'HFR3', 'CDR-H3', 'HFR4'],
    'lc': ['LFR1', 'CDR-L1', 'LFR2', 'CDR-L2', 'LFR3', 'CDR-L3', 'LFR4'],
}

# For Kabat files, columns are:
# gene, FWR1 start, FWR1 stop, CDR1 start, CDR1 stop, FWR2 start, FWR2 stop, CDR2 start, CDR2 stop, FWR3 start, FWR3 stop, chain type, coding frame start

def parse_kabat_annotation(gene: str, species: str) -> Optional[dict]:
    """Return region boundaries for a gene as a dict of region name -> (start, stop) (1-based, inclusive)."""
    base_gene = gene.split('*')[0]  # Only the part before the *
    path = KABAT_PATHS[species]
    pattern = re.compile(rf"^{re.escape(base_gene)}(\\*.*)?$")
    print(f"[DEBUG] Searching for gene '{gene}' (base '{base_gene}') in {path} with pattern {pattern.pattern}")
    found = False
    with open(path) as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            fields = line.strip().split('\t')
            kabat_gene = fields[0]
            if kabat_gene.startswith(base_gene):
                print(f"[DEBUG] Kabat file contains: {kabat_gene}")
            if pattern.match(kabat_gene):
                print(f"[DEBUG] Matched Kabat gene: {kabat_gene}")
                found = True
                # Parse regions
                return {
                    'FR1': (int(fields[1]), int(fields[2])),
                    'CDR1': (int(fields[3]), int(fields[4])),
                    'FR2': (int(fields[5]), int(fields[6])),
                    'CDR2': (int(fields[7]), int(fields[8])),
                    'FR3': (int(fields[9]), int(fields[10])),
                }
    if not found:
        print(f"[WARN] No Kabat annotation found for gene '{gene}' (base '{base_gene}') in {path}")
    return None

def parse_custom_annotation(gene: str, species: str, chain_type: str) -> Optional[dict]:
    path = ANNOTATION_CSV_PATHS.get(species, {}).get(chain_type)
    if not path or not os.path.exists(path):
        return None
    base_gene = gene.split('*')[0]
    with open(path, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['sequence_id'] == gene or row['sequence_id'].startswith(base_gene):
                region_dict = {}
                for region in REGION_ORDER[chain_type]:
                    val = row.get(region, '').replace(' ', '')
                    if val and val != '-' and '-' in val:
                        start, stop = map(int, val.split('-'))
                        region_dict[region] = (start, stop)
                return region_dict if region_dict else None
    return None

def build_region_string(region_dict: dict, seq_len: int, chain_type: str) -> list:
    arr = ['UNK'] * seq_len
    for region in REGION_ORDER[chain_type]:
        if region in region_dict:
            start, stop = region_dict[region]
            for i in range(start-1, stop):
                if 0 <= i < seq_len:
                    arr[i] = region
    return arr

def build_region_blocks(region_dict: dict, seq_len: int, chain_type: str) -> list:
    blocks = []
    for region in REGION_ORDER[chain_type]:
        if region in region_dict:
            start, end = region_dict[region]
            start = max(1, start)
            end = min(seq_len, end)
            if start <= end:
                blocks.append((region, start, end))
    return blocks

def get_germline_sequence(gene: str, species: str) -> Optional[str]:
    """Return the germline sequence for a gene from the IMGT FASTA (as a single string, uppercased, no gaps)."""
    path = IMGT_FASTA_PATHS[species]
    base_gene = gene.split('*')[0]
    for record in SeqIO.parse(path, 'fasta'):
        # Match on base gene name (e.g., IGHV1-52 matches IGHV1-52*01)
        if base_gene in record.id or f'|{base_gene}' in record.description:
            print(f"[DEBUG] Matched germline FASTA record: {record.id}")
            return str(record.seq).replace('-', '').replace('.', '').upper()
    print(f"[WARN] No germline FASTA record found for {gene} (base {base_gene}) in {path}")
    return None

def get_germline_and_annotation(gene: str, species: str, chain_type: str):
    seq = get_germline_sequence(gene, species)
    if not seq:
        return None
    region_dict = parse_custom_annotation(gene, species, chain_type)
    if region_dict:
        region_arr = build_region_string(region_dict, len(seq), chain_type)
        region_blocks = build_region_blocks(region_dict, len(seq), chain_type)
        return seq, region_arr, region_blocks
    return seq, None, None

