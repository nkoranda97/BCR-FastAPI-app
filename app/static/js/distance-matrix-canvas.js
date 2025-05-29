// /static/js/distance-matrix-canvas.js – v3.1
// ----------------------------------------------------------------------------
// Enhanced amino-acid identity matrix viewer with improved performance and UX
// ----------------------------------------------------------------------------

class DistanceMatrixCanvas {
    constructor(containerId, opts = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.error(`DistanceMatrixCanvas: Container element #${containerId} not found.`);
            throw new Error(`Container #${containerId} not found`);
        }
        if (getComputedStyle(this.container).position === "static") {
            this.container.style.position = "relative";
        }

        this.opt = {
            margin:            { top: 20, right: 20, bottom: 20, left: 20 },
            cellMinSize:       3,
            colorDomain:       [0, 100],
            colorInterpolator: d3.interpolateRdYlGn,
            bgColor:           "#ffffff",
            tooltipBgColor:    "rgba(31, 41, 55, 0.9)",
            tooltipTextColor:  "#f9fafb",
            zoomExtent:        [0.1, 30],
            showTooltip:       true,
            ...opts
        };

        this.data          = null;
        this.labels        = [];
        this.n             = 0;
        this.cellBaseSize  = this.opt.cellMinSize;
        this.zoomTransform = d3.zoomIdentity;
        this._tempCanvas   = document.createElement('canvas');
        this._tempCtx      = this._tempCanvas.getContext('2d');

        this._initDOM();
        this._initZoom();

        this._resizeObserver = new ResizeObserver(() => this._onResize());
        this._resizeObserver.observe(this.container);

        this._onResize(true);
    }

    _initDOM() {
        this.container.innerHTML = "";

        this.canvas = document.createElement("canvas");
        Object.assign(this.canvas.style, {
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            pointerEvents: "auto"
        });
        this.ctx = this.canvas.getContext("2d", { alpha: true });
        this.container.appendChild(this.canvas);

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
            .style("z-index", "10")
            .style("max-width", "300px")
            .style("word-break", "break-word");

        this.colorScale = d3.scaleSequential(this.opt.colorInterpolator)
            .domain(this.opt.colorDomain);

        d3.select(this.canvas)
            .on("mousemove.tooltip", (ev) => this._onMouseMove(ev))
            .on("mouseleave.tooltip", () => this.tooltip.style("visibility", "hidden"));
    }

    _initZoom() {
        this.zoomBehavior = d3.zoom()
            .scaleExtent(this.opt.zoomExtent)
            .filter(ev => {
                // Allow zoom with wheel and touch, but ignore right-click
                if (ev.type === 'wheel') return true;
                if (ev.type.startsWith('touch')) return true;
                return ev.button === 0 || ev.type === 'dblclick';
            })
            .on("zoom", (ev) => {
                this.zoomTransform = ev.transform;
                this._render();
            });
            
        d3.select(this.canvas)
            .call(this.zoomBehavior)
            .on("dblclick.zoom", () => {
                // Reset zoom on double-click
                d3.select(this.canvas)
                    .call(this.zoomBehavior.transform, this._getInitialTransform());
            });
    }

    update({ matrix, labels }) {
        if (!matrix || !labels || matrix.length === 0 || matrix.length !== labels.length) {
            console.error("DistanceMatrixCanvas: Invalid data.");
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
        this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        this._calculateCellBaseSize();

        if (initial && this.n > 0) {
            d3.select(this.canvas).call(this.zoomBehavior.transform, this._getInitialTransform());
        } else {
            this._render();
        }
    }

    _render() {
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

        const viewX = -panX / scale;
        const viewY = -panY / scale;
        const viewW = (this.width  - margin.left - margin.right) / scale;
        const viewH = (this.height - margin.top  - margin.bottom) / scale;

        const c0 = Math.max(0, Math.floor(viewX / cellBaseSize));
        const c1 = Math.min(n, Math.ceil((viewX + viewW) / cellBaseSize));
        const r0 = Math.max(0, Math.floor(viewY / cellBaseSize));
        const r1 = Math.min(n, Math.ceil((viewY + viewH) / cellBaseSize));

        const visibleWidth = c1 - c0;
        const visibleHeight = r1 - r0;
        
        if (visibleWidth <= 0 || visibleHeight <= 0) {
            ctx.restore();
            return;
        }

        // Create offscreen canvas for visible region
        this._tempCanvas.width = visibleWidth;
        this._tempCanvas.height = visibleHeight;
        const tempCtx = this._tempCtx;
        const imageData = tempCtx.createImageData(visibleWidth, visibleHeight);
        const pixels = imageData.data;
        
        // Fill image data with colors for visible cells
        for (let r = r0; r < r1; ++r) {
            for (let c = c0; c < c1; ++c) {
                const val = data[r][c];
                if (val === undefined) continue;
                
                const color = d3.color(this.colorScale(100 - val));
                const idx = ((r - r0) * visibleWidth + (c - c0)) * 4;
                
                pixels[idx]     = color.r;
                pixels[idx + 1] = color.g;
                pixels[idx + 2] = color.b;
                pixels[idx + 3] = 255;
            }
        }
        
        // Draw to offscreen canvas
        tempCtx.putImageData(imageData, 0, 0);
        
        // Draw to main canvas with proper scaling
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(
            this._tempCanvas,
            0, 0, visibleWidth, visibleHeight,
            c0 * cellBaseSize, r0 * cellBaseSize,
            visibleWidth * cellBaseSize, visibleHeight * cellBaseSize
        );

        ctx.restore();
    }

    _onMouseMove(ev) {
        if (!this.opt.showTooltip || !this.data || this.n === 0) {
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
            .html(`<strong>${lblR}</strong> vs <strong>${lblC}</strong><br>Similarity: ${sim}%`)
            .style("visibility", "visible")
            .style("left", `${mx + 10}px`)
            .style("top", `${my + 10}px`);
            
        // Adjust position if near edge
        const tooltipNode = this.tooltip.node();
        const rect = tooltipNode.getBoundingClientRect();
        const containerRect = this.container.getBoundingClientRect();
        
        let left = mx + 10;
        let top = my + 10;
        
        if (left + rect.width > containerRect.right) {
            left = containerRect.right - rect.width - 10;
        }
        if (top + rect.height > containerRect.bottom) {
            top = containerRect.bottom - rect.height - 10;
        }
        
        this.tooltip
            .style("left", `${left}px`)
            .style("top", `${top}px`);
    }
}