from bokeh.models import (
    ColumnDataSource,
    HoverTool,
    CustomJS,
    Dropdown,
    Slider,
    ColorPicker,
    TextInput,
    DataTable,
    TableColumn,
    Div,
    HTMLTemplateFormatter,
)
from bokeh.plotting import figure, show
from bokeh.layouts import column, row
from bokeh.palettes import Category20
from bokeh.transform import cumsum
import pandas as pd
from math import pi
from collections import Counter
import os

from .callbacks import side_panel_callback


class Plot:
    @staticmethod
    def bar(df, x, project_id):
        df[x] = df[x].astype(str)

        # Group data and sort
        group = df.groupby(x).size().reset_index(name="counts")
        group = group.sort_values(by="counts", ascending=False)

        x_agg = df.groupby(x).agg({col: list for col in df.columns if col != x})

        def format_dict(lst):
            counter = Counter(lst)
            sorted_items = sorted(
                counter.items(), key=lambda item: item[1], reverse=True
            )
            return "\n".join([f"{k}: {v}" for k, v in sorted_items])

        x_agg = x_agg.map(format_dict)
        x_agg.reset_index(inplace=True)
        group = group.merge(x_agg, on=x)

        # Add URLs to the data source
        source = ColumnDataSource(group)

        # Create the plot
        p = figure(
            y_range=group[x].astype(str),
            title="Graph Title",
            toolbar_location="right",
            tools="tap,pan,wheel_zoom,box_zoom,reset,save",
            height=600,
            width=1200,
        )
        p.hbar(y=x, right="counts", height=0.9, source=source)

        # Add hover tool
        hover = HoverTool()
        hover.tooltips = [("Category", f"@{x}"), ("Count", "@counts")]
        p.add_tools(hover)

        p.ygrid.grid_line_color = None
        p.x_range.start = 0

        callback = side_panel_callback(source, x, project_id)
        p.js_on_event("tap", callback)

        toolbox = row()

        # Title input
        title_input = TextInput(value="Graph Title", title="Graph Title:")
        title_input_callback = CustomJS(
            args=dict(p=p),
            code="""
            p.title.text = cb_obj.value;
        """,
        )
        title_input.js_on_change("value", title_input_callback)
        toolbox.children.append(title_input)

        # Color picker for bars
        color_picker = ColorPicker(title="Bar Color", color="#31AADE")
        color_picker_callback = CustomJS(
            args=dict(renderer=p.renderers[0]),
            code="""
            renderer.glyph.fill_color = cb_obj.color;
            renderer.glyph.line_color = cb_obj.color;
        """,
        )
        color_picker.js_on_change("color", color_picker_callback)
        toolbox.children.append(color_picker)

        # Dropdown for bar width
        bar_width_dropdown = Dropdown(
            label="Bar Width", menu=[("0.5", "0.5"), ("0.7", "0.7"), ("0.9", "0.9")]
        )
        bar_width_callback = CustomJS(
            args=dict(renderer=p.renderers[0]),
            code="""
            renderer.glyph.height = parseFloat(cb_obj.item);
        """,
        )
        bar_width_dropdown.js_on_event("menu_item_click", bar_width_callback)
        toolbox.children.append(bar_width_dropdown)

        layout = column(p, toolbox, sizing_mode="stretch_both")

        return layout

    @staticmethod
    def pie(df, x, project_id, title=""):
        df_copy = df.copy()
        df_copy = df_copy.dropna(subset=[x])
        df_copy.loc[:, x] = df_copy[x].astype(str)

        group = df_copy.groupby(x).size().reset_index(name="counts")
        group = group.sort_values(by="counts", ascending=False)
        group.reset_index(drop=True, inplace=True)

        group["angle"] = group["counts"] / group["counts"].sum() * 2 * pi
        group["percentage"] = group["counts"] / group["counts"].sum() * 100
        colors = (Category20[20] * (len(group) // 20 + 1))[: len(group)]
        group["color"] = colors

        x_agg = df.groupby(x).agg({col: list for col in df.columns if col != x})

        def format_dict(lst):
            counter = Counter(lst)
            sorted_items = sorted(
                counter.items(), key=lambda item: item[1], reverse=True
            )
            return "\n".join([f"{k}: {v}" for k, v in sorted_items])

        x_agg = x_agg.map(format_dict)
        x_agg.reset_index(inplace=True)
        group = group.merge(x_agg, on=x)

        source = ColumnDataSource(group)

        p = figure(
            height=600,
            width=1000,
            title=title,
            toolbar_location="above",
            tools="pan,wheel_zoom,box_zoom,reset, tap",
            x_range=(-0.5, 1.0),
        )

        p.wedge(
            x=0,
            y=1,
            radius=0.4,
            start_angle=cumsum("angle", include_zero=True),
            end_angle=cumsum("angle"),
            line_color="white",
            fill_color="color",
            legend_field=x,
            source=source,
        )

        p.axis.axis_label = None
        p.axis.visible = False
        p.grid.grid_line_color = None

        hover = HoverTool()
        hover.tooltips = [
            ("Category", f"@{x}"),
            ("Count", "@counts"),
            ("Percentage", "@percentage{0.2f}%"),
        ]
        p.add_tools(hover)

        slider = Slider(start=0, end=50, value=0, step=0.01, title="Percent Cutoff")

        # Read the JavaScript file from the static directory
        js_path = os.path.join("app", "static", "js", "update_pie.js")
        with open(js_path, "r") as js_file:
            js_code = js_file.read()

        callback = CustomJS(
            args=dict(source=source, slider=slider, original_data=source.data, x=x),
            code=js_code,
        )

        slider.js_on_change("value", callback)

        callback = side_panel_callback(source, x, project_id)
        p.js_on_event("tap", callback)

        layout = column(slider, p, sizing_mode="stretch_both")

        return layout

    @staticmethod
    def table(df):
        Columns = [
            TableColumn(
                field=Ci,
                title=Ci,
                formatter=HTMLTemplateFormatter(
                    template=f'<div title="<%= value %>"><%= value %></div>'
                ),
            )
            for Ci in df.columns
        ]  # bokeh columns with tooltips
        return DataTable(
            columns=Columns, source=ColumnDataSource(df), sizing_mode="stretch_both"
        )  # bokeh table


# Create a singleton instance
plot = Plot()
