/* ═══════════════════════════════════════════════════════════════
   GESTOR APACUANA — Theme Manager
   Handles theme (light/dark/auto), accent colors, density,
   and persists preferences in localStorage.
   ═══════════════════════════════════════════════════════════════ */

const ThemeManager = {
  KEYS: {
    theme:    'gestor_theme',
    accent:   'gestor_accent',
    density:  'gestor_density',
  },

  DEFAULTS: {
    theme:   'light',
    accent:  'emerald',
    density: 'comfortable',
  },

  /** Initialize theme from localStorage on page load */
  init() {
    const theme   = localStorage.getItem(this.KEYS.theme)   || this.DEFAULTS.theme;
    const accent  = localStorage.getItem(this.KEYS.accent)  || this.DEFAULTS.accent;
    const density = localStorage.getItem(this.KEYS.density) || this.DEFAULTS.density;
    const sidebarColor = localStorage.getItem('gestor_sidebar_color');

    this.applyTheme(theme, false);
    this.applyAccent(accent, false);
    this.applyDensity(density, false);
    if (sidebarColor) this.applySidebarColor(sidebarColor, false);

    // Listen for OS theme changes when in auto mode
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if (this.getTheme() === 'auto') {
        this.applyTheme('auto', false);
      }
    });
  },

  /** Get current saved theme preference */
  getTheme() {
    return localStorage.getItem(this.KEYS.theme) || this.DEFAULTS.theme;
  },

  getAccent() {
    return localStorage.getItem(this.KEYS.accent) || this.DEFAULTS.accent;
  },

  getDensity() {
    return localStorage.getItem(this.KEYS.density) || this.DEFAULTS.density;
  },

  /** Apply theme to DOM */
  applyTheme(theme, save = true) {
    let resolved = theme;
    if (theme === 'auto') {
      resolved = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', resolved);
    if (save) localStorage.setItem(this.KEYS.theme, theme);

    // Update toggle button icon
    this._updateThemeIcon(resolved);
  },

  /** Apply accent color to DOM */
  applyAccent(accent, save = true) {
    // If it starts with # it's a custom color
    if (accent.startsWith('#')) {
      document.documentElement.setAttribute('data-accent', 'custom');
      this._applyCustomColor(accent);
    } else {
      document.documentElement.setAttribute('data-accent', accent);
      // Remove custom properties if previously set
      document.documentElement.style.removeProperty('--color-accent');
      document.documentElement.style.removeProperty('--color-accent-hover');
      document.documentElement.style.removeProperty('--color-accent-subtle');
      document.documentElement.style.removeProperty('--color-accent-text');
      document.documentElement.style.removeProperty('--color-accent-ring');
    }
    if (save) localStorage.setItem(this.KEYS.accent, accent);

    // Update swatch selection in customize panel
    this._updateSwatchSelection(accent);
  },

  /** Apply density */
  applyDensity(density, save = true) {
    document.documentElement.setAttribute('data-density', density);
    if (save) localStorage.setItem(this.KEYS.density, density);
  },

  applySidebarColor(color, save = true) {
    document.documentElement.style.setProperty('--sidebar-bg', color);
    if (save) localStorage.setItem('gestor_sidebar_color', color);
  },

  /** Toggle between light and dark */
  toggleTheme() {
    const current = this.getTheme();
    const next = (current === 'dark') ? 'light' : 'dark';
    this.applyTheme(next);
  },

  /** Reset all preferences to defaults */
  resetAll() {
    Object.values(this.KEYS).forEach(k => localStorage.removeItem(k));
    localStorage.removeItem('gestor_sidebar_color');
    document.documentElement.style.removeProperty('--sidebar-bg');
    this.applyTheme(this.DEFAULTS.theme);
    this.applyAccent(this.DEFAULTS.accent);
    this.applyDensity(this.DEFAULTS.density);
  },

  /** Apply custom hex color */
  _applyCustomColor(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);

    document.documentElement.style.setProperty('--color-accent', hex);
    // Darken for hover
    const darken = (c) => Math.max(0, Math.round(c * 0.85));
    document.documentElement.style.setProperty('--color-accent-hover',
      `rgb(${darken(r)}, ${darken(g)}, ${darken(b)})`);
    // Subtle background
    document.documentElement.style.setProperty('--color-accent-subtle',
      `rgba(${r}, ${g}, ${b}, 0.1)`);
    // Text on subtle
    document.documentElement.style.setProperty('--color-accent-text', hex);
    // Focus ring
    document.documentElement.style.setProperty('--color-accent-ring',
      `rgba(${r}, ${g}, ${b}, 0.25)`);
  },

  /** Update the theme toggle icon in header */
  _updateThemeIcon(resolved) {
    const icon = document.getElementById('theme-toggle-icon');
    if (!icon) return;
    if (resolved === 'dark') {
      icon.textContent = 'light_mode';
    } else {
      icon.textContent = 'dark_mode';
    }
  },

  /** Update which color swatch is selected in customize panel */
  _updateSwatchSelection(accent) {
    document.querySelectorAll('.color-swatch').forEach(el => {
      el.classList.toggle('selected', el.dataset.accent === accent);
    });
  }
};

// ─── CUSTOMIZE PANEL CONTROLLER ─────────────────────────────────
const CustomizePanel = {
  isOpen: false,

  toggle() {
    this.isOpen = !this.isOpen;
    const panel = document.getElementById('customize-panel');
    const backdrop = document.getElementById('customize-backdrop');
    if (panel) panel.classList.toggle('open', this.isOpen);
    if (backdrop) backdrop.classList.toggle('open', this.isOpen);

    if (this.isOpen) this._syncUI();
  },

  close() {
    this.isOpen = false;
    const panel = document.getElementById('customize-panel');
    const backdrop = document.getElementById('customize-backdrop');
    if (panel) panel.classList.remove('open');
    if (backdrop) backdrop.classList.remove('open');
  },

  _syncUI() {
    // Sync theme buttons
    const theme = ThemeManager.getTheme();
    document.querySelectorAll('[data-set-theme]').forEach(el => {
      el.classList.toggle('selected', el.dataset.setTheme === theme);
    });

    // Sync accent swatches
    const accent = ThemeManager.getAccent();
    document.querySelectorAll('.color-swatch[data-accent]').forEach(el => {
      el.classList.toggle('selected', el.dataset.accent === accent);
    });

    // Sync density
    const density = ThemeManager.getDensity();
    document.querySelectorAll('[data-set-density]').forEach(el => {
      el.classList.toggle('selected', el.dataset.setDensity === density);
    });

    // Sync sidebar color swatches
    const sidebarColor = localStorage.getItem('gestor_sidebar_color') || '#111827';
    this._syncSidebarSwatches(sidebarColor);

    // Update sidebar color picker input value
    const sidebarPicker = document.getElementById('sidebar-color-picker');
    if (sidebarPicker) sidebarPicker.value = sidebarColor;
  },

  _syncSidebarSwatches(activeColor) {
    const normalizedActive = activeColor.toUpperCase();
    document.querySelectorAll('.sidebar-color-swatch').forEach(el => {
      const swatchColor = (el.dataset.sidebarColor || '').toUpperCase();
      el.classList.toggle('selected', swatchColor === normalizedActive);
    });
  }
};

// ─── TOAST SYSTEM ───────────────────────────────────────────────
const Toast = {
  show(message, type = 'info', duration = 4000) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <span class="material-symbols-outlined" style="font-size:18px;color:var(--color-${type})">
        ${type === 'success' ? 'check_circle' : type === 'error' ? 'error' : type === 'warning' ? 'warning' : 'info'}
      </span>
      <span style="flex:1">${message}</span>
      <button onclick="this.parentElement.remove()" style="background:none;border:none;cursor:pointer;color:var(--color-text-tertiary);padding:2px">
        <span class="material-symbols-outlined" style="font-size:16px">close</span>
      </button>
    `;

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      toast.style.transition = 'all 300ms ease';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  },

  success(msg) { this.show(msg, 'success'); },
  error(msg)   { this.show(msg, 'error');   },
  warning(msg) { this.show(msg, 'warning'); },
  info(msg)    { this.show(msg, 'info');    },
};

// Initialize immediately (before DOMContentLoaded to prevent flash)
ThemeManager.init();
