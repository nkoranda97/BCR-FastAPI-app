/* ======================================================================
   PhylogeneticTree – v2.3 (Tooltip Event Handler Fix)
   ----------------------------------------------------------------------
   • Responsive: redraws on container resize (ResizeObserver)
   • Smooth zoom / pan + dedicated API for external buttons
   • Collapse / expand on click with visual cue
   • High-DPI PNG / lossless SVG export
   • Initial view focused on root for large trees
   • Layout width adapts to tree depth
   • Layout height adapts to the number of leaf nodes
   • Tooltip event handlers correctly applied to all nodes
   • Includes console.log for tooltip debugging
   =====================================================================*/

class PhylogeneticTree {
  constructor(containerId, opts = {}) {
    /* --------- DOM + basic metrics ---------------------------------- */
    this.container = document.getElementById(containerId);
    if (!this.container) throw new Error(`Container #${containerId} not found`);

    // Initialize selection and last newick storage
    this.selected = new Set();
    this.lastNewick = null;

    // Add toolbar for distance toggle and export
    const toolbar = document.createElement('div');
    toolbar.style.margin = '8px';
    toolbar.innerHTML = `
        <label style="margin-right:12px;">
          <input type="checkbox" id="${containerId}-show-distances"> Show Distances
        </label>
        <button id="${containerId}-export-selected">Export Selected</button>
      `;
    this.container.parentNode.insertBefore(toolbar, this.container);
    document.getElementById(`${containerId}-show-distances`).addEventListener('change', e => {
      this.opts.showDistances = e.target.checked;
      if (this.lastNewick) this.update(this.lastNewick);
    });
    document.getElementById(`${containerId}-export-selected`).addEventListener('click', () => this.exportSelected());

    const defaults = {
      margin: { top: 24, right: 120, bottom: 24, left: 60 },
      nodeRadius: 4.5,
      showDistances: false,
      linkWidth: 1.5,
      fontSize: 12,
      duration: 600,
      zoomTransitionDuration: 50,
      levelSeparation: 80,
      estimatedLeafLabelWidth: 150,
      verticalNodeSeparation: 40,
      colorScheme: d3.scaleOrdinal([
        '#6366f1', '#34d399', '#fbbf24', '#f87171',
        '#60a5fa', '#f472b6', '#a78bfa', '#facc15', '#2dd4bf', '#fb923c'
      ]),
      ...opts
    };
    this.opts = defaults;

    /* --------- SVG scaffold ----------------------------------------- */
    const { width, height } = this.#containerBox();
    this.svgRoot = d3.select(this.container)
      .append('svg')
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
      .classed('select-none', true);

    this.zoomCaptureRect = this.svgRoot.append('rect')
      .attr('width', width)
      .attr('height', height)
      .attr('fill', 'none')
      .style('pointer-events', 'all');

    this.viewport = this.svgRoot.append('g');

    /* --------- zoom / pan ------------------------------------------- */
    this.zoom = d3.zoom()
      .scaleExtent([0.02, 10])
      .filter(event => {
        return event.type === 'wheel' || event.type === 'dblclick' || event.type === 'mousedown';
      })
      .on('zoom', (event) => {
        this.viewport.transition()
          .duration(this.opts.zoomTransitionDuration)
          .attr('transform', event.transform);
      });

    this.svgRoot.call(this.zoom);

    /* --------- helpers ---------------------------------------------- */
    this.tree = d3.tree();
    this.diagonal = d3.linkHorizontal().x(d => d.y).y(d => d.x);
    // Custom orthogonal (right-angled) path generator for phylograms
    this.orthogonal = (d) => {
      const source = d.source;
      const target = d.target;
      return `M${source.y},${source.x}H${target.y}V${target.x}`;
    };
    this.root = null;
    this.id = 0;
    this.leafCount = 0;
    this.initialTransformSet = false;
    this.maxDistance = 0; // Track maximum distance from root

    /* --------- UI adornments ---------------------------------------- */
    this.#addTooltip();
    this.#observeResize();
  }

  /* ====================== public API =============================== */
  update(newick) {
    this.lastNewick = newick;
    this.root = this.#newickToHierarchy(newick);
    if (this.root) {
      this.leafCount = this.root.leaves().length;
      // Calculate distances and set horizontal positions
      this.#calculateDistances();
    } else {
      this.leafCount = 0;
    }

    this.#refreshDims();

    const layout = this.tree(this.root);
    const nodes = layout.descendants();
    const links = layout.links();

    // Apply distance-based positioning after tree layout
    if (this.opts.showDistances && this.maxDistance > 0) {
      this.#applyDistancePositions(nodes);
    }

    /* -------- links ------------------------------------------------- */
    const linkSel = this.viewport.selectAll('.link').data(links, d => d.target.__id);
    linkSel.exit().remove();
    linkSel.enter()
      .append('path')
      .attr('class', 'link')
      .attr('fill', 'none')
      .attr('stroke-width', this.opts.linkWidth)
      .attr('stroke-opacity', 0.6)
      .merge(linkSel)
      .transition().duration(this.opts.duration)
      .attr('stroke', d => this.opts.colorScheme(d.source.depth))
      .attr('d', this.opts.showDistances ? this.orthogonal : this.diagonal);

    /* -------- nodes ------------------------------------------------- */
    const nodeSel = this.viewport.selectAll('.node').data(nodes, d => d.__id);

    const nodeEnter = nodeSel.enter()
      .append('g')
      .attr('class', 'node')
      // Set initial position for new nodes; existing nodes will be transitioned
      .attr('transform', d => {
        // For new nodes, if parent exists, start from parent's position for animation
        const parent = d.parent;
        const startX = parent ? parent.x : d.x;
        const startY = parent ? parent.y : d.y;
        return `translate(${startY},${startX})`;
      })
      .style('opacity', 0); // Start new nodes as transparent

    nodeEnter.append('circle')
      .attr('r', this.opts.nodeRadius);

    nodeEnter.filter(d => !d.children && !d._children)
      .append('text')
      .attr('dy', '.32em')
      .style('font-size', this.opts.fontSize);

    nodeSel.exit()
      .transition().duration(this.opts.duration)
      .attr('transform', d => { // Animate exit to parent's new position
        const parent = d.parent;
        return `translate(${parent ? parent.y : d.y},${parent ? parent.x : d.x})`;
      })
      .style('opacity', 0)
      .remove();

    // Merge enter and update selections
    const nodeUpdate = nodeEnter.merge(nodeSel);

    // Apply transitions to ALL nodes (new and existing)
    nodeUpdate.transition().duration(this.opts.duration)
      .attr('transform', d => `translate(${d.y},${d.x})`)
      .style('opacity', 1);

    nodeUpdate.select('circle')
      .transition().duration(this.opts.duration)
      .attr('fill', d => this.opts.colorScheme(d.depth))
      .attr('stroke', d => d._children ? this.opts.colorScheme(d.depth) : '#fff')
      .attr('stroke-width', d => d._children ? 3 : 2);

    nodeUpdate.select('text')
      .filter(d => !d.children && !d._children) // Only for actual leaf nodes
      .attr('x', this.opts.nodeRadius + 5)
      .style('text-anchor', 'start')
      .text(d => d.data.name ?? '');

    nodeUpdate.select('text')
      .filter(d => d.children || d._children) // Clear text for internal nodes
      .text('');

    // ATTACH EVENT HANDLERS to ALL nodes (new and existing)
    nodeUpdate
      .on('mouseover', (e, d) => this.#tooltipIn(e, d))
      .on('mouseout', () => this.#tooltipOut())
      .on('click', (e, d) => {
        if (e.shiftKey && !d.children && !d._children) {
          // select leaf on shift-click
          const id = d.__id;
          if (this.selected.has(id)) this.selected.delete(id);
          else this.selected.add(id);
          d3.select(e.currentTarget).select('circle')
            .attr('stroke', this.selected.has(id) ? 'red' : (d._children ? this.opts.colorScheme(d.depth) : '#fff'))
            .attr('stroke-width', this.selected.has(id) ? 4 : (d._children ? 3 : 2));
        } else {
          this.#toggleNodeCollapse(d);
        }
      });

    if (!this.initialTransformSet && this.root) {
      this.#setInitialView();
      this.initialTransformSet = true;
    }
  }

  #toggleNodeCollapse(d) {
    const isExpanding = d._children; // True if we are about to expand

    if (d.children) {
      d._children = d.children;
      d.children = null;
    } else if (d._children) {
      d.children = d._children;
      d._children = null;
    } else {
      return; // Node is a leaf, nothing to collapse/expand
    }

    if (this.root) {
      this.leafCount = this.root.leaves().length;
      // Calculate distances and set horizontal positions  
      this.#calculateDistances();
    }
    this.#refreshDims();

    let nodes, links;
    if (this.opts.showDistances && this.maxDistance > 0) {
      // Use custom phylogram layout
      ({ nodes, links } = this.#createPhylogramLayout());
    } else {
      // Use standard d3.tree layout
      const layout = this.tree(this.root);
      nodes = layout.descendants();
      links = layout.links();
    }

    // Clicked node's current position (will be the source/target for animations)
    const sourcePoint = { x: d.x, y: d.y, depth: d.depth };


    const linkSel = this.viewport.selectAll('.link').data(links, l => l.target.__id);

    linkSel.exit()
      .transition().duration(this.opts.duration)
      .attr('d', this.diagonal({ source: sourcePoint, target: sourcePoint }))
      .remove();

    linkSel.enter()
      .append('path')
      .attr('class', 'link')
      .attr('d', this.diagonal({ source: sourcePoint, target: sourcePoint }))
      .attr('fill', 'none')
      .attr('stroke-width', this.opts.linkWidth)
      .attr('stroke-opacity', 0)
      .merge(linkSel)
      .transition().duration(this.opts.duration)
      .attr('stroke', l_d => this.opts.colorScheme(l_d.source.depth))
      .attr('d', this.opts.showDistances ? this.orthogonal : this.diagonal)
      .attr('stroke-opacity', 0.6);


    const nodeSel = this.viewport.selectAll('.node').data(nodes, n_d => n_d.__id);

    nodeSel.exit()
      .transition().duration(this.opts.duration)
      .attr('transform', `translate(${sourcePoint.y},${sourcePoint.x})`)
      .style('opacity', 0)
      .remove();

    const nodeEnter = nodeSel.enter()
      .append('g')
      .attr('class', 'node')
      .attr('transform', `translate(${sourcePoint.y},${sourcePoint.x})`)
      .style('opacity', 0);

    nodeEnter.append('circle')
      .attr('r', this.opts.nodeRadius);

    nodeEnter.filter(n_d => !n_d.children && !n_d._children)
      .append('text')
      .attr('dy', '.32em')
      .style('font-size', this.opts.fontSize);

    const nodeUpdate = nodeEnter.merge(nodeSel);

    nodeUpdate.transition().duration(this.opts.duration)
      .attr('transform', n_d => `translate(${n_d.y},${n_d.x})`)
      .style('opacity', 1);

    nodeUpdate.select('circle')
      .transition().duration(this.opts.duration)
      .attr('fill', n_d => this.opts.colorScheme(n_d.depth))
      .attr('stroke', n_d => n_d._children ? this.opts.colorScheme(n_d.depth) : '#fff')
      .attr('stroke-width', n_d => n_d._children ? 3 : 2);

    nodeUpdate.select('text')
      .filter(n_d => !n_d.children && !n_d._children)
      .attr('x', this.opts.nodeRadius + 5)
      .style('text-anchor', 'start')
      .text(n_d => n_d.data.name ?? '');

    nodeUpdate.select('text')
      .filter(n_d => n_d.children || n_d._children)
      .text('');

    // RE-ATTACH EVENT HANDLERS to ensure they are on all nodes after update
    nodeUpdate
      .on('mouseover', (e, n_d) => this.#tooltipIn(e, n_d))
      .on('mouseout', () => this.#tooltipOut())
      .on('click', (e, n_d) => this.#toggleNodeCollapse(n_d)); // Re-bind click
  }


  resetZoom() {
    if (this.root) {
      this.#setInitialView();
    }
  }

  exportSVG(filename = 'phylogenetic_tree.svg') {
    const svgNode = this.svgRoot.node().cloneNode(true);
    d3.select(svgNode).select('.phylotree-tooltip').remove();

    const styleEl = document.createElement('style');
    let cssText = `
          .link { fill: none; stroke-opacity: 0.6; stroke-width: ${this.opts.linkWidth}px; }
          .node circle { stroke-width: 2px; }
          .node text { font-size: ${this.opts.fontSize}px; text-anchor: start; }
          .select-none { user-select: none; }
      `;
    for (const sheet of document.styleSheets) {
      try {
        if (sheet.cssRules) {
          for (const rule of sheet.cssRules) {
            if (!rule.selectorText || !rule.selectorText.includes('tooltip')) {
              cssText += rule.cssText + '\n';
            }
          }
        }
      } catch (e) {
        console.warn("Cannot access stylesheet for SVG export: " + sheet.href, e);
      }
    }
    styleEl.textContent = cssText;
    svgNode.insertBefore(styleEl, svgNode.firstChild);

    const data = new XMLSerializer().serializeToString(svgNode);
    this.#downloadBlob(data, 'image/svg+xml', filename);
  }

  exportPNG(filename = 'phylogenetic_tree.png', scale = 2) {
    if (!this.root) {
      this.#showTemporaryMessage('Nothing to export (tree not rendered yet)');
      return;
    }
    const contentBBox = this.viewport.node().getBBox();
    if (!contentBBox.width || !contentBBox.height) {
      this.#showTemporaryMessage('Content bounding box is invalid for export.');
      return;
    }

    const svgNodeClone = this.svgRoot.node().cloneNode(true);
    const clonedSvg = d3.select(svgNodeClone);
    clonedSvg.select('.phylotree-tooltip').remove();

    clonedSvg.attr('width', contentBBox.width)
      .attr('height', contentBBox.height)
      .attr('viewBox', `${contentBBox.x} ${contentBBox.y} ${contentBBox.width} ${contentBBox.height}`);

    const styleEl = document.createElement('style');
    let cssText = `
          .link { fill: none; stroke-opacity: 0.6; stroke-width: ${this.opts.linkWidth}px; }
          .node circle { stroke-width: 2px; }
          .node text { font-size: ${this.opts.fontSize}px; text-anchor: start; }
          .select-none { user-select: none; }
      `;
    for (const sheet of document.styleSheets) {
      try {
        if (sheet.cssRules) {
          for (const rule of sheet.cssRules) {
            if (!rule.selectorText || !rule.selectorText.includes('tooltip')) {
              cssText += rule.cssText + '\n';
            }
          }
        }
      } catch (e) { /* ignore */ }
    }
    styleEl.textContent = cssText;
    clonedSvg.node().insertBefore(styleEl, clonedSvg.node().firstChild);

    const svgData = new XMLSerializer().serializeToString(clonedSvg.node());

    const canvas = document.createElement('canvas');
    canvas.width = contentBBox.width * scale;
    canvas.height = contentBBox.height * scale;
    const ctx = canvas.getContext('2d');
    ctx.scale(scale, scale);

    const img = new Image();
    img.onload = () => {
      ctx.drawImage(img, 0, 0);
      canvas.toBlob(blob => this.#downloadBlob(blob, 'image/png', filename));
    };
    img.onerror = (e) => {
      console.error("Error loading SVG image for PNG export:", e);
      this.#showTemporaryMessage('Error generating PNG.');
    }
    img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)));
  }

  exportSelected(filename = 'phylogenetic_tree_selected.svg') {
    if (this.selected.size === 0) {
      this.#showTemporaryMessage('No nodes selected for export.');
      return;
    }

    const selectedNodes = this.root.descendants().filter(n => this.selected.has(n.__id));
    const selectedLinks = this.root.links().filter(l => this.selected.has(l.target.__id));

    const exportRoot = d3.hierarchy({ children: selectedNodes });
    exportRoot.each(d => {
      d.parent = exportRoot;
      d.depth = d.ancestors().length - 1;
    });

    const layout = this.tree(exportRoot);
    const nodes = layout.descendants();
    const links = layout.links();

    const svgNode = d3.create("svg");
    const g = svgNode.append("g");

    g.selectAll(".link")
      .data(links)
      .enter().append("path")
      .attr("class", "link")
      .attr("fill", "none")
      .attr("stroke-width", this.opts.linkWidth)
      .attr("stroke-opacity", 0.6)
      .attr("stroke", d => this.opts.colorScheme(d.source.depth))
      .attr("d", this.diagonal);

    const nodeEnter = g.selectAll(".node")
      .data(nodes)
      .enter().append("g")
      .attr("class", "node")
      .attr("transform", d => `translate(${d.y},${d.x})`);

    nodeEnter.append("circle")
      .attr("r", this.opts.nodeRadius)
      .attr("fill", d => this.opts.colorScheme(d.depth))
      .attr("stroke", d => d._children ? this.opts.colorScheme(d.depth) : "#fff")
      .attr("stroke-width", d => d._children ? 3 : 2);

    nodeEnter.filter(d => !d.children && !d._children)
      .append("text")
      .attr("dy", ".32em")
      .style("font-size", this.opts.fontSize)
      .attr("x", this.opts.nodeRadius + 5)
      .style("text-anchor", "start")
      .text(d => d.data.name ?? "");

    const styleEl = document.createElement('style');
    let cssText = `
          .link { fill: none; stroke-opacity: 0.6; stroke-width: ${this.opts.linkWidth}px; }
          .node circle { stroke-width: 2px; }
          .node text { font-size: ${this.opts.fontSize}px; text-anchor: start; }
          .select-none { user-select: none; }
      `;
    for (const sheet of document.styleSheets) {
      try {
        if (sheet.cssRules) {
          for (const rule of sheet.cssRules) {
            if (!rule.selectorText || !rule.selectorText.includes('tooltip')) {
              cssText += rule.cssText + '\n';
            }
          }
        }
      } catch (e) {
        console.warn("Cannot access stylesheet for SVG export: " + sheet.href, e);
      }
    }
    styleEl.textContent = cssText;
    svgNode.insertBefore(styleEl, svgNode.firstChild);

    const data = new XMLSerializer().serializeToString(svgNode.node());
    this.#downloadBlob(data, 'image/svg+xml', filename);
  }

  /* ===================== private helpers =========================== */
  #setInitialView() {
    if (!this.root || this.root.x === undefined || this.root.y === undefined) return;

    const { width: svgWidth, height: svgHeight } = this.#containerBox();
    let initialScale = 1.0;

    const rootLayoutY = this.root.y;
    const rootLayoutX = this.root.x;

    const targetSvgX = this.opts.margin.left;
    const targetSvgY = svgHeight / 2;

    const tx = targetSvgX - (rootLayoutY * initialScale);
    const ty = targetSvgY - (rootLayoutX * initialScale);

    const initialTransform = d3.zoomIdentity.translate(tx, ty).scale(initialScale);
    this.svgRoot.call(this.zoom.transform, initialTransform);
  }

  #tooltipIn(evt, d) {
    console.log('Tooltip In:', d.data.name || 'Unnamed node', d); // For debugging
    const dist = d.data.length ? `Distance: ${d.data.length.toFixed(3)}<br/>` : '';
    const name = d.data.name || 'Unnamed node';
    const childrenCount = d.children ? d.children.length : (d._children ? d._children.length : 0);
    const descendantsCount = d.descendants().length - 1;

    let html = `<strong>${name}</strong><br/>`;
    if (dist) html += dist;
    html += `Depth: ${d.depth}<br/>`;
    if (childrenCount > 0) {
      html += `Direct Children: ${childrenCount}<br/>`;
    }
    html += `Total Descendants: ${descendantsCount}`;
    if (d._children) {
      html += `<br/><em>(Collapsed - click to expand)</em>`;
    } else if (d.children && d.children.length > 0) {
      html += `<br/><em>(Click to collapse)</em>`;
    }

    this.tooltip.html(html)
      .style('opacity', 1)
      .style('left', `${evt.clientX + 16}px`)
      .style('top', `${evt.clientY + 8}px`);
  }
  #tooltipOut() {
    console.log('Tooltip Out'); // For debugging
    this.tooltip.style('opacity', 0);
  }

  #addTooltip() {
    this.tooltip = d3.select('body')
      .append('div')
      .attr('class', 'phylotree-tooltip pointer-events-none')
      .style('opacity', 0)
      .style('position', 'fixed')
      .style('z-index', 2000)
      .style('background-color', 'rgba(255, 255, 255, 0.95)')
      .style('border', '1px solid #ccc')
      .style('border-radius', '4px')
      .style('padding', '8px 12px')
      .style('box-shadow', '0 2px 5px rgba(0,0,0,0.1)');
  }

  #observeResize() {
    new ResizeObserver(() => {
      this.#refreshDims();
      if (this.initialTransformSet && this.root) {
        this.#setInitialView();
      } else if (this.root) {
        this.#setInitialView();
        this.initialTransformSet = true;
      }
    }).observe(this.container);
  }

  #refreshDims() {
    const { width, height: containerHeight } = this.#containerBox();
    // Allow vertical scrolling if tree exceeds container height
    this.container.style.overflowY = 'auto';

    // Use fixed vertical separation, don't constrain by container height
    const vSep = this.opts.verticalNodeSeparation;

    // Calculate total height needed for all leaves
    const desiredTreeHeight = this.root ? this.leafCount * vSep : 0;
    const minHeight = Math.max(containerHeight, this.opts.fontSize * 5);
    const layoutHeight = Math.max(desiredTreeHeight, minHeight);

    // Total SVG height includes margins
    const totalHeight = layoutHeight + this.opts.margin.top + this.opts.margin.bottom;

    // Update SVG and zoom rect dims and viewBox
    this.svgRoot
      .attr('width', width)
      .attr('height', totalHeight)
      .attr('viewBox', `0 0 ${width} ${totalHeight}`);

    this.zoomCaptureRect
      .attr('width', width)
      .attr('height', totalHeight);

    // Compute horizontal layout
    const containerHorizontalSpace = width - this.opts.margin.left - this.opts.margin.right;
    let layoutWidth = containerHorizontalSpace;
    if (this.root) {
      const maxDepth = this.root.height || 0;
      layoutWidth = Math.max(containerHorizontalSpace, maxDepth * this.opts.levelSeparation + this.opts.estimatedLeafLabelWidth + this.opts.nodeRadius * 2 + this.opts.margin.right);
    }
    layoutWidth = Math.max(layoutWidth, this.opts.levelSeparation * 2);
    // Apply tree size
    this.tree.size([Math.max(1, layoutHeight), Math.max(1, layoutWidth)]);
  }

  #containerBox() {
    const r = this.container.getBoundingClientRect();
    const containerWidth = r.width || parseInt(this.container.style.width) || 800;
    const containerHeight = r.height || parseInt(this.container.style.height) || 600;
    return { width: containerWidth, height: containerHeight };
  }

  #newickToHierarchy(str) {
    if (!str || typeof str !== 'string' || str.trim() === '') {
      console.error("Invalid Newick string provided.");
      this.#showTemporaryMessage("Invalid Newick string.");
      return null;
    }
    const parse = (s) => {
      let ancestors = [], tree = {}, tokens = s.split(/\s*(;|\(|\)|,|:)\s*/);
      for (let i = 0; i < tokens.length; i++) {
        const t = tokens[i];
        switch (t) {
          case '(': {
            const parent = tree;
            const child = {};
            (parent.children || (parent.children = [])).push(child);
            ancestors.push(parent);
            tree = child;
            break;
          }
          case ',': ancestors.at(-1).children.push(tree = {}); break;
          case ')': tree = ancestors.pop(); break;
          case ':': break;
          default: if (t && t !== ';') {
            tokens[i - 1] === ':' ? tree.length = parseFloat(t) : tree.name = t;
          }
        }
      }
      return tree;
    };
    try {
      const hierarchyRoot = d3.hierarchy(parse(str));
      hierarchyRoot.eachBefore(d => {
        d.__id = ++this.id;
        if (d.children && d.children.length === 0) d.children = null;
      });
      return hierarchyRoot;
    } catch (error) {
      console.error("Error parsing Newick string:", error);
      this.#showTemporaryMessage("Error parsing Newick. Check format.");
      return null;
    }
  }

  #hierarchyToNewick(rootNode) {
    if (!rootNode) return ';';
    const walk = (n) => {
      let str = '';
      const childrenToWalk = n.children || n._children;

      if (childrenToWalk && childrenToWalk.length > 0) {
        str += '(' + childrenToWalk.map(walk).join(',') + ')';
      }
      str += (n.data.name ?? '');
      if (n.data.length !== undefined) {
        str += ':' + n.data.length;
      }
      return str;
    };
    return walk(rootNode) + ';';
  }

  #downloadBlob(data, type, fname) {
    const blob = data instanceof Blob ? data : new Blob([data], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 100);
  }

  #showTemporaryMessage(message, duration = 3000) {
    d3.select(this.container).select('.phylotree-message').remove();

    const msgDiv = d3.select(this.container)
      .append('div')
      .attr('class', 'phylotree-message')
      .style('position', 'absolute')
      .style('top', '10px')
      .style('left', '50%')
      .style('transform', 'translateX(-50%)')
      .style('padding', '10px 20px')
      .style('background-color', 'rgba(220, 53, 69, 0.85)')
      .style('color', 'white')
      .style('border-radius', '5px')
      .style('z-index', '2000')
      .style('opacity', '0')
      .style('transition', 'opacity 0.3s ease-in-out');

    msgDiv.text(message)
      .style('opacity', '1')
      .transition()
      .delay(duration)
      .duration(500)
      .style('opacity', '0')
      .on('end', function () { d3.select(this).remove(); });
  }

  // Calculate cumulative distances from root and set horizontal positions
  #calculateDistances() {
    if (!this.root) return;

    // First pass: calculate cumulative distance from root
    this.root.each(d => {
      d.distanceFromRoot = 0;
      if (d.parent) {
        d.distanceFromRoot = d.parent.distanceFromRoot + (d.data.length || 0);
      }
    });

    // Find maximum distance for scaling
    this.maxDistance = Math.max(...this.root.descendants().map(d => d.distanceFromRoot));
  }

  // Apply distance-based horizontal positioning to nodes
  #applyDistancePositions(nodes) {
    if (!this.maxDistance || this.maxDistance === 0) return;

    const { width } = this.#containerBox();
    const availableWidth = width - this.opts.margin.left - this.opts.margin.right - this.opts.estimatedLeafLabelWidth;

    nodes.forEach(d => {
      d.y = this.opts.margin.left + (d.distanceFromRoot / this.maxDistance) * availableWidth;
    });
  }

  // Create a phylogram layout with distance-based positioning
  #createPhylogramLayout() {
    if (!this.root) return { nodes: [], links: [] };

    const { width, height } = this.#containerBox();
    const availableWidth = width - this.opts.margin.left - this.opts.margin.right - this.opts.estimatedLeafLabelWidth;
    const availableHeight = height - this.opts.margin.top - this.opts.margin.bottom;

    const leaves = this.root.leaves();
    const leafSpacing = availableHeight / Math.max(1, leaves.length - 1);

    // Assign vertical positions to leaves
    leaves.forEach((leaf, i) => {
      leaf.x = this.opts.margin.top + (i * leafSpacing);
      leaf.y = this.opts.margin.left + (leaf.distanceFromRoot / this.maxDistance) * availableWidth;
    });

    // Position internal nodes
    this.root.eachAfter(d => {
      if (d.children) {
        // Position at average of children's y positions
        d.x = d3.mean(d.children, child => child.x);
        d.y = this.opts.margin.left + (d.distanceFromRoot / this.maxDistance) * availableWidth;
      }
    });

    const nodes = this.root.descendants();
    const links = this.root.links();

    return { nodes, links };
  }

  // Export names of selected leaf nodes as text file
  exportSelected() {
    if (!this.root) return;
    const names = [];
    this.root.leaves().forEach(d => {
      if (this.selected.has(d.__id)) names.push(d.data.name || '');
    });
    if (names.length === 0) {
      this.#showTemporaryMessage('No leaves selected');
      return;
    }
    const content = names.join('\n');
    this.#downloadBlob(content, 'text/plain', 'selected_leaves.txt');
  }
}

window.PhylogeneticTree = PhylogeneticTree;
