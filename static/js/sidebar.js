/* ═══════════════════════════════════════════════════════════════
   GESTOR APACUANA — Sidebar Controller
   Handles collapse/expand, mobile drawer, submenu toggles,
   and persists collapsed state in localStorage.
   ═══════════════════════════════════════════════════════════════ */

const Sidebar = {
  STORAGE_KEY: 'gestor_sidebar_collapsed',

  init() {
    this.sidebar  = document.getElementById('app-sidebar');
    this.overlay  = document.getElementById('sidebar-overlay');
    this.toggleBtn = document.getElementById('sidebar-toggle');

    if (!this.sidebar) return;

    // Restore saved state (desktop only)
    const saved = localStorage.getItem(this.STORAGE_KEY);
    if (window.innerWidth > 1400) {
      // Full desktop (>1400px): respect saved state
      if (saved === 'true') {
        this.sidebar.classList.add('collapsed');
      }
    } else if (window.innerWidth > 1024) {
      // Low-res desktop (1025-1400px, includes 1366x768): auto-collapse (CSS handles :hover expand)
      this.sidebar.classList.add('collapsed');
    }

    // Toggle button
    if (this.toggleBtn) {
      this.toggleBtn.addEventListener('click', () => this.toggle());
    }

    // Mobile overlay close
    if (this.overlay) {
      this.overlay.addEventListener('click', () => this.closeMobile());
    }

    // Auto-open relevant submenus based on current page
    this._autoExpandActiveSubmenu();

    // Setup submenu toggles
    this._setupSubmenus();

    // Handle resize
    window.addEventListener('resize', () => {
      if (window.innerWidth > 1024) {
        this.closeMobile();
      }
    });
  },

  /** Toggle sidebar collapsed state */
  toggle() {
    if (window.innerWidth <= 1024) {
      this.toggleMobile();
      return;
    }
    this.sidebar.classList.toggle('collapsed');
    const isCollapsed = this.sidebar.classList.contains('collapsed');
    localStorage.setItem(this.STORAGE_KEY, isCollapsed);
  },

  /** Expand sidebar */
  expand() {
    this.sidebar.classList.remove('collapsed');
    localStorage.setItem(this.STORAGE_KEY, 'false');
  },

  /** Collapse sidebar */
  collapse() {
    this.sidebar.classList.add('collapsed');
    localStorage.setItem(this.STORAGE_KEY, 'true');
  },

  /** Open mobile sidebar */
  openMobile() {
    this.sidebar.classList.add('mobile-open');
    if (this.overlay) this.overlay.classList.add('mobile-open');
    document.body.style.overflow = 'hidden';
  },

  /** Close mobile sidebar */
  closeMobile() {
    this.sidebar.classList.remove('mobile-open');
    if (this.overlay) this.overlay.classList.remove('mobile-open');
    document.body.style.overflow = '';
  },

  /** Toggle mobile sidebar */
  toggleMobile() {
    if (this.sidebar.classList.contains('mobile-open')) {
      this.closeMobile();
    } else {
      this.openMobile();
    }
  },

  /** Setup all submenu toggle buttons */
  _setupSubmenus() {
    document.querySelectorAll('.sidebar-submenu-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const submenu = btn.nextElementSibling;
        if (!submenu || !submenu.classList.contains('sidebar-submenu')) return;

        const isOpen = submenu.classList.contains('open');
        const expanded = !isOpen;

        submenu.classList.toggle('open');
        btn.setAttribute('aria-expanded', expanded);
      });
    });
  },

  /** Auto-expand the submenu containing the current active page */
  _autoExpandActiveSubmenu() {
    const activeLink = this.sidebar.querySelector('.sidebar-link.active');
    if (!activeLink) return;

    const parentSubmenu = activeLink.closest('.sidebar-submenu');
    if (parentSubmenu) {
      parentSubmenu.classList.add('open');
      const btn = parentSubmenu.previousElementSibling;
      if (btn && btn.classList.contains('sidebar-submenu-btn')) {
        btn.setAttribute('aria-expanded', 'true');
      }
    }
  }
};

function initSidebar() {
  Sidebar.init();
}
document.addEventListener('turbo:load', initSidebar);
document.addEventListener('DOMContentLoaded', () => {
  if (typeof Turbo === 'undefined') initSidebar();
});
