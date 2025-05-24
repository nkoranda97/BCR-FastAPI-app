// --------------------------------------------------
// FASTA → array<{name, seq}>
// --------------------------------------------------
function parseFASTA (txt) {
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
      chunk  = [];
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
  constructor (containerId, sequences, regionBlocks = null) {
    this.container = document.getElementById(containerId);
    this.seqs      = sequences ?? [];
    this.zoom      = 1;
    this.baseSize  =  14; // px – base font size for sequence characters, will scale with zoom
    this.regionBlocks = regionBlocks;
    // Amino acid color scheme
    this.aaColors = {
      'A': 'bg-blue-100', 'C': 'bg-yellow-100', 'D': 'bg-red-100', 'E': 'bg-red-100',
      'F': 'bg-blue-100', 'G': 'bg-green-100', 'H': 'bg-purple-100', 'I': 'bg-blue-100',
      'K': 'bg-purple-100', 'L': 'bg-blue-100', 'M': 'bg-blue-100', 'N': 'bg-green-100',
      'P': 'bg-yellow-100', 'Q': 'bg-green-100', 'R': 'bg-purple-100', 'S': 'bg-green-100',
      'T': 'bg-green-100', 'V': 'bg-blue-100', 'W': 'bg-blue-100', 'Y': 'bg-green-100',
      '-': 'bg-gray-100', '*': 'bg-gray-100', '.': 'bg-gray-100'
    };
    if (!this.container) { console.error(`[MSAViewer] container #${containerId} missing`); return; }

    this.container.innerHTML = ''; // Clear container

    // Toolbar (sticky → stays visible while scrolling)
    this.toolbar = document.createElement('div');
    this.toolbar.className = 'flex justify-end gap-2 p-2 bg-slate-50 border-b border-slate-200 sticky top-0 z-20';
    this.toolbar.innerHTML = `
      <button class="px-2 py-1 rounded bg-slate-200 text-sm font-bold hover:bg-slate-300 transition-colors" data-action="zoom-in">+</button>
      <button class="px-2 py-1 rounded bg-slate-200 text-sm font-bold hover:bg-slate-300 transition-colors" data-action="zoom-out">−</button>
      <button class="px-2 py-1 rounded bg-slate-200 text-sm font-bold hover:bg-slate-300 transition-colors" data-action="reset">Reset</button>
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
    this.render();
  }

  _bindControls () {
    this.toolbar.addEventListener('click', e => {
      const act = e.target.closest('button')?.dataset.action;
      if (!act) return;
      if (act === 'zoom-in')  this._setZoom(this.zoom * 1.25);
      if (act === 'zoom-out') this._setZoom(this.zoom / 1.25);
      if (act === 'reset')    this._setZoom(1);
    });
  }

  _setZoom (z) {
    this.zoom = Math.min(Math.max(z, 0.25), 5); 
    const newCharSize = this.baseSize * this.zoom; 

    this.rowsWrap.querySelectorAll('.msa-name, .msa-seq-char-wrapper').forEach(el => {
      el.style.fontSize = `${newCharSize}px`;
    });

    this.rowsWrap.querySelectorAll('.msa-cell').forEach(cell => {
      cell.style.width = `${newCharSize + 2}px`; 
    });
    
    this.rowsWrap.querySelectorAll('.msa-region-segment').forEach(segment => {
        const len = parseInt(segment.dataset.length, 10);
        segment.style.width = `calc(${len} * (${newCharSize + 2}px))`;
    });

    const regionBar = this.rowsWrap.querySelector('.msa-region-bar-row');
    const consensusRow = this.rowsWrap.querySelector('.msa-consensus-row');

    if (regionBar && consensusRow) {
        requestAnimationFrame(() => {
            if (this.rowsWrap.contains(regionBar)) { // Ensure regionBar is still in DOM
                const regionBarHeight = regionBar.getBoundingClientRect().height;
                consensusRow.style.top = `${regionBarHeight}px`;
            }
        });
    }
  }

  _consensus (sequences) { // Pass sequences to avoid using this.seqs if it's filtered
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

  _rowDOM (name, seq, { isConsensus = false, isGermline = false, germlineSeq = null, topOffsetPx = 0 } = {}) {
    const row = document.createElement('div');
    row.className = 'flex border-b border-slate-100 items-stretch';

    const nameCol = document.createElement('div');
    nameCol.className = 'msa-name w-32 pr-3 text-right font-mono text-slate-700 border-r border-slate-300 bg-white sticky left-0 z-15 flex items-center justify-end';
    // Apply bold to Germline and Consensus names
    if (isGermline || isConsensus) {
        nameCol.classList.add('font-bold');
    } else {
        nameCol.classList.add('font-semibold');
    }
    nameCol.style.fontSize = `${this.baseSize * this.zoom}px`;
    nameCol.textContent = name;
    row.appendChild(nameCol);

    const seqDiv = document.createElement('div');
    seqDiv.className = 'msa-seq-char-wrapper flex'; 
    seqDiv.style.fontSize = `${this.baseSize * this.zoom}px`; 

    [...seq].forEach((aa, idx) => {
      const span = document.createElement('span');
      span.className = 'msa-cell inline-block text-center leading-snug'; 
      span.style.width = `${this.baseSize * this.zoom + 2}px`; 
      span.textContent = aa;

      const colorClass = this.aaColors[aa] || 'bg-gray-100';
      span.classList.add(colorClass, 'rounded-sm'); 

      // Bold characters for Consensus and Germline sequences
      if (isConsensus || isGermline) {
        span.classList.add('font-bold');
      }
      
      // Highlight mismatches against Germline sequence (for non-Germline, non-Consensus rows)
      if (!isConsensus && !isGermline && germlineSeq && aa !== germlineSeq[idx] && aa !== '-' && germlineSeq[idx] !== '-') {
        span.classList.add('bg-yellow-200', 'font-bold', 'border', 'border-yellow-400');
      }
      seqDiv.appendChild(span);
    });
    row.appendChild(seqDiv);

    if (isConsensus) {
      row.classList.add('msa-consensus-row', 'bg-slate-100', 'sticky', 'z-5'); 
      row.style.top = `${topOffsetPx}px`;
      nameCol.classList.remove('bg-white', 'font-semibold'); // font-bold already added
      nameCol.classList.add('bg-slate-100'); 
    }
    // Optional: Add specific styling for the Germline row if needed (e.g., background)
    if (isGermline) {
       row.classList.add('bg-sky-50'); // Example light blue tint
       nameCol.classList.remove('bg-white');
       nameCol.classList.add('bg-sky-50');
     }
    return row;
  }
  
  _regionBarDOM(seqLen) {
    if (!this.regionBlocks || !this.regionBlocks.length) return null;

    const row = document.createElement('div');
    row.className = 'msa-region-bar-row flex border-b-2 border-slate-300 bg-slate-200 text-xs font-semibold text-center sticky top-0 z-10';
    
    const nameCol = document.createElement('div');
    nameCol.className = 'msa-name w-32 pr-3 text-right font-mono font-bold text-slate-700 border-r-2 border-slate-300 bg-slate-200 sticky left-0 z-15 flex items-center justify-end';
    nameCol.style.fontSize = `${this.baseSize * this.zoom}px`; 
    nameCol.textContent = 'Regions'; 
    row.appendChild(nameCol);

    const regionsContainer = document.createElement('div');
    regionsContainer.className = 'flex items-stretch'; 
    
    let currentPosition = 0;
    this.regionBlocks.forEach(([regionName, start, end], regionIdx) => { 
        const len = end - start + 1;
        if (start -1 > currentPosition) { 
            const gapLen = start - 1 - currentPosition;
            const gapSpan = document.createElement('span');
            gapSpan.className = 'msa-region-segment inline-flex items-center justify-center';
            gapSpan.dataset.length = gapLen;
            gapSpan.style.width = `calc(${gapLen} * (${this.baseSize * this.zoom + 2}px))`;
            gapSpan.innerHTML = '&nbsp;'; 
            regionsContainer.appendChild(gapSpan);
        }

        const segmentSpan = document.createElement('span');
        segmentSpan.className = 'msa-region-segment inline-flex items-center justify-center border-r border-slate-300 px-1';
        segmentSpan.dataset.length = len; 
        segmentSpan.style.width = `calc(${len} * (${this.baseSize * this.zoom + 2}px))`;
        segmentSpan.textContent = regionName;
        // Example: Alternate background colors for regions for better visual separation
        // if (regionIdx % 2 === 0) {
        //    segmentSpan.style.backgroundColor = 'rgba(0,0,0,0.03)'; // Slightly darker shade
        // }
        regionsContainer.appendChild(segmentSpan);
        currentPosition = end;
    });

    if (currentPosition < seqLen) {
        const fillLen = seqLen - currentPosition;
        const fillSpan = document.createElement('span');
        fillSpan.className = 'msa-region-segment inline-flex items-center justify-center';
        fillSpan.dataset.length = fillLen;
        fillSpan.style.width = `calc(${fillLen} * (${this.baseSize * this.zoom + 2}px))`;
        fillSpan.innerHTML = '&nbsp;';
        regionsContainer.appendChild(fillSpan);
    }
    row.appendChild(regionsContainer);
    return row;
  }

  render () {
    this.rowsWrap.innerHTML = ''; 
    if (!this.seqs || !this.seqs.length) {
      this.rowsWrap.insertAdjacentHTML('beforeend', '<p class="text-gray-500 p-4 text-center">No sequence data to display.</p>');
      return;
    }

    const sequencesToRender = this.seqs.filter(s => s.name.toLowerCase() !== 'region');
    if (!sequencesToRender.length) {
        this.rowsWrap.insertAdjacentHTML('beforeend', '<p class="text-gray-500 p-4 text-center">No sequence data after filtering.</p>');
        return;
    }

    const germlineObj = sequencesToRender.find(s => s.name.toLowerCase() === 'germline');
    const germlineSeq = germlineObj ? germlineObj.seq : null;

    const consensusObj = sequencesToRender.find(s => s.name.toLowerCase() === 'consensus');
    // Pass sequencesToRender to _consensus to avoid issues if 'Consensus' row was filtered out but needs calculation
    const consensusSeq = consensusObj ? consensusObj.seq : this._consensus(sequencesToRender.filter(s => s.name.toLowerCase() !== 'germline'));


    const seqLen = Math.max(
        ...sequencesToRender.map(s => s.seq.length), 
        germlineSeq ? germlineSeq.length : 0, 
        consensusSeq ? consensusSeq.length : 0
    );

    let regionBarHeight = 0;
    const regionBar = this._regionBarDOM(seqLen);
    if (regionBar) {
        this.rowsWrap.appendChild(regionBar);
        requestAnimationFrame(() => { 
             if (this.rowsWrap.contains(regionBar)) { 
                regionBarHeight = regionBar.getBoundingClientRect().height;
                const consensusRowEl = this.rowsWrap.querySelector('.msa-consensus-row');
                if (consensusRowEl) {
                    consensusRowEl.style.top = `${regionBarHeight}px`;
                }
            }
        });
    }
    
    sequencesToRender.forEach(({ name, seq }) => {
      const isConsensusRow = name.toLowerCase() === 'consensus';
      const isGermlineRow = name.toLowerCase() === 'germline';
      this.rowsWrap.appendChild(
        this._rowDOM(name, seq, {
          isConsensus: isConsensusRow,
          isGermline: isGermlineRow,
          germlineSeq: germlineSeq, // Pass the actual Germline sequence for comparison
          topOffsetPx: isConsensusRow ? regionBarHeight : 0 
        })
      );
    });
    
    this._setZoom(this.zoom); 
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const hcContainer = document.getElementById('msa-hc');
  const lcContainer = document.getElementById('msa-lc');

  if (hcContainer?.dataset.seqs) {
    try {
      const hcSeqs = JSON.parse(hcContainer.dataset.seqs);
      const hcRegionBlocks = hcContainer.dataset.regionBlocks ? JSON.parse(hcContainer.dataset.regionBlocks) : null;
      if (Array.isArray(hcSeqs) && hcSeqs.length) {
        new MSAViewer('msa-hc', hcSeqs, hcRegionBlocks);
      } else if (Array.isArray(hcSeqs) && hcSeqs.length === 0) {
        hcContainer.innerHTML = '<p class="text-gray-500 p-4 text-center">No Heavy-chain alignment data available.</p>';
      }
    } catch (e) {
      console.error("Error parsing HC data:", e);
      hcContainer.innerHTML = '<p class="text-red-500 p-4 text-center">Error loading Heavy-chain alignment data.</p>';
    }
  }

  if (lcContainer?.dataset.seqs) {
    try {
      const lcSeqs = JSON.parse(lcContainer.dataset.seqs);
      const lcRegionBlocks = lcContainer.dataset.regionBlocks ? JSON.parse(lcContainer.dataset.regionBlocks) : null;
      if (Array.isArray(lcSeqs) && lcSeqs.length) {
        new MSAViewer('msa-lc', lcSeqs, lcRegionBlocks);
      } else if (Array.isArray(lcSeqs) && lcSeqs.length === 0) {
         lcContainer.innerHTML = '<p class="text-gray-500 p-4 text-center">No Light-chain alignment data available.</p>';
      }
    } catch (e) {
      console.error("Error parsing LC data:", e);
      lcContainer.innerHTML = '<p class="text-red-500 p-4 text-center">Error loading Light-chain alignment data.</p>';
    }
  }
});
