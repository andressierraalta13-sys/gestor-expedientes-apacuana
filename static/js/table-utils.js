/* ═══════════════════════════════════════════════════════════════
   GESTOR APACUANA — Table Utilities
   Client-side search, sort, and pagination for HTML tables.
   ═══════════════════════════════════════════════════════════════ */

class TableController {
  /**
   * @param {string} tableId — ID of the <table> element
   * @param {Object} options
   * @param {string} options.searchInputId — ID of search input
   * @param {string} options.countId — ID of element to show count
   * @param {string} options.paginationId — ID of pagination container
   * @param {number} options.perPage — Rows per page (default 15)
   */
  constructor(tableId, options = {}) {
    this.table = document.getElementById(tableId);
    if (!this.table) return;

    this.tbody = this.table.querySelector('tbody');
    this.allRows = Array.from(this.tbody.querySelectorAll('tr'));
    this.filteredRows = [...this.allRows];
    this.currentPage = 1;
    this.perPage = options.perPage || 15;
    this.sortCol = -1;
    this.sortAsc = true;

    // Search
    if (options.searchInputId) {
      this.searchInput = document.getElementById(options.searchInputId);
      if (this.searchInput) {
        let timeout;
        this.searchInput.addEventListener('input', () => {
          clearTimeout(timeout);
          timeout = setTimeout(() => this._search(), 200);
        });
      }
    }

    // Count display
    this.countEl = options.countId ? document.getElementById(options.countId) : null;

    // Pagination container
    this.paginationEl = options.paginationId ? document.getElementById(options.paginationId) : null;

    // Callback on render
    this.onRender = options.onRender || null;

    // Sortable headers
    this._setupSort();

    // Initial render
    this._render();
  }

  /** Filter rows based on search query */
  _search() {
    const query = (this.searchInput?.value || '').toLowerCase().trim();

    if (!query) {
      this.filteredRows = [...this.allRows];
    } else {
      const normalizedQuery = query.replace(/[.\-]/g, '');
      this.filteredRows = this.allRows.filter(row => {
        const normalizedRowText = row.textContent.toLowerCase().replace(/[.\-]/g, '');
        return normalizedRowText.includes(normalizedQuery) || row.textContent.toLowerCase().includes(query);
      });
    }

    this.currentPage = 1;
    this._render();
  }

  /** Setup click handlers on sortable column headers */
  _setupSort() {
    const headers = this.table.querySelectorAll('thead th.sortable');
    headers.forEach((th, idx) => {
      th.addEventListener('click', () => {
        // Determine actual column index (account for colspan, etc.)
        const colIdx = parseInt(th.dataset.col || idx);

        if (this.sortCol === colIdx) {
          this.sortAsc = !this.sortAsc;
        } else {
          this.sortCol = colIdx;
          this.sortAsc = true;
        }

        // Update header classes
        headers.forEach(h => h.classList.remove('asc', 'desc'));
        th.classList.add(this.sortAsc ? 'asc' : 'desc');

        // Sort
        this.filteredRows.sort((a, b) => {
          const aVal = (a.cells[colIdx]?.textContent || '').trim().toLowerCase();
          const bVal = (b.cells[colIdx]?.textContent || '').trim().toLowerCase();

          // Try numeric comparison
          const aNum = parseFloat(aVal.replace(/[^0-9.-]/g, ''));
          const bNum = parseFloat(bVal.replace(/[^0-9.-]/g, ''));
          if (!isNaN(aNum) && !isNaN(bNum)) {
            return this.sortAsc ? aNum - bNum : bNum - aNum;
          }

          // String comparison
          return this.sortAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
        });

        this.currentPage = 1;
        this._render();
      });
    });
  }

  /** Render current page of filtered rows */
  _render() {
    const total = this.filteredRows.length;
    const totalPages = Math.max(1, Math.ceil(total / this.perPage));
    this.currentPage = Math.min(this.currentPage, totalPages);

    const start = (this.currentPage - 1) * this.perPage;
    const end = Math.min(start + this.perPage, total);
    const visible = this.filteredRows.slice(start, end);

    // Hide all, show only current page
    this.allRows.forEach(r => r.style.display = 'none');
    visible.forEach(r => r.style.display = '');

    // Update count
    if (this.countEl) {
      if (total === this.allRows.length) {
        this.countEl.textContent = `${total} registros`;
      } else {
        this.countEl.textContent = `${total} de ${this.allRows.length} registros`;
      }
    }

    // Update pagination
    this._renderPagination(totalPages);

    // Call external onRender callback
    if (this.onRender) {
      this.onRender(this);
    }
  }

  /** Render pagination controls */
  _renderPagination(totalPages) {
    if (!this.paginationEl) return;

    const total = this.filteredRows.length;
    const start = (this.currentPage - 1) * this.perPage + 1;
    const end = Math.min(this.currentPage * this.perPage, total);

    let html = `
      <span>Mostrando ${total > 0 ? start : 0}–${end} de ${total}</span>
      <div class="pagination-pages">
    `;

    // Previous
    html += `<button class="pagination-btn" ${this.currentPage <= 1 ? 'disabled' : ''} data-page="${this.currentPage - 1}">
      <span class="material-symbols-outlined" style="font-size:16px">chevron_left</span>
    </button>`;

    // Page numbers (show max 7)
    const maxButtons = 7;
    let pageStart = Math.max(1, this.currentPage - 3);
    let pageEnd = Math.min(totalPages, pageStart + maxButtons - 1);
    if (pageEnd - pageStart < maxButtons - 1) {
      pageStart = Math.max(1, pageEnd - maxButtons + 1);
    }

    if (pageStart > 1) {
      html += `<button class="pagination-btn" data-page="1">1</button>`;
      if (pageStart > 2) html += `<span style="padding:0 4px;color:var(--color-text-tertiary)">…</span>`;
    }

    for (let i = pageStart; i <= pageEnd; i++) {
      html += `<button class="pagination-btn ${i === this.currentPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
    }

    if (pageEnd < totalPages) {
      if (pageEnd < totalPages - 1) html += `<span style="padding:0 4px;color:var(--color-text-tertiary)">…</span>`;
      html += `<button class="pagination-btn" data-page="${totalPages}">${totalPages}</button>`;
    }

    // Next
    html += `<button class="pagination-btn" ${this.currentPage >= totalPages ? 'disabled' : ''} data-page="${this.currentPage + 1}">
      <span class="material-symbols-outlined" style="font-size:16px">chevron_right</span>
    </button>`;

    html += '</div>';
    this.paginationEl.innerHTML = html;

    // Bind page clicks
    this.paginationEl.querySelectorAll('[data-page]').forEach(btn => {
      btn.addEventListener('click', () => {
        const page = parseInt(btn.dataset.page);
        if (page >= 1 && page <= totalPages) {
          this.currentPage = page;
          this._render();
        }
      });
    });
  }

  /** Go to specific page */
  goToPage(page) {
    this.currentPage = page;
    this._render();
  }
}

// Export for use
window.TableController = TableController;
