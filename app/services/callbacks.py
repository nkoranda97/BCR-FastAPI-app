from bokeh.models import CustomJS


def side_panel_callback(source, x, project_id):
    """
    Creates a callback for the side panel that opens a modal and fetches LC gene aggregation when clicking on a bar in the plot.
    """
    return CustomJS(
        args=dict(source=source),
        code=f"""
        var selected = source.selected.indices;
        if (selected.length > 0) {{
            var index = selected[0];
            var category = source.data['{x}'][index];
            // Fetch LC gene aggregation from backend
            fetch(`/analyze/lc_aggregation/{project_id}/` + encodeURIComponent(category))
                .then(response => response.json())
                .then(data => {{
                    var content = '';
                    if (data.lc_genes && data.lc_genes.length > 0) {{
                        content += '<table class="min-w-full text-left text-sm">';
                        content += '<thead><tr><th class="px-2 py-1">LC Gene</th><th class="px-2 py-1">Count</th></tr></thead><tbody>';
                        data.lc_genes.forEach(function(row) {{
                            content += `<tr><td class="px-2 py-1"><a href=\"/analyze/hc_lc_detail/{project_id}/${{encodeURIComponent(category)}}/${{encodeURIComponent(row.gene)}}\" class=\"text-blue-600 hover:underline\">${{row.gene}}</a></td><td class=\"px-2 py-1\">${{row.count}}</td></tr>`;
                        }});
                        content += '</tbody></table>';
                    }} else {{
                        content = '<div class="text-gray-500">No LC genes found for this HC gene.</div>';
                    }}
                    var modal = document.getElementById('lc-modal');
                    var modalContent = document.getElementById('lc-modal-content');
                    if (modal && modalContent) {{
                        modalContent.innerHTML = content;
                        modal.classList.remove('hidden');
                        document.getElementById('lc-modal-overlay').classList.remove('hidden');
                    }}
                }});
        }}
    """,
    )
