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
  constructor (containerId, sequences) {
    this.container = document.getElementById(containerId);
    this.seqs      = sequences ?? [];
    this.zoom      = 1;
    this.baseSize  =  14; // px – will scale with zoom
    // Amino acid color scheme
    this.aaColors = {
      'A': 'bg-blue-100', // Alanine - hydrophobic
      'C': 'bg-yellow-100', // Cysteine - special
      'D': 'bg-red-100', // Aspartic acid - acidic
      'E': 'bg-red-100', // Glutamic acid - acidic
      'F': 'bg-blue-100', // Phenylalanine - hydrophobic
      'G': 'bg-green-100', // Glycine - special
      'H': 'bg-purple-100', // Histidine - basic
      'I': 'bg-blue-100', // Isoleucine - hydrophobic
      'K': 'bg-purple-100', // Lysine - basic
      'L': 'bg-blue-100', // Leucine - hydrophobic
      'M': 'bg-blue-100', // Methionine - hydrophobic
      'N': 'bg-green-100', // Asparagine - polar
      'P': 'bg-yellow-100', // Proline - special
      'Q': 'bg-green-100', // Glutamine - polar
      'R': 'bg-purple-100', // Arginine - basic
      'S': 'bg-green-100', // Serine - polar
      'T': 'bg-green-100', // Threonine - polar
      'V': 'bg-blue-100', // Valine - hydrophobic
      'W': 'bg-blue-100', // Tryptophan - hydrophobic
      'Y': 'bg-green-100', // Tyrosine - polar
      '-': 'bg-gray-100', // Gap
      '*': 'bg-gray-100', // Stop codon
      '.': 'bg-gray-100'  // Gap
    };
    if (!this.container) { console.error(`[MSAViewer] container #${containerId} missing`); return; }

    // ------------------------------------------------------------------
    // Build DOM scaffold                                                
    // ------------------------------------------------------------------
    this.container.innerHTML = '';

    // Toolbar (sticky → stays visible while scrolling)
    this.toolbar = document.createElement('div');
    this.toolbar.className = 'flex justify-end gap-2 p-2 bg-slate-50 border-b border-slate-200 sticky top-0 z-20';
    this.toolbar.innerHTML = `
      <button class="px-2 py-1 rounded bg-slate-200 text-sm font-bold" data-action="zoom-in">+</button>
      <button class="px-2 py-1 rounded bg-slate-200 text-sm font-bold" data-action="zoom-out">−</button>
      <button class="px-2 py-1 rounded bg-slate-200 text-sm font-bold" data-action="reset">Reset</button>
    `;
    this.container.appendChild(this.toolbar);

    // Scroll container
    this.scrollArea = document.createElement('div');
    this.scrollArea.className = 'overflow-auto max-h-96';
    this.container.appendChild(this.scrollArea);

    // Wrapper that grows horizontally (so table can be wider than viewport)
    this.rowsWrap = document.createElement('div');
    this.rowsWrap.className = 'inline-block min-w-max';
    this.scrollArea.appendChild(this.rowsWrap);

    this._bindControls();
    this.render();
  }

  // ------------------------------------------------------------
  // Bind toolbar controls                                       
  // ------------------------------------------------------------
  _bindControls () {
    this.toolbar.addEventListener('click', e => {
      const act = e.target.dataset.action;
      if (!act) return;
      if (act === 'zoom-in')  this._setZoom(this.zoom * 1.25);
      if (act === 'zoom-out') this._setZoom(this.zoom / 1.25);
      if (act === 'reset')    this._setZoom(1);
    });
  }

  // ------------------------------------------------------------
  // Update zoom (font-size + cell width)                        
  // ------------------------------------------------------------
  _setZoom (z) {
    this.zoom = Math.min(Math.max(z, 0.5), 3);
    // Update font size on every rendered row & cell width
    const size = this.baseSize * this.zoom;
    this.rowsWrap.querySelectorAll('.msa-name, .msa-seq').forEach(el => {
      el.style.fontSize = `${size}px`;
    });
    this.rowsWrap.querySelectorAll('.msa-cell').forEach(cell => {
      cell.style.width = `${size + 2}px`; // +2 → a bit of breathing room
    });
  }

  // ------------------------------------------------------------
  // Compute consensus sequence                                  
  // ------------------------------------------------------------
  _consensus () {
    if (!this.seqs.length) return '';
    const len = Math.max(...this.seqs.map(s => s.seq.length));
    let out = '';
    for (let i = 0; i < len; i++) {
      const counts = new Map();
      this.seqs.forEach(({ seq }) => {
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

  // ------------------------------------------------------------
  // Render a single row of the alignment                        
  // ------------------------------------------------------------
  _rowDOM (name, seq, { isConsensus = false, consensus = null } = {}) {
    const row = document.createElement('div');
    row.className = 'flex border-b border-slate-100 items-stretch';
    if (isConsensus) row.classList.add('bg-slate-100', 'sticky', 'top-0', 'z-10');

    // Name column (sticky so it stays when scrolling horizontally)
    const nameCol = document.createElement('div');
    nameCol.className = 'msa-name w-32 pr-3 text-right font-mono font-semibold text-slate-700 border-r border-slate-300 bg-white sticky left-0 z-10';
    nameCol.textContent = name;

    // Sequence cells container
    const seqDiv = document.createElement('div');
    seqDiv.className = 'msa-seq flex';

    [...seq].forEach((aa, idx) => {
      const span = document.createElement('span');
      span.className = 'msa-cell inline-block text-center';
      span.style.width = `${this.baseSize * this.zoom + 2}px`;
      span.textContent = aa;
      
      // Apply amino acid color
      const colorClass = this.aaColors[aa] || 'bg-gray-100';
      span.classList.add(colorClass, 'rounded');
      
      // Make consensus sequence bold
      if (isConsensus) {
        span.classList.add('font-bold');
      }
      
      // Add mismatch highlighting if not consensus
      if (!isConsensus && consensus && aa !== consensus[idx]) {
        span.classList.add('bg-yellow-200', 'font-bold');
        // Add a subtle border to make it stand out more
        span.classList.add('border', 'border-yellow-400');
      }
      seqDiv.appendChild(span);
    });

    row.appendChild(nameCol);
    row.appendChild(seqDiv);
    return row;
  }

  // ------------------------------------------------------------
  // Render entire alignment                                     
  // ------------------------------------------------------------
  render () {
    this.rowsWrap.innerHTML = '';
    if (!this.seqs.length) {
      this.rowsWrap.insertAdjacentHTML('beforeend', '<p class="text-gray-500 p-2">No sequence data.</p>');
      return;
    }

    const cons   = this._consensus();
    const hasSeq = Boolean(cons);
    if (hasSeq) this.rowsWrap.appendChild(this._rowDOM('Consensus', cons, { isConsensus: true }));

    this.seqs.forEach(r => {
      this.rowsWrap.appendChild(this._rowDOM(r.name, r.seq, { consensus: cons }));
    });

    this._setZoom(this.zoom); // ensure initial font size & widths
  }
}

// ------------------------------------------------------------
// Boot                                                 
// ------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  const hcContainer = document.getElementById('msa-hc');
  const lcContainer = document.getElementById('msa-lc');

  if (hcContainer?.dataset.seqs) {
    const hcSeqs = JSON.parse(hcContainer.dataset.seqs);
    if (Array.isArray(hcSeqs) && hcSeqs.length) new MSAViewer('msa-hc', hcSeqs);
  }

  if (lcContainer?.dataset.seqs) {
    const lcSeqs = JSON.parse(lcContainer.dataset.seqs);
    if (Array.isArray(lcSeqs) && lcSeqs.length) new MSAViewer('msa-lc', lcSeqs);
  }
}); 