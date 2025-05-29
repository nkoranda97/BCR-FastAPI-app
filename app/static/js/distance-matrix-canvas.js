// /static/js/distance-matrix-canvas.js – v3.0
// ----------------------------------------------------------------------------
// Clean, minimal, viewport-aware amino-acid identity matrix viewer
// ----------------------------------------------------------------------------

class DistanceMatrixCanvas {
    constructor(containerId, opts = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.error(`DistanceMatrixCanvas: Container element #${containerId} not found.`);
            throw new Error(`Container #${containerId} not found`);
        }
        // Ensure container has a non-static position for absolute positioned children
        if (getComputedStyle(this.container).position === "static") {
            this.container.style.position = "relative";
        }

        // ---------------------------------------------------------------------
        // Options (merged with user-supplied overrides)
        // ---------------------------------------------------------------------
        this.opt = {
            margin:            { top: 20, right: 20, bottom: 20, left: 20 },
            cellMinSize:       3,
            colorDomain:       [0, 100],    // lower → higher identity (inverted later)
            colorInterpolator: d3.interpolateRdYlGn,
            bgColor:           "#ffffff",
            tooltipBgColor:    "rgba(31, 41, 55, 0.9)",
            tooltipTextColor:  "#f9fafb",
            zoomExtent:        [0.1, 30],
            ...opts
        };

        // ------------------------------------------------------------------
        // Internal state
        // ------------------------------------------------------------------
        this.data          = null;   // 2-D array of distances (0-100)
        this.labels        = [];     // row/col labels (for tooltip only)
        this.n             = 0;      // matrix dimension (square)
        this.cellBaseSize  = this.opt.cellMinSize;
        this.zoomTransform = d3.zoomIdentity;

        // ------------------------------------------------------------------
        // DOM scaffolding
        // ------------------------------------------------------------------
        this._initDOM();
        this._initZoom();

        this._resizeObserver = new ResizeObserver(() => this._onResize());
        this._resizeObserver.observe(this.container);

        this._onResize(true);
    }

    // ---------------------------------------------------------------------
    // DOM helpers
    // ---------------------------------------------------------------------
    _initDOM() {
        this.container.innerHTML = "";

        // Canvas for the heat-map grid
        this.canvas = document.createElement("canvas");
        Object.assign(this.canvas.style, {
            position: "absolute",
            top: 0,
            left: 0,
            pointerEvents: "auto"
        });
        this.ctx = this.canvas.getContext("2d", { alpha: true });
        this.container.appendChild(this.canvas);

        // Tooltip (HTML)
        this.tooltip = d3.select(this.container)
            .append("div")
            .attr("role", "tooltip")
            .style("position", "absolute")
            .style("background", this.opt.tooltipBgColor)
            .style("color", this.opt.tooltipTextColor)
            .style("padding", "6px 10px")
            .style("border-radius", "4px")
            .style("font", "11px Inter, sans-serif")
            .style("visibility", "hidden")
            .style("pointer-events", "none")
            .style("z-index", "10");

        // Colour scale (note: similarity = 100 – distance)
        this.colorScale = d3.scaleSequential(this.opt.colorInterpolator)
            .domain(this.opt.colorDomain);

        // Tooltip mouse events
        d3.select(this.canvas)
            .on("mousemove.tooltip", (ev) => this._onMouseMove(ev))
            .on("mouseleave.tooltip", () => this.tooltip.style("visibility", "hidden"));
    }

    _initZoom() {
        this.zoomBehavior = d3.zoom()
            .scaleExtent(this.opt.zoomExtent)
            .on("zoom", (ev) => {
                this.zoomTransform = ev.transform;
                this._render();
            });
        d3.select(this.canvas).call(this.zoomBehavior);
    }

    // ---------------------------------------------------------------------
    // Public API
    // ---------------------------------------------------------------------
    update({ matrix, labels }) {
        if (!matrix || !labels || matrix.length === 0 || matrix.length !== labels.length) {
            console.error("DistanceMatrixCanvas: Invalid data. Matrix and labels must be non-empty and correspond.");
            this.data = null;
            this.labels = [];
            this.n = 0;
        } else {
            this.data = matrix;
            this.labels = labels;
            this.n = matrix.length;
        }

        this._calculateCellBaseSize();
        const initialTransform = this._getInitialTransform();
        d3.select(this.canvas).call(this.zoomBehavior.transform, initialTransform);
    }

    destroy() {
        this._resizeObserver?.disconnect();
        d3.select(this.canvas).on(".zoom", null).on(".tooltip", null);
        this.container.innerHTML = "";
    }

    // ---------------------------------------------------------------------
    // Layout helpers
    // ---------------------------------------------------------------------
    _getInitialTransform() {
        if (this.n === 0) return d3.zoomIdentity;

        const { margin, zoomExtent } = this.opt;
        const availW = this.width  - margin.left - margin.right;
        const availH = this.height - margin.top  - margin.bottom;
        const gridW  = this.cellBaseSize * this.n;
        const gridH  = this.cellBaseSize * this.n;

        let k = 1;
        if (gridW > 0 && gridH > 0) {
            k = Math.min(1, availW / gridW, availH / gridH);
        }
        k = Math.max(zoomExtent[0], Math.min(zoomExtent[1], k));

        const x = (availW  - gridW * k) / 2;
        const y = (availH  - gridH * k) / 2;
        return d3.zoomIdentity.translate(x, y).scale(k);
    }

    _calculateCellBaseSize() {
        if (this.n === 0) {
            this.cellBaseSize = this.opt.cellMinSize;
            return;
        }
        const availW = this.width  - this.opt.margin.left - this.opt.margin.right;
        const availH = this.height - this.opt.margin.top  - this.opt.margin.bottom;
        this.cellBaseSize = Math.max(
            this.opt.cellMinSize,
            Math.min(availW / this.n, availH / this.n)
        );
    }

    _onResize(initial = false) {
        this.width  = this.container.offsetWidth;
        this.height = this.container.offsetHeight;

        const dpr = window.devicePixelRatio || 1;
        this.canvas.width  = this.width  * dpr;
        this.canvas.height = this.height * dpr;
        Object.assign(this.canvas.style, { width: `${this.width}px`, height: `${this.height}px` });
        this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        this._calculateCellBaseSize();

        if (initial && this.n > 0) {
            d3.select(this.canvas).call(this.zoomBehavior.transform, this._getInitialTransform());
        } else {
            this._render();
        }
    }

    // ---------------------------------------------------------------------
    // RENDERING
    // ---------------------------------------------------------------------
    _render() {
        // Paint background
        this.ctx.save();
        this.ctx.fillStyle = this.opt.bgColor;
        this.ctx.fillRect(0, 0, this.width, this.height);
        this.ctx.restore();

        if (!this.data || this.n === 0) return;
        
        this._renderMatrix();
    }

    _renderMatrix() {
        const { ctx, data, n, cellBaseSize } = this;
        const { margin } = this.opt;
        const { x: panX, y: panY, k: scale } = this.zoomTransform;

        ctx.save();
        ctx.translate(margin.left + panX, margin.top + panY);
        ctx.scale(scale, scale);

        // Visible window in grid coords
        const viewX = -panX / scale;
        const viewY = -panY / scale;
        const viewW = (this.width  - margin.left - margin.right) / scale;
        const viewH = (this.height - margin.top  - margin.bottom) / scale;

        const c0 = Math.max(0, Math.floor(viewX / cellBaseSize));
        const c1 = Math.min(n, Math.ceil((viewX + viewW) / cellBaseSize));
        const r0 = Math.max(0, Math.floor(viewY / cellBaseSize));
        const r1 = Math.min(n, Math.ceil((viewY + viewH) / cellBaseSize));

        for (let r = r0; r < r1; ++r) {
            for (let c = c0; c < c1; ++c) {
                const val = data[r][c];
                if (val === undefined) continue;
                ctx.fillStyle = this.colorScale(100 - val); // similarity colour
                ctx.fillRect(c * cellBaseSize, r * cellBaseSize, cellBaseSize, cellBaseSize);
            }
        }
        ctx.restore();
    }

    // ------------------------------------------------------------------
    // Tooltip handling
    // ------------------------------------------------------------------
    _onMouseMove(ev) {
        if (!this.data || this.n === 0) {
            this.tooltip.style("visibility", "hidden");
            return;
        }

        const { margin } = this.opt;
        const { x: panX, y: panY, k: scale } = this.zoomTransform;
        const cell = this.cellBaseSize;

        const [mx, my] = d3.pointer(ev, this.canvas);
        const gridX = (mx - margin.left - panX) / scale;
        const gridY = (my - margin.top  - panY) / scale;

        const c = Math.floor(gridX / cell);
        const r = Math.floor(gridY / cell);
        if (r < 0 || r >= this.n || c < 0 || c >= this.n) {
            this.tooltip.style("visibility", "hidden");
            return;
        }

        const sim = (100 - this.data[r][c]).toFixed(2);
        const lblR = this.labels[r];
        const lblC = this.labels[c];

        this.tooltip
            .style("visibility", "visible")
            .html(`<strong>${lblR}</strong> vs <strong>${lblC}</strong><br>Similarity: ${sim}%`)
            .style("left", `${mx + 10}px`)
            .style("top",  `${my + 10}px`);
    }
}

// ----------------------------------------------------------------------------
// Example usage (for manual testing – remove in production)
// ----------------------------------------------------------------------------
/*
window.addEventListener("DOMContentLoaded", () => {
    const id = "distance-matrix-container";
    let el = document.getElementById(id);
    if (!el) {
        el = document.createElement("div");
        el.id = id;
        el.style.cssText = "width:800px;height:600px;border:1px solid #ccc";
        document.body.appendChild(el);
    }

    const N = 25;
    const labels = Array.from({ length: N }, (_, i) => `Sequence_${String.fromCharCode(65 + i)}_long_name_test`);
    const matrix = Array.from({ length: N }, () => Array.from({ length: N }, () => Math.random() * 100));

    const vis = new DistanceMatrixCanvas(id);
    vis.update({ matrix, labels });
});
*/

