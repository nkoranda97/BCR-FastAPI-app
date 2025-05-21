from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, HoverTool
from bokeh.palettes import Category20
import pandas as pd
import numpy as np
from typing import Optional


def generate_logo(
    data: pd.DataFrame,
    plot_type: str = "seqlogo",
    color: str = "proteinClustal",
    width: int = 16,
    gene: str = "all",
    chain: Optional[str] = None,
) -> figure:
    """
    Generate a sequence logo plot using Bokeh.

    Args:
        data: DataFrame containing sequence data
        plot_type: Type of plot to generate ('seqlogo' or 'frequency')
        color: Color scheme to use ('proteinClustal' or 'nucleotide')
        width: Width of the plot
        gene: Gene to plot ('all' or specific gene name)
        chain: Chain type ('H' for heavy, 'L' for light)

    Returns:
        Bokeh figure object
    """
    # Filter data if gene is specified
    if gene != "all":
        # Use v_call_VDJ for heavy chain and v_call_VJ for light chain
        if chain == "H":
            data = data[data["v_call_VDJ"] == gene]
        else:
            data = data[data["v_call_VJ"] == gene]

    # Filter by chain if specified
    if chain:
        if chain == "H":
            data = data[data["v_call_VDJ"].str.startswith("IGH")]
        elif chain == "L":
            data = data[data["v_call_VJ"].str.startswith(("IGK", "IGL"))]

    # Get sequence data and handle varying lengths
    sequences = data["sequence"].tolist()
    if not sequences:
        return figure(title="No sequences found")

    # Find the maximum sequence length
    max_length = max(len(seq) for seq in sequences)

    # Pad shorter sequences with gaps
    padded_sequences = [seq + "-" * (max_length - len(seq)) for seq in sequences]

    # Calculate position-wise frequencies
    positions = range(max_length)

    # Create figure
    p = figure(
        title=f"Sequence Logo for {gene if gene != 'all' else 'All Sequences'}",
        x_range=(0, max_length),
        y_range=(0, 2),
        width=width * 50,
        height=400,
        tools="pan,wheel_zoom,box_zoom,reset,save",
    )

    # Add hover tool
    hover = HoverTool()
    hover.tooltips = [
        ("Position", "@x"),
        ("Residue", "@residue"),
        ("Frequency", "@frequency{0.00}"),
    ]
    p.add_tools(hover)

    # Plot sequence logo
    if plot_type == "seqlogo":
        # Calculate information content
        for pos in positions:
            residues = [seq[pos] for seq in padded_sequences]
            unique_residues = set(residues)

            # Calculate frequencies
            frequencies = {}
            for res in unique_residues:
                freq = residues.count(res) / len(residues)
                frequencies[res] = freq

            # Calculate information content
            ic = 2 - sum(-freq * np.log2(freq) for freq in frequencies.values())

            # Plot residues
            y_offset = 0
            for res, freq in sorted(
                frequencies.items(), key=lambda x: x[1], reverse=True
            ):
                height = freq * ic
                p.rect(
                    x=pos + 0.5,
                    y=y_offset + height / 2,
                    width=0.8,
                    height=height,
                    fill_color=Category20[20][hash(res) % 20],
                    line_color=None,
                )
                y_offset += height

    # Style the plot
    p.xaxis.axis_label = "Position"
    p.yaxis.axis_label = "Information Content (bits)"
    p.grid.grid_line_color = None
    p.outline_line_color = None

    return p
