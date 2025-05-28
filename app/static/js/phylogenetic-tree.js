/* ======================================================================
   PhylogeneticTree – v2.0
   ----------------------------------------------------------------------
   • Responsive: redraws on container resize (ResizeObserver)
   • Smooth zoom / pan + dedicated API for external buttons
   • Collapse / expand on click with visual cue
   • Search-as-you-type highlight (adds .hit opacity)
   • High-DPI PNG / lossless SVG export
   =====================================================================*/

   class PhylogeneticTree {
    constructor(containerId, opts = {}) {
      /* --------- DOM + basic metrics ---------------------------------- */
      this.container = document.getElementById(containerId);
      if (!this.container) throw new Error(`Container #${containerId} not found`);
  
      const defaults = {
        margin: { top: 24, right: 120, bottom: 24, left: 120 },
        nodeRadius: 4,
        linkWidth: 1.5,
        fontSize: 12,
        duration: 600,
        // nice pastel palette that still distinguishes depths 0-9
        colorScheme: d3.scaleOrdinal([
          '#6366f1', '#34d399', '#fbbf24', '#f87171',
          '#60a5fa', '#f472b6', '#a78bfa', '#facc15', '#2dd4bf', '#fb923c'
        ]),
        ...opts
      };
      this.opts = defaults;
  
      /* --------- SVG scaffold ----------------------------------------- */
      const { width, height } = this.#containerBox();
      this.svgRoot = d3.select(this.container) // <svg> for export
        .append('svg')
        .attr('width', width)
        .attr('height', height)
        .attr('viewBox', `0 0 ${width} ${height}`)
        .attr('preserveAspectRatio', 'xMidYMid meet')
        .classed('select-none', true);
  
      // group that actually holds the tree; zoom / pan acts here
      this.viewport = this.svgRoot.append('g')
        .attr('transform', `translate(${this.opts.margin.left},${this.opts.margin.top})`);
  
      /* --- capture layer: makes the whole area draggable / wheel-zoomable --- */
      this.bg = this.viewport
        .append('rect')
        .attr('class', 'zoom-bg')
        .attr('x', -this.opts.margin.left)
        .attr('y', -this.opts.margin.top)
        .attr('width', width)
        .attr('height', height)
        .attr('fill', 'transparent')
        .style('pointer-events', 'all');
  
      /* --------- zoom / pan ------------------------------------------- */
      this.zoom = d3.zoom()
        .scaleExtent([0.1, 8])
        .filter(event => {
          // Only allow zoom on wheel events and drag
          return event.type === 'wheel' || event.type === 'mousedown';
        })
        .on('zoom', (event) => {
          // Smooth transition for zoom
          this.viewport.transition()
            .duration(50)
            .attr('transform', event.transform);
        });

      // Initialize zoom behavior on the background rect
      this.bg.call(this.zoom);
  
      /* --------- helpers ---------------------------------------------- */
      this.tree = d3.tree();
      this.diagonal = d3.linkHorizontal().x(d => d.y).y(d => d.x);
      this.root = null;                 // will hold d3-hierarchy root
      this.id = 0;                      // incremental node ids (stable keys)
  
      /* --------- UI adornments ---------------------------------------- */
      this.#addTooltip();
      // this.#addSearchBox(); // Removed to hide the search box
      this.#observeResize();
    }
  
    /* ====================== public API =============================== */
    update(newick) {
      this.root = this.#newickToHierarchy(newick);
      this.#refreshDims();
  
      const layout = this.tree(this.root);       // ‼️ compute x/y here
      const nodes  = layout.descendants();
      const links  = layout.links();
  
      /* -------- links ------------------------------------------------- */
      const linkSel = this.viewport.selectAll('.link').data(links, d => d.target.__id);
      linkSel.exit().remove();
      linkSel.enter()
        .append('path')
        .attr('class', 'link')
        .attr('d', this.diagonal)
        .attr('fill', 'none')
        .attr('stroke-width', this.opts.linkWidth)
        .attr('stroke-opacity', 0.6)
        .merge(linkSel)
        .transition().duration(this.opts.duration)
        .attr('stroke', d => this.opts.colorScheme(d.source.depth))
        .attr('d', this.diagonal);
  
      /* -------- nodes ------------------------------------------------- */
      const nodeSel = this.viewport.selectAll('.node').data(nodes, d => d.__id);
      const nodeEnter = nodeSel.enter()
        .append('g')
        .attr('class', 'node')
        .on('mouseover', (e, d) => this.#tooltipIn(e, d))
        .on('mouseout', () => this.#tooltipOut());
  
      nodeEnter.append('circle')
        .attr('r', this.opts.nodeRadius)
        .attr('stroke', '#fff')
        .attr('stroke-width', 2);
  
      // Only add text labels for leaf nodes (nodes without children)
      nodeEnter.filter(d => !d.children)
        .append('text')
        .attr('dy', '.32em')
        .attr('x', 10)
        .style('text-anchor', 'start')
        .style('font-size', this.opts.fontSize)
        .text(d => d.data.name ?? '');
  
      nodeSel.exit().remove();
      nodeEnter.merge(nodeSel)
        .transition().duration(this.opts.duration)
        .attr('transform', d => `translate(${d.y},${d.x})`)
        .select('circle')
        .attr('fill', d => this.opts.colorScheme(d.depth));
    }
  
    resetZoom() {
      // Smooth transition to reset zoom
      this.svgRoot
        .transition()
        .duration(300)
        .call(this.zoom.transform, d3.zoomIdentity);
    }
    exportSVG(filename = 'phylogenetic_tree.svg') {
      const data = this.svgRoot.node().outerHTML;
      this.#downloadBlob(data, 'image/svg+xml', filename);
    }
    exportPNG(filename = 'phylogenetic_tree.png', scale = 2) {
      const bbox = this.viewport.node().getBBox(); // real content box
      if (!bbox.width || !bbox.height) {
        alert('Nothing to export (tree not rendered yet)');
        return;
      }
      const svgData = new XMLSerializer().serializeToString(this.svgRoot.node());
  
      const canvas = document.createElement('canvas');
      canvas.width  = bbox.width  * scale;
      canvas.height = bbox.height * scale;
  
      const img = new Image();
      img.onload = () => {
        const ctx = canvas.getContext('2d');
        // keep the tree inside the canvas corner
        ctx.translate(-bbox.x * scale, -bbox.y * scale);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        canvas.toBlob(blob => this.#downloadBlob(blob, 'image/png', filename));
      };
      img.src = 'data:image/svg+xml;base64,' + btoa(svgData);
    }
  
    /* ===================== private helpers =========================== */
    #tooltipIn(evt, d) {
      const dist = d.data.length ? `Distance: ${d.data.length.toFixed(3)}<br/>` : '';
      const html = `<strong>${d.data.name || 'Unnamed node'}</strong><br/>
                    ${dist}Depth: ${d.depth}<br/>
                    Descendants: ${d.descendants().length - 1}`;
      this.tooltip.html(html)
        .style('opacity', 1)
        .style('left', `${evt.clientX + 16}px`)
        .style('top',  `${evt.clientY + 8}px`);
    }
    #tooltipOut() { this.tooltip.style('opacity', 0); }
  
    #addTooltip() {
      this.tooltip = d3.select(this.container)
        .append('div')
        .attr('class', 'tooltip pointer-events-none bg-white/95 border border-gray-200 rounded-lg px-3 py-2 shadow-lg text-sm text-gray-700')
        .style('opacity', 0)
        .style('position', 'fixed')
        .style('z-index', 1000);
    }
  
    #addSearchBox() {
      const box = d3.select(this.container)
        .append('input')
        .attr('type', 'text')
        .attr('placeholder', 'Search nodes…')
        .attr('class', 'absolute top-3 right-3 z-20 px-3 py-2 border rounded-md shadow-sm text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white/80 backdrop-blur-md')
        .on('input', (e) => {
          const q = e.target.value.toLowerCase();
          this.viewport.selectAll('.node').style('opacity', d =>
            q ? ((d.data.name || '').toLowerCase().includes(q) ? 1 : 0.25) : 1
          );
        });
    }
  
    #observeResize() {
      new ResizeObserver(() => this.#refreshDims()).observe(this.container);
    }
  
    #refreshDims() {
      const { width, height } = this.#containerBox();
      d3.select(this.container).select('svg')
        .attr('width', width)
        .attr('height', height);

      this.bg
        .attr('width', width)
        .attr('height', height);

      this.tree.size([height - this.opts.margin.top - this.opts.margin.bottom,
                      width - this.opts.margin.left - this.opts.margin.right]);
    }
    #containerBox() {
      const r = this.container.getBoundingClientRect();
      return { width: r.width || 800, height: r.height || 600 };
    }
  
    /* -------- Newick <-> hierarchy ----------------------------------- */
    #newickToHierarchy(str) {
      const parse = (s) => {
        let ancestors=[], tree={}, tokens=s.split(/\s*(;|\(|\)|,|:)\s*/);
        for (let i=0; i<tokens.length; i++) {
          const t=tokens[i];
          switch(t) {
            case '(': {                      // start children
              const parent = tree;
              const child  = {};
              (parent.children || (parent.children = [])).push(child);
              ancestors.push(parent);       // keep parent on the stack
              tree = child;                 // descend
              break;
            }
            case ',': ancestors.at(-1).children.push(tree={}); break;
            case ')': tree=ancestors.pop(); break;
            case ':': break;   // ignore branch length here
            default : if(t && t!==';'){
                        tokens[i-1]===':'?tree.length=parseFloat(t):tree.name=t;
                      }
          }
        }
        return tree;
      };
      const root = d3.hierarchy(parse(str));
      root.eachBefore(d => d.__id = ++this.id);
      return root;
    }
    #hierarchyToNewick(root) {           // simple for re-render toggle
      const walk = n => `${n.children ? '(' + n.children.map(walk).join(',') + ')' : ''}${n.data.name ?? ''}`;
      return walk(root) + ';';
    }
  
    /* -------- misc util ---------------------------------------------- */
    #downloadBlob(data, type, fname) {
      const blob = data instanceof Blob ? data : new Blob([data], { type });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = fname;
      document.body.appendChild(a);
      a.click();
      // Use a short timeout to ensure the download is triggered before cleanup
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 100);
    }
  }
  
  /* ---------- Make globally available so HTML inline code can use it */
  window.PhylogeneticTree = PhylogeneticTree;