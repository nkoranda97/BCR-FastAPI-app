// --------------------------------------------------
// FASTA → array<{name, seq}>
// --------------------------------------------------
function parseFASTA(txt) {
  if (!txt) return [];
  const records = [];
  let header = null, chunk = [];
  txt.split(/\r?\n/).forEach(line => {
    line = line.trim();
    if (!line) return;
    if (line.startsWith('>')) {
      if (header !== null) {
        records.push({ name: header, seq: chunk.join('').toUpperCase().replace(/[^A-Z\-*\.]/g, '') });
      }
      header = line.slice(1).trim();
      chunk = [];
    } else {
      chunk.push(line);
    }
  });
  if (header !== null) {
    records.push({ name: header, seq: chunk.join('').toUpperCase().replace(/[^A-Z\-*\.]/g, '') });
  }
  return records;
}

class MSAViewer {
  constructor(containerId, sequences, regionBlocks = null) {
    this.container = document.getElementById(containerId);
    this.seqs = sequences ?? [];
    this.filteredSeqs = this.seqs; // For search/filter functionality
    this.zoom = 1;
    this.baseSize = 14; // px – base font size for sequence characters, will scale with zoom
    this.nameColWidth = this._calculateNameColWidth(); // Dynamic width based on sequence names
    this.regionBlocks = regionBlocks;
    this.showPositionRuler = true;
    this.compactView = false; // Show only variable positions
    this.highlightMismatches = true; // Toggle for germline mismatch highlighting
    this.showAminoAcidColors = true; // Toggle for amino acid color scheme
    this.selectedColumns = new Set(); // Track selected positions
    this.searchTerm = '';
    // Amino acid color scheme with additional properties
    this.aaColors = {
      'A': 'bg-blue-100', 'C': 'bg-yellow-100', 'D': 'bg-red-100', 'E': 'bg-red-100',
      'F': 'bg-blue-100', 'G': 'bg-green-100', 'H': 'bg-purple-100', 'I': 'bg-blue-100',
      'K': 'bg-purple-100', 'L': 'bg-blue-100', 'M': 'bg-blue-100', 'N': 'bg-green-100',
      'P': 'bg-yellow-100', 'Q': 'bg-green-100', 'R': 'bg-purple-100', 'S': 'bg-green-100',
      'T': 'bg-green-100', 'V': 'bg-blue-100', 'W': 'bg-blue-100', 'Y': 'bg-green-100',
      '-': 'bg-gray-100', '*': 'bg-gray-100', '.': 'bg-gray-100'
    };

    if (!this.container) { console.error(`[MSAViewer] container #${containerId} missing`); return; }

    this._addStyles(); // Add custom CSS
    this.container.innerHTML = ''; // Clear container

    // Enhanced Toolbar with search and additional controls
    this.toolbar = document.createElement('div');
    this.toolbar.className = 'msa-viewer-toolbar flex flex-wrap items-center justify-between gap-2 p-3 bg-slate-50 border-b border-slate-200 sticky top-0 z-20';
    this.toolbar.innerHTML = `
      <div class="flex items-center gap-2">
        <input type="text" placeholder="Search sequences..." 
               class="px-3 py-1 border border-slate-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500" 
               data-action="search" style="width: 200px;">
        <span class="text-xs text-slate-600" data-role="seq-count"></span>
      </div>
      <div class="flex items-center gap-2">
        <button class="px-2 py-1 rounded bg-slate-300 text-sm hover:bg-slate-400 transition-colors" 
                data-action="toggle-highlighting" title="Toggle germline mismatch highlighting">Show Mismatches</button>
        <button class="px-2 py-1 rounded bg-slate-300 text-sm hover:bg-slate-400 transition-colors" 
                data-action="toggle-coloring" title="Toggle amino acid color scheme">Color AA</button>
        <div class="border-l border-slate-300 pl-2 ml-2"></div>
        <button class="px-2 py-1 rounded bg-slate-200 text-sm font-bold hover:bg-slate-300 transition-colors" 
                data-action="zoom-in" title="Zoom in">+</button>
        <button class="px-2 py-1 rounded bg-slate-200 text-sm font-bold hover:bg-slate-300 transition-colors" 
                data-action="zoom-out" title="Zoom out">−</button>
        <button class="px-2 py-1 rounded bg-slate-200 text-sm font-bold hover:bg-slate-300 transition-colors" 
                data-action="reset" title="Reset zoom">Reset</button>
      </div>
    `;
    this.container.appendChild(this.toolbar);

    // Scroll container for alignment rows
    this.scrollArea = document.createElement('div');
    // overflow-auto will provide scrollbars (vertical and horizontal) if content overflows
    this.scrollArea.className = 'overflow-auto';
    // Set a default max-height. This allows vertical scrolling if rows exceed this height.
    this.scrollArea.style.maxHeight = 'calc(100vh - 250px)'; // Default, adjust as needed for your page layout
    // If the parent card has a specific max-height (like from Tailwind's max-h-96), use that.
    if (this.container.closest('.max-h-96')) {
      this.scrollArea.style.maxHeight = '384px'; // Tailwind max-h-96 is 24rem = 384px
    } else if (this.container.closest('.max-h-screen-sm')) {
      this.scrollArea.style.maxHeight = 'calc(100vh - 150px)';
    }
    this.container.appendChild(this.scrollArea);

    // Wrapper that grows horizontally (so table can be wider than viewport)
    this.rowsWrap = document.createElement('div');
    this.rowsWrap.className = 'inline-block min-w-full';
    this.scrollArea.appendChild(this.rowsWrap);

    this._bindControls();
    this._filterSequences(); // Initialize filtered sequences
    this.render();
    this._addStyles(); // Apply custom styles
  }

  _bindControls() {
    // Toolbar event handling
    this.toolbar.addEventListener('click', e => {
      const act = e.target.closest('button')?.dataset.action;
      if (!act) return;
      if (act === 'zoom-in') this._setZoom(this.zoom * 1.25);
      if (act === 'zoom-out') this._setZoom(this.zoom / 1.25);
      if (act === 'reset') this._setZoom(1);
      if (act === 'toggle-highlighting') this._toggleHighlighting();
      if (act === 'toggle-coloring') this._toggleColoring();
    });

    // Search functionality
    const searchInput = this.toolbar.querySelector('[data-action="search"]');
    if (searchInput) {
      searchInput.addEventListener('input', e => {
        this.searchTerm = e.target.value.toLowerCase();
        this._filterSequences();
        this.render();
      });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', e => {
      if (e.target.tagName === 'INPUT') return; // Don't interfere with input fields
      if (e.ctrlKey || e.metaKey) {
        switch (e.key) {
          case '=':
          case '+':
            e.preventDefault();
            this._setZoom(this.zoom * 1.25);
            break;
          case '-':
            e.preventDefault();
            this._setZoom(this.zoom / 1.25);
            break;
          case '0':
            e.preventDefault();
            this._setZoom(1);
            break;
        }
      }
    });

    // Column selection
    this.container.addEventListener('click', e => {
      if (e.target.classList.contains('msa-cell') && !e.target.closest('.msa-consensus-row, .msa-region-bar-row')) {
        const cellIndex = Array.from(e.target.parentNode.children).indexOf(e.target);
        this._toggleColumnSelection(cellIndex);
      }
    });
  }

  _setZoom(z) {
    this.zoom = Math.min(Math.max(z, 0.25), 5);
    const cellWidth = this.baseSize * this.zoom;
    const fontSize = this.baseSize * this.zoom;

    // Update font sizes
    this.rowsWrap.querySelectorAll('.msa-name, .msa-seq-char-wrapper').forEach(el => {
      el.style.fontSize = `${fontSize}px`;
    });

    // Update cell widths (no padding, cleaner alignment)
    this.rowsWrap.querySelectorAll('.msa-cell').forEach(cell => {
      cell.style.width = `${cellWidth}px`;
      cell.style.height = `${cellWidth}px`;
    });

    // Update region segment widths
    this.rowsWrap.querySelectorAll('.msa-region-segment').forEach(segment => {
      const len = parseInt(segment.dataset.length, 10);
      segment.style.width = `${len * cellWidth}px`;
    });
  }

  _consensus(sequences) { // Pass sequences to avoid using this.seqs if it's filtered
    if (!sequences || !sequences.length) return '';
    const len = Math.max(...sequences.map(s => s.seq.length));
    let out = '';
    for (let i = 0; i < len; i++) {
      const counts = new Map();
      sequences.forEach(({ seq }) => {
        const aa = seq[i] ?? '-';
        counts.set(aa, (counts.get(aa) || 0) + 1);
      });
      let bestAA = '-', bestCt = 0;
      counts.forEach((ct, aa) => {
        if (ct > bestCt) { bestCt = ct; bestAA = aa; }
      });
      out += bestAA;
    }
    return out;
  }

  _rowDOM(name, seq, { isConsensus = false, isGermline = false, germlineSeq = null } = {}) {
    const row = document.createElement('div');
    row.className = 'flex items-stretch border-b border-slate-100';

    // Name column with fixed width for alignment
    const nameCol = document.createElement('div');
    nameCol.className = 'msa-name flex items-center justify-end pr-3 text-right font-mono text-slate-700 border-r border-slate-300 bg-white sticky left-0 z-15';
    nameCol.style.width = `${this.nameColWidth}px`;
    nameCol.style.minWidth = `${this.nameColWidth}px`;
    nameCol.style.fontSize = `${this.baseSize * this.zoom}px`;

    if (isGermline || isConsensus) {
      nameCol.classList.add('font-bold');
    } else {
      nameCol.classList.add('font-semibold');
    }
    nameCol.textContent = name;
    row.appendChild(nameCol);

    // Sequence container
    const seqDiv = document.createElement('div');
    seqDiv.className = 'msa-seq-char-wrapper flex';
    seqDiv.style.fontSize = `${this.baseSize * this.zoom}px`;

    const cellWidth = this.baseSize * this.zoom;
    [...seq].forEach((aa, idx) => {
      const span = document.createElement('span');
      span.className = 'msa-cell flex items-center justify-center border-r border-slate-200 cursor-pointer';
      span.style.width = `${cellWidth}px`;
      span.style.height = `${cellWidth}px`;
      span.textContent = aa;

      // Add tooltip showing sequence name and position
      span.title = `${name} - Position ${idx + 1}`;

      // Apply amino acid colors conditionally
      if (this.showAminoAcidColors) {
        const colorClass = this.aaColors[aa] || 'bg-gray-100';
        span.classList.add(colorClass);
      } else {
        span.classList.add('bg-white');
      }

      // Bold for special sequences
      if (isConsensus || isGermline) {
        span.classList.add('font-bold');
      }

      // Highlight mismatches
      if (this.highlightMismatches && !isConsensus && !isGermline && germlineSeq && aa !== germlineSeq[idx] && aa !== '-' && germlineSeq[idx] !== '-') {
        span.classList.add('bg-yellow-200', 'font-bold', 'ring-1', 'ring-yellow-400');
      }

      seqDiv.appendChild(span);
    });
    row.appendChild(seqDiv);

    // Special styling for consensus
    if (isConsensus) {
      row.classList.add('msa-consensus-row', 'bg-slate-100', 'sticky', 'top-0', 'z-10');
      nameCol.classList.remove('bg-white');
      nameCol.classList.add('bg-slate-100');
    }

    // Special styling for germline
    if (isGermline) {
      row.classList.add('bg-sky-50');
      nameCol.classList.remove('bg-white');
      nameCol.classList.add('bg-sky-50');
    }

    return row;
  }

  _regionBarDOM(seqLen) {
    if (!this.regionBlocks || !this.regionBlocks.length) return null;

    const row = document.createElement('div');
    row.className = 'msa-region-bar-row flex items-stretch border-b-2 border-slate-300 bg-slate-200 text-xs font-semibold sticky top-0 z-20';

    // Name column with same fixed width
    const nameCol = document.createElement('div');
    nameCol.className = 'msa-name flex items-center justify-end pr-3 text-right font-mono font-bold text-slate-700 border-r-2 border-slate-300 bg-slate-200 sticky left-0 z-25';
    nameCol.style.width = `${this.nameColWidth}px`;
    nameCol.style.minWidth = `${this.nameColWidth}px`;
    nameCol.style.fontSize = `${this.baseSize * this.zoom}px`;
    nameCol.textContent = 'Regions';
    row.appendChild(nameCol);

    // Regions container
    const regionsContainer = document.createElement('div');
    regionsContainer.className = 'flex items-stretch';

    const cellWidth = this.baseSize * this.zoom;
    let currentPos = 0;

    this.regionBlocks.forEach(([regionName, start, end]) => {
      const regionStart = start - 1; // Convert to 0-based indexing
      const regionEnd = end - 1;
      const regionLen = regionEnd - regionStart + 1;

      // Add gap before region if needed
      if (regionStart > currentPos) {
        const gapLen = regionStart - currentPos;
        const gapSpan = document.createElement('span');
        gapSpan.className = 'msa-region-segment flex items-center justify-center';
        gapSpan.dataset.length = gapLen;
        gapSpan.style.width = `${gapLen * cellWidth}px`;
        gapSpan.innerHTML = '&nbsp;';
        regionsContainer.appendChild(gapSpan);
      }

      // Add region segment
      const segmentSpan = document.createElement('span');
      segmentSpan.className = 'msa-region-segment flex items-center justify-center border-r border-slate-400 px-1 bg-slate-300';
      segmentSpan.dataset.length = regionLen;
      segmentSpan.style.width = `${regionLen * cellWidth}px`;
      segmentSpan.textContent = regionName;
      regionsContainer.appendChild(segmentSpan);

      currentPos = regionEnd + 1;
    });

    // Fill remaining space if needed
    if (currentPos < seqLen) {
      const fillLen = seqLen - currentPos;
      const fillSpan = document.createElement('span');
      fillSpan.className = 'msa-region-segment flex items-center justify-center';
      fillSpan.dataset.length = fillLen;
      fillSpan.style.width = `${fillLen * cellWidth}px`;
      fillSpan.innerHTML = '&nbsp;';
      regionsContainer.appendChild(fillSpan);
    }

    row.appendChild(regionsContainer);
    return row;
  }

  _positionRulerDOM(seqLen) {
    if (!this.showPositionRuler) return null;

    const row = document.createElement('div');
    row.className = 'msa-position-ruler-row flex items-stretch border-b border-slate-200 bg-slate-50 text-xs sticky top-0 z-15';

    // Name column
    const nameCol = document.createElement('div');
    nameCol.className = 'msa-name flex items-center justify-end pr-3 text-right font-mono text-slate-600 border-r border-slate-300 bg-slate-50 sticky left-0 z-20';
    nameCol.style.width = `${this.nameColWidth}px`;
    nameCol.style.minWidth = `${this.nameColWidth}px`;
    nameCol.style.fontSize = `${this.baseSize * this.zoom}px`;
    nameCol.textContent = 'Position';
    row.appendChild(nameCol);

    // Position numbers
    const positionsDiv = document.createElement('div');
    positionsDiv.className = 'flex';

    const cellWidth = this.baseSize * this.zoom;
    for (let i = 0; i < seqLen; i++) {
      const span = document.createElement('span');
      span.className = 'msa-cell flex items-center justify-center text-slate-500 border-r border-slate-200';
      span.style.width = `${cellWidth}px`;
      span.style.height = `${cellWidth}px`;
      span.style.fontSize = `${Math.max(8, this.baseSize * this.zoom * 0.7)}px`;

      // Show position number every 10 positions or if zoomed in enough
      if ((i + 1) % 10 === 0 || this.zoom > 1.5) {
        span.textContent = i + 1;
      } else if ((i + 1) % 5 === 0) {
        span.textContent = '·';
      }

      positionsDiv.appendChild(span);
    }

    row.appendChild(positionsDiv);
    return row;
  }

  _filterSequences() {
    if (!this.searchTerm) {
      this.filteredSeqs = this.seqs;
    } else {
      this.filteredSeqs = this.seqs.filter(seq =>
        seq.name.toLowerCase().includes(this.searchTerm)
      );
    }
    // Recalculate name column width for filtered sequences
    this.nameColWidth = this._calculateNameColWidthForSequences(this.filteredSeqs);
    this._updateSequenceCount();
  }

  _updateSequenceCount() {
    const countEl = this.toolbar.querySelector('[data-role="seq-count"]');
    if (countEl) {
      const total = this.seqs.length;
      const filtered = this.filteredSeqs.length;
      countEl.textContent = filtered === total ? `${total} sequences` : `${filtered}/${total} sequences`;
    }
  }

  _togglePositionRuler() {
    this.showPositionRuler = !this.showPositionRuler;
    const button = this.toolbar.querySelector('[data-action="toggle-ruler"]');
    if (button) {
      button.style.backgroundColor = this.showPositionRuler ? '#cbd5e1' : '#f1f5f9';
    }
    this.render();
  }

  _toggleCompactView() {
    this.compactView = !this.compactView;
    const button = this.toolbar.querySelector('[data-action="compact-view"]');
    if (button) {
      button.style.backgroundColor = this.compactView ? '#cbd5e1' : '#f1f5f9';
      button.title = this.compactView ? 'Show all positions' : 'Show only variable positions';
    }
    this.render();
  }

  _getVariablePositions(sequences) {
    if (!sequences.length) return [];

    const maxLen = Math.max(...sequences.map(s => s.seq.length));
    const variablePositions = [];

    for (let i = 0; i < maxLen; i++) {
      const chars = new Set();
      sequences.forEach(seq => {
        const char = seq.seq[i] || '-';
        if (char !== '-') chars.add(char);
      });

      if (chars.size > 1) {
        variablePositions.push(i);
      }
    }

    return variablePositions;
  }

  _filterSequenceForCompactView(seq, variablePositions) {
    if (!this.compactView) return seq;
    return variablePositions.map(pos => seq[pos] || '-').join('');
  }

  _exportAlignment() {
    const sequences = this.filteredSeqs.filter(s => s.name.toLowerCase() !== 'region');
    if (!sequences.length) {
      alert('No sequences to export');
      return;
    }

    let fastaContent = '';
    sequences.forEach(seq => {
      fastaContent += `>${seq.name}\n${seq.seq}\n`;
    });

    const blob = new Blob([fastaContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'alignment.fasta';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  _toggleColumnSelection(columnIndex) {
    if (this.selectedColumns.has(columnIndex)) {
      this.selectedColumns.delete(columnIndex);
    } else {
      this.selectedColumns.add(columnIndex);
    }
    this._updateColumnHighlighting();
  }

  _updateColumnHighlighting() {
    this.rowsWrap.querySelectorAll('.msa-cell').forEach((cell, globalIndex) => {
      const row = cell.closest('.flex');
      const cellIndex = Array.from(row.querySelectorAll('.msa-cell')).indexOf(cell);

      if (this.selectedColumns.has(cellIndex)) {
        cell.classList.add('ring-2', 'ring-blue-500', 'bg-blue-50');
      } else {
        cell.classList.remove('ring-2', 'ring-blue-500', 'bg-blue-50');
      }
    });
  }

  _calculateConservation(sequences, position) {
    const chars = sequences.map(s => s.seq[position] || '-').filter(c => c !== '-');
    if (chars.length === 0) return 0;

    const counts = {};
    chars.forEach(c => counts[c] = (counts[c] || 0) + 1);
    const maxCount = Math.max(...Object.values(counts));
    return maxCount / chars.length;
  }

  _addStyles() {
    // Add custom styles for MSA viewer if not already added
    if (document.getElementById('msa-viewer-styles')) return;

    const style = document.createElement('style');
    style.id = 'msa-viewer-styles';
    style.textContent = `
      .msa-cell {
        transition: all 0.15s ease;
        user-select: none;
      }
      
      .msa-cell:hover {
        transform: scale(1.1);
        z-index: 10;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
      }
      
      .msa-name {
        font-feature-settings: "tnum";
      }
      
      .msa-consensus-row {
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
      }
      
      .msa-position-ruler-row {
        font-feature-settings: "tnum";
      }
      
      .msa-region-bar-row {
        background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
      }
      
      @media (max-width: 768px) {
        .msa-viewer-toolbar {
          flex-direction: column;
          gap: 0.5rem;
        }
        
        .msa-viewer-toolbar > div {
          justify-content: center;
        }
      }
    `;
    document.head.appendChild(style);
  }

  _calculateNameColWidth() {
    if (!this.seqs || !this.seqs.length) return 120; // Default minimum width

    // Find the longest sequence name
    const longestName = this.seqs.reduce((longest, seq) =>
      seq.name.length > longest.length ? seq.name : longest, ''
    );

    // Add special names that might be added (Consensus, Germline, Regions)
    const specialNames = ['Consensus', 'Germline', 'Regions'];
    const allNames = [longestName, ...specialNames];
    const actualLongestName = allNames.reduce((longest, name) =>
      name.length > longest.length ? name : longest, ''
    );

    // Calculate width: approximately 8px per character + padding
    // Use a temporary canvas to measure text width more accurately
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    ctx.font = `${this.baseSize}px monospace`;
    const textWidth = ctx.measureText(actualLongestName).width;

    // Add padding (24px total: 12px left + 12px right) and ensure minimum width
    const calculatedWidth = Math.max(120, Math.ceil(textWidth + 24));

    return calculatedWidth;
  }

  _calculateNameColWidthForSequences(sequences) {
    if (!sequences || !sequences.length) return 120; // Default minimum width

    // Find the longest sequence name from the provided sequences
    const longestName = sequences.reduce((longest, seq) =>
      seq.name.length > longest.length ? seq.name : longest, ''
    );

    // Add special names that might be added (Consensus, Germline, Regions)
    const specialNames = ['Consensus', 'Germline', 'Regions'];
    const allNames = [longestName, ...specialNames];
    const actualLongestName = allNames.reduce((longest, name) =>
      name.length > longest.length ? name : longest, ''
    );

    // Calculate width: approximately 8px per character + padding
    // Use a temporary canvas to measure text width more accurately
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    ctx.font = `${this.baseSize}px monospace`;
    const textWidth = ctx.measureText(actualLongestName).width;

    // Add padding (24px total: 12px left + 12px right) and ensure minimum width
    const calculatedWidth = Math.max(120, Math.ceil(textWidth + 24));

    return calculatedWidth;
  }

  _toggleHighlighting() {
    this.highlightMismatches = !this.highlightMismatches;
    const button = this.toolbar.querySelector('[data-action="toggle-highlighting"]');
    if (button) {
      button.style.backgroundColor = this.highlightMismatches ? '#cbd5e1' : '#f1f5f9';
      button.title = this.highlightMismatches ? 'Turn off germline mismatch highlighting' : 'Turn on germline mismatch highlighting';
    }
    this.render();
  }

  _toggleColoring() {
    this.showAminoAcidColors = !this.showAminoAcidColors;
    const button = this.toolbar.querySelector('[data-action="toggle-coloring"]');
    if (button) {
      button.style.backgroundColor = this.showAminoAcidColors ? '#cbd5e1' : '#f1f5f9';
      button.title = this.showAminoAcidColors ? 'Turn off amino acid colors' : 'Turn on amino acid colors';
    }
    this.render();
  }

  render() {
    this.rowsWrap.innerHTML = '';
    if (!this.seqs || !this.seqs.length) {
      this.rowsWrap.insertAdjacentHTML('beforeend', '<p class="text-gray-500 p-4 text-center">No sequence data to display.</p>');
      return;
    }

    // Use filtered sequences
    const sequencesToRender = this.filteredSeqs.filter(s => s.name.toLowerCase() !== 'region');
    if (!sequencesToRender.length) {
      this.rowsWrap.insertAdjacentHTML('beforeend', '<p class="text-gray-500 p-4 text-center">No sequences match the filter.</p>');
      return;
    }

    const germlineObj = sequencesToRender.find(s => s.name.toLowerCase() === 'germline');
    const germlineSeq = germlineObj ? germlineObj.seq : null;

    const consensusObj = sequencesToRender.find(s => s.name.toLowerCase() === 'consensus');
    const consensusSeq = consensusObj ? consensusObj.seq : this._consensus(sequencesToRender.filter(s => s.name.toLowerCase() !== 'germline'));

    // Get variable positions for compact view
    const variablePositions = this.compactView ?
      this._getVariablePositions(sequencesToRender.filter(s => s.name.toLowerCase() !== 'consensus' && s.name.toLowerCase() !== 'germline')) :
      null;

    const seqLen = this.compactView ?
      (variablePositions ? variablePositions.length : 0) :
      Math.max(
        ...sequencesToRender.map(s => s.seq.length),
        germlineSeq ? germlineSeq.length : 0,
        consensusSeq ? consensusSeq.length : 0
      );

    // Add region bar first (sticky at top)
    const regionBar = this._regionBarDOM(seqLen);
    if (regionBar) {
      this.rowsWrap.appendChild(regionBar);
    }

    // Add position ruler
    const positionRuler = this._positionRulerDOM(seqLen);
    if (positionRuler) {
      this.rowsWrap.appendChild(positionRuler);
    }

    // Add consensus row next (sticky below region bar)
    if (consensusObj) {
      const displaySeq = this._filterSequenceForCompactView(consensusSeq, variablePositions);
      const displayGermline = germlineSeq ? this._filterSequenceForCompactView(germlineSeq, variablePositions) : null;
      this.rowsWrap.appendChild(
        this._rowDOM('Consensus', displaySeq, {
          isConsensus: true,
          germlineSeq: displayGermline
        })
      );
    }

    // Add all other sequences (germline and regular sequences)
    sequencesToRender
      .filter(s => s.name.toLowerCase() !== 'consensus')
      .forEach(({ name, seq }) => {
        const isGermlineRow = name.toLowerCase() === 'germline';
        const displaySeq = this._filterSequenceForCompactView(seq, variablePositions);
        const displayGermline = germlineSeq ? this._filterSequenceForCompactView(germlineSeq, variablePositions) : null;
        this.rowsWrap.appendChild(
          this._rowDOM(name, displaySeq, {
            isGermline: isGermlineRow,
            germlineSeq: displayGermline
          })
        );
      });

    this._setZoom(this.zoom);
    this._updateSequenceCount();
    this._updateColumnHighlighting();
  }

  _showHelp() {
    const helpText = `
MSA Viewer Help:

🔍 Search: Filter sequences by name
📏 Ruler: Toggle position numbers
� Compact: Show only variable positions
�💾 Export: Download alignment as FASTA
❓ Help: Show this help message

Keyboard Shortcuts:
• Ctrl/Cmd + Plus: Zoom in
• Ctrl/Cmd + Minus: Zoom out  
• Ctrl/Cmd + 0: Reset zoom

Color Coding:
🔵 Blue: Hydrophobic amino acids (A, F, I, L, M, V, W)
🟢 Green: Polar amino acids (G, N, Q, S, T, Y)
🟡 Yellow: Special amino acids (C, P)
🟣 Purple: Charged amino acids (H, K, R)
🔴 Red: Acidic amino acids (D, E)
⚪ Gray: Gaps and stops (-, *, .)

Visual Indicators:
• Green ring: 100% conserved position
• Yellow ring: 80%+ conserved position
• Yellow highlight: Mismatch with germline
• Blue highlight: Selected column

Interaction:
• Click amino acid cells to select columns
• Hover over cells for amino acid information
• Cells scale on hover for better visibility
    `;

    alert(helpText);
  }
}
