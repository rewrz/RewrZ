const AVAILABLE_THEMES = ['light', 'dark', 'nature', 'ocean', 'sunset', 'sakura', 'galaxy', 'mint'];
const THEME_UI_META = {
  light: { name: '浅色', icon: 'fa-sun' },
  dark: { name: '深色', icon: 'fa-moon' },
  nature: { name: '自然', icon: 'fa-leaf' },
  ocean: { name: '海洋', icon: 'fa-water' },
  sunset: { name: '夕阳', icon: 'fa-cloud-sun' },
  sakura: { name: '樱花', icon: 'fa-heart' },
  galaxy: { name: '星空', icon: 'fa-star' },
  mint: { name: '薄荷', icon: 'fa-seedling' },
};
const DARK_MODE_THEMES = new Set(['dark', 'galaxy']);

const THEME_VARIABLE_PRESETS = {
  light: {
    '--color-primary': '#6366f1',
    '--color-primary-hover': '#4f46e5',
    '--color-secondary': '#475569',
    '--color-background': '#ffffff',
    '--color-background-alt': '#f8fafc',
    '--color-text': '#0f172a',
    '--color-text-light': '#475569',
    '--color-text-muted': '#64748b',
    '--color-border': '#cbd5e1',
    '--color-border-light': '#e2e8f0',
    '--color-card-bg': '#ffffff',
    '--color-card-shadow': 'rgba(99, 102, 241, 0.1)',
    '--color-nav-bg': 'rgba(255, 255, 255, 0.85)',
    '--color-footer-bg': '#f8fafc',
    '--font-family-base': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-heading': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-decorative': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--backdrop-blur': 'blur(12px)',
  },
  dark: {
    '--color-primary': '#818cf8',
    '--color-primary-hover': '#6366f1',
    '--color-secondary': '#cbd5e1',
    '--color-background': '#0f172a',
    '--color-background-alt': '#1e293b',
    '--color-text': '#f1f5f9',
    '--color-text-light': '#dbe4f0',
    '--color-text-muted': '#94a3b8',
    '--color-border': '#334155',
    '--color-border-light': '#475569',
    '--color-card-bg': '#1e293b',
    '--color-card-shadow': 'rgba(129, 140, 248, 0.15)',
    '--color-nav-bg': 'rgba(15, 23, 42, 0.85)',
    '--color-footer-bg': '#1e293b',
    '--font-family-base': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-heading': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-decorative': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--backdrop-blur': 'blur(12px)',
  },
  nature: {
    '--color-primary': '#10b981',
    '--color-primary-hover': '#059669',
    '--color-secondary': '#166534',
    '--color-background': '#f0fdf4',
    '--color-background-alt': '#dcfce7',
    '--color-text': '#14532d',
    '--color-text-light': '#166534',
    '--color-text-muted': '#15803d',
    '--color-border': '#86efac',
    '--color-border-light': '#dcfce7',
    '--color-card-bg': '#ffffff',
    '--color-card-shadow': 'rgba(16, 185, 129, 0.1)',
    '--color-nav-bg': 'rgba(240, 253, 244, 0.9)',
    '--color-footer-bg': '#dcfce7',
    '--font-family-base': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-heading': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-decorative': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--backdrop-blur': 'blur(12px)',
  },
  ocean: {
    '--color-primary': '#0ea5e9',
    '--color-primary-hover': '#0284c7',
    '--color-secondary': '#0f766e',
    '--color-background': '#f0f9ff',
    '--color-background-alt': '#e0f2fe',
    '--color-text': '#0c4a6e',
    '--color-text-light': '#075985',
    '--color-text-muted': '#0369a1',
    '--color-border': '#7dd3fc',
    '--color-border-light': '#e0f2fe',
    '--color-card-bg': '#ffffff',
    '--color-card-shadow': 'rgba(14, 165, 233, 0.1)',
    '--color-nav-bg': 'rgba(240, 249, 255, 0.9)',
    '--color-footer-bg': '#e0f2fe',
    '--font-family-base': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-heading': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-decorative': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--backdrop-blur': 'blur(12px)',
  },
  sunset: {
    '--color-primary': '#ea8a12',
    '--color-primary-hover': '#c96a08',
    '--color-secondary': '#9a3412',
    '--color-background': '#fff7e6',
    '--color-background-alt': '#fde7bd',
    '--color-text': '#6f2f0f',
    '--color-text-light': '#92400e',
    '--color-text-muted': '#b45309',
    '--color-border': '#f2b26b',
    '--color-border-light': '#f7d7a4',
    '--color-card-bg': '#fffdf9',
    '--color-card-shadow': 'rgba(234, 138, 18, 0.14)',
    '--color-nav-bg': 'rgba(255, 247, 230, 0.92)',
    '--color-footer-bg': '#fde7bd',
    '--font-family-base': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-heading': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-decorative': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--backdrop-blur': 'blur(12px)',
  },
  sakura: {
    '--color-primary': '#e34f96',
    '--color-primary-hover': '#c92d77',
    '--color-secondary': '#9d174d',
    '--color-background': '#fff4f8',
    '--color-background-alt': '#f9dde9',
    '--color-text': '#6d173b',
    '--color-text-light': '#84214c',
    '--color-text-muted': '#a63a68',
    '--color-border': '#ee9fc3',
    '--color-border-light': '#f6d6e5',
    '--color-card-bg': '#fffdfd',
    '--color-card-shadow': 'rgba(227, 79, 150, 0.14)',
    '--color-nav-bg': 'rgba(255, 244, 248, 0.93)',
    '--color-footer-bg': '#f9dde9',
    '--font-family-base': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-heading': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-decorative': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--backdrop-blur': 'blur(12px)',
  },
  galaxy: {
    '--color-primary': '#b26bff',
    '--color-primary-hover': '#9747f0',
    '--color-secondary': '#ddd6fe',
    '--color-background': '#0a0a18',
    '--color-background-alt': '#17162d',
    '--color-text': '#f6efff',
    '--color-text-light': '#ddd3fb',
    '--color-text-muted': '#bba9f7',
    '--color-border': '#6d55c6',
    '--color-border-light': '#2d2553',
    '--color-card-bg': '#18172c',
    '--color-card-shadow': 'rgba(178, 107, 255, 0.2)',
    '--color-nav-bg': 'rgba(10, 10, 24, 0.94)',
    '--color-footer-bg': '#17162d',
    '--font-family-base': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-heading': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-decorative': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--backdrop-blur': 'blur(14px)',
  },
  mint: {
    '--color-primary': '#12a594',
    '--color-primary-hover': '#0f8477',
    '--color-secondary': '#0f766e',
    '--color-background': '#effcf8',
    '--color-background-alt': '#d8f5ed',
    '--color-text': '#0f4f48',
    '--color-text-light': '#11635a',
    '--color-text-muted': '#14766d',
    '--color-border': '#67d9c9',
    '--color-border-light': '#c7efe6',
    '--color-card-bg': '#fbfffd',
    '--color-card-shadow': 'rgba(18, 165, 148, 0.13)',
    '--color-nav-bg': 'rgba(239, 252, 248, 0.93)',
    '--color-footer-bg': '#d8f5ed',
    '--font-family-base': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-heading': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--font-family-decorative': "'SourceHanSansCN', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif",
    '--backdrop-blur': 'blur(12px)',
  },
};

class SiteShellController {
  constructor() {
    this.root = document.documentElement;
    this.body = document.body;
    this.themeLink = document.getElementById('theme-variables-link');
    this.hljsThemeLink = document.getElementById('hljs-theme-link');
    this.theme = this.root.dataset.currentTheme || this.body?.dataset.currentTheme || 'light';
    this.effectBodyClass = this.body?.dataset.effectBodyClass || '';
    this.activeEffects = this.parseBodyEffects();
    this.themeCsrfToken = this.body?.dataset.themeCsrfToken || '';
    this.canPersistTheme = this.body?.dataset.themePersistAllowed === 'true';
    this.backgroundType = this.body?.dataset.backgroundType || 'none';
    this.backgroundUrl = this.body?.dataset.backgroundUrl || '';
    this.pageBackgroundUrl = this.body?.dataset.pageBackgroundUrl || '';
    this.homepageMode = this.body?.dataset.homepageMode || 'default';
    this.isReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.themeToastTimer = null;
    this.themeSyncInFlight = null;
  }

  init() {
    // 首屏以服务端渲染的 variables.css 为准：
    // 不用 JS 预设覆盖（避免打掉后台自定义主题色），也不重复重拉样式表
    this.applyTheme(this.theme, {
      persist: false,
      sync: false,
      announce: false,
      applyVariables: false,
      reloadCss: false,
    });
    // variables.css 加载失败时，用本地预设兜底，避免页面裸奔
    this.themeLink?.addEventListener('error', () => this.applyThemeVariables(this.theme));
    this.applyEffectBodyClass(this.effectBodyClass);
    this.applyEffects(this.activeEffects);
    this.applyBackground();
    this.applyHomepageMode();
    this.bindThemeToggle();
    this.bindMobileMenu();
    this.bindBackToTop();
    this.bindVisibilitySync();
    this.bindProfileMotion();
    this.setupHighlighting();
    window.themeManager = {
      getCurrentTheme: () => this.theme,
      setTheme: (theme) => this.applyTheme(theme, { persist: true, sync: true, announce: false }),
      setEffectBodyClass: (effectBodyClass) => this.applyEffectBodyClass(effectBodyClass || ''),
      toggleTheme: () => this.toggleTheme(),
      syncFromServer: () => this.syncThemeFromServer(true),
    };
  }

  normalizeTheme(theme) {
    return AVAILABLE_THEMES.includes(theme) ? theme : 'light';
  }

  parseBodyEffects() {
    try {
      const raw = this.body?.dataset.activeEffects || '[]';
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (_) {
      return [];
    }
  }

  getThemeMeta(theme) {
    return THEME_UI_META[theme] || { name: theme || '浅色', icon: 'fa-palette' };
  }

  hexToRgb(hex) {
    const normalized = String(hex || '').trim().replace('#', '');
    if (!/^[0-9a-fA-F]{6}$/.test(normalized)) {
      return '99, 102, 241';
    }
    const value = parseInt(normalized, 16);
    const red = (value >> 16) & 255;
    const green = (value >> 8) & 255;
    const blue = value & 255;
    return `${red}, ${green}, ${blue}`;
  }

  buildDerivedThemeVariables(theme) {
    const preset = THEME_VARIABLE_PRESETS[theme];
    if (!preset) {
      return {};
    }
    const primary = preset['--color-primary'] || '#6366f1';
    const primaryHover = preset['--color-primary-hover'] || primary;
    const background = preset['--color-background'] || '#ffffff';
    const backgroundAlt = preset['--color-background-alt'] || background;
    const cardBg = preset['--color-card-bg'] || '#ffffff';
    const text = preset['--color-text'] || '#0f172a';
    const textLight = preset['--color-text-light'] || text;
    const border = preset['--color-border'] || '#cbd5e1';
    const borderLight = preset['--color-border-light'] || border;
    const primaryRgb = this.hexToRgb(primary);

    return {
      '--color-primary-light': `color-mix(in srgb, ${primary} 72%, white)`,
      '--color-primary-dark': `color-mix(in srgb, ${primaryHover} 82%, black)`,
      '--color-accent': `color-mix(in srgb, ${primary} 52%, #f59e0b)`,
      '--color-accent-light': `color-mix(in srgb, ${primary} 32%, white 68%)`,
      '--color-accent-dark': `color-mix(in srgb, ${primaryHover} 56%, black 44%)`,
      '--color-surface': `color-mix(in srgb, ${cardBg} 82%, transparent)`,
      '--color-surface-elevated': `color-mix(in srgb, ${cardBg} 94%, transparent)`,
      '--color-surface-secondary': `color-mix(in srgb, ${backgroundAlt} 74%, ${cardBg} 26%)`,
      '--color-surface-tertiary': `color-mix(in srgb, ${primary} 10%, ${cardBg} 90%)`,
      '--color-text-primary': text,
      '--color-text-secondary': textLight,
      '--color-text-tertiary': preset['--color-text-muted'] || textLight,
      '--color-text-inverse': '#ffffff',
      '--color-border-secondary': `color-mix(in srgb, ${border} 86%, ${borderLight} 14%)`,
      '--gradient-primary': `linear-gradient(135deg, ${primary}, color-mix(in srgb, ${primary} 56%, ${preset['--color-secondary'] || primaryHover}))`,
      '--gradient-text': `linear-gradient(135deg, ${text}, color-mix(in srgb, ${primary} 34%, ${text} 66%))`,
      '--color-primary-rgb': primaryRgb,
      '--color-primary-alpha-20': `rgba(${primaryRgb}, 0.2)`,
      '--color-primary-alpha-40': `rgba(${primaryRgb}, 0.4)`,
      '--font-family-primary': preset['--font-family-base'],
      '--font-family-mono': 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, Courier New, monospace',
      '--spacing-1': '0.25rem',
      '--spacing-2': '0.5rem',
      '--spacing-3': '0.75rem',
      '--spacing-4': '1rem',
      '--spacing-6': '1.5rem',
      '--spacing-8': '2rem',
      '--spacing-20': '5rem',
      '--radius-sm': '0.5rem',
      '--radius-md': '0.75rem',
      '--radius-lg': '1rem',
      '--radius-full': '9999px',
      '--shadow-sm': '0 6px 18px -12px rgba(15, 23, 42, 0.22)',
      '--shadow-md': '0 12px 28px -16px rgba(15, 23, 42, 0.26)',
      '--shadow-lg': '0 18px 40px -20px rgba(15, 23, 42, 0.34)',
      '--z-index-fixed': '60',
      '--font-size-sm': '0.875rem',
      '--font-size-base': '1rem',
      '--font-size-lg': '1.125rem',
      '--font-size-xl': '1.25rem',
      '--font-size-2xl': '1.5rem',
      '--font-size-3xl': '1.875rem',
      '--line-height-relaxed': '1.9',
      '--easing-smooth': 'cubic-bezier(0.4, 0, 0.2, 1)',
      '--duration-fast': '150ms',
      '--duration-normal': '300ms',
    };
  }

  getThemeVariables(theme) {
    const preset = THEME_VARIABLE_PRESETS[theme] || THEME_VARIABLE_PRESETS.light;
    return {
      ...preset,
      ...this.buildDerivedThemeVariables(theme),
    };
  }

  applyThemeVariables(theme) {
    const variables = this.getThemeVariables(theme);
    Object.entries(variables).forEach(([name, value]) => {
      this.root.style.setProperty(name, value);
    });
  }

  refreshThemeStylesheet() {
    if (!this.themeLink) {
      return;
    }
    this.themeLink.href = `/api/v1/theme/variables.css?theme=${encodeURIComponent(this.theme)}&v=${Date.now()}`;
  }

  refreshHighlightTheme(theme = this.theme) {
    if (!this.hljsThemeLink) {
      return;
    }
    const nextHref = DARK_MODE_THEMES.has(theme)
      ? this.hljsThemeLink.dataset.themeDark
      : this.hljsThemeLink.dataset.themeLight;
    if (nextHref) {
      this.hljsThemeLink.href = nextHref;
    }
  }

  getNextTheme(theme) {
    const currentIndex = AVAILABLE_THEMES.indexOf(this.normalizeTheme(theme));
    const nextIndex = currentIndex >= 0 ? (currentIndex + 1) % AVAILABLE_THEMES.length : 0;
    return AVAILABLE_THEMES[nextIndex];
  }

  updateThemeToggleUI(theme) {
    const currentMeta = this.getThemeMeta(theme);
    const nextTheme = this.getNextTheme(theme);
    const nextMeta = this.getThemeMeta(nextTheme);

    const desktopToggle = document.getElementById('desktop-theme-toggle');
    const desktopIcon = document.getElementById('desktop-theme-icon');
    if (desktopToggle && desktopIcon) {
      desktopIcon.className = `fas ${currentMeta.icon}`;
      desktopToggle.title = `当前：${currentMeta.name}主题，点击切换到${nextMeta.name}主题`;
      desktopToggle.setAttribute('aria-label', `当前${currentMeta.name}主题，点击切换到${nextMeta.name}主题`);
    }

    const mobileToggle = document.getElementById('mobile-theme-toggle');
    const mobileIcon = document.getElementById('mobile-theme-icon');
    const mobileLabel = document.getElementById('mobile-theme-label');
    if (mobileToggle && mobileIcon && mobileLabel) {
      mobileIcon.className = `fas ${currentMeta.icon}`;
      mobileLabel.textContent = `当前：${currentMeta.name}主题，切换到${nextMeta.name}主题`;
      mobileToggle.setAttribute('aria-label', `当前${currentMeta.name}主题，点击切换到${nextMeta.name}主题`);
    }
  }

  applyTheme(theme, options = {}) {
    const normalizedTheme = this.normalizeTheme(theme);
    this.theme = normalizedTheme;
    this.root.dataset.currentTheme = normalizedTheme;
    this.root.dataset.glassIntensity = this.body?.dataset.glassIntensity || this.root.dataset.glassIntensity || 'medium';
    if (this.body) {
      this.body.dataset.currentTheme = normalizedTheme;
      this.body.dataset.activeTheme = normalizedTheme;
    }

    this.root.classList.remove(...AVAILABLE_THEMES);
    this.root.classList.add(normalizedTheme);
    this.root.classList.toggle('dark', DARK_MODE_THEMES.has(normalizedTheme));
    if (this.body) {
      this.body.classList.remove(...AVAILABLE_THEMES);
      this.body.classList.add(normalizedTheme);
      this.body.classList.toggle('dark', DARK_MODE_THEMES.has(normalizedTheme));
    }

    if (options.applyVariables !== false) {
      this.applyThemeVariables(normalizedTheme);
    }
    if (options.reloadCss !== false) {
      this.refreshThemeStylesheet();
    }
    this.refreshHighlightTheme(normalizedTheme);
    this.updateThemeToggleUI(normalizedTheme);

    if (options.sync) {
      this.persistThemeToBackend(normalizedTheme);
    }

    if (options.announce) {
      this.showThemeToast(`已切换到${this.getThemeMeta(normalizedTheme).name}主题`);
    }

    window.dispatchEvent(new CustomEvent('themeChanged', {
      detail: { theme: normalizedTheme, source: options.source || 'site-shell' },
    }));
  }

  toggleTheme() {
    const nextTheme = this.getNextTheme(this.theme);
    this.applyTheme(nextTheme, { persist: true, sync: true, announce: true });
  }

  async persistThemeToBackend(theme) {
    if (!this.canPersistTheme || !this.themeCsrfToken) {
      return;
    }
    if (this.themeSyncInFlight) {
      return this.themeSyncInFlight;
    }

    const formData = new FormData();
    formData.append('theme', theme);
    formData.append('csrf_token', this.themeCsrfToken);

    this.themeSyncInFlight = fetch('/api/v1/theme/update', {
      method: 'POST',
      body: formData,
      credentials: 'include',
    }).then((response) => {
      if (response && (response.status === 401 || response.status === 403)) {
        this.canPersistTheme = false;
      }
      return response;
    }).catch(() => null).finally(() => {
      this.themeSyncInFlight = null;
    });

    return this.themeSyncInFlight;
  }

  applyEffectBodyClass(className) {
    if (!this.body) return;
    Array.from(this.body.classList)
      .filter((value) => value.startsWith('atmosphere-'))
      .forEach((value) => this.body.classList.remove(value));
    if (className) {
      this.body.classList.add(className);
      this.body.dataset.effectBodyClass = className;
    } else {
      this.body.dataset.effectBodyClass = '';
    }
  }

  async applyEffects(effects) {
    this.activeEffects = Array.isArray(effects) ? effects : [];
    if (this.body) {
      this.body.dataset.activeEffects = JSON.stringify(this.activeEffects);
    }
    if (!window.effectManager) {
      return;
    }
    window.effectManager.stopAll();
    for (const effectName of this.activeEffects) {
      await window.effectManager.startEffect(effectName);
    }
  }

  applyBackground() {
    if (!this.body) return;
    this.body.classList.remove('bg-none', 'bg-gradient', 'bg-gradient-1', 'bg-gradient-2', 'bg-gradient-3', 'bg-gradient-4', 'bg-custom', 'bg-page-cover');
    this.body.style.backgroundImage = '';
    this.body.style.backgroundSize = '';
    this.body.style.backgroundPosition = '';
    this.body.style.backgroundRepeat = '';
    this.body.style.backgroundAttachment = '';
    this.body.style.removeProperty('--page-bg-image');

    if (this.pageBackgroundUrl) {
      this.body.classList.add('bg-page-cover');
      this.body.style.setProperty('--page-bg-image', `url('${this.pageBackgroundUrl}')`);
      this.body.style.backgroundSize = 'cover';
      this.body.style.backgroundPosition = 'center';
      this.body.style.backgroundRepeat = 'no-repeat';
      this.body.style.backgroundAttachment = 'fixed';
      return;
    }

    switch (this.backgroundType) {
      case 'gradient':
      case 'gradient1':
        this.body.classList.add('bg-gradient', 'bg-gradient-1');
        this.body.style.backgroundImage = 'linear-gradient(135deg, #6c7ef8 0%, #4b5fcf 100%)';
        break;
      case 'gradient2':
        this.body.classList.add('bg-gradient', 'bg-gradient-2');
        this.body.style.backgroundImage = 'linear-gradient(135deg, #ffb5c2 0%, #ffd8b8 100%)';
        break;
      case 'gradient3':
        this.body.classList.add('bg-gradient', 'bg-gradient-3');
        this.body.style.backgroundImage = 'linear-gradient(135deg, #c0f4ed 0%, #d8e6ff 100%)';
        break;
      case 'gradient4':
        this.body.classList.add('bg-gradient', 'bg-gradient-4');
        this.body.style.backgroundImage = 'linear-gradient(135deg, #ffe7c8 0%, #ffd1d1 100%)';
        break;
      case 'custom':
        if (this.backgroundUrl) {
          this.body.classList.add('bg-custom');
          this.body.style.backgroundImage = `url('${this.backgroundUrl}')`;
          this.body.style.backgroundSize = 'cover';
          this.body.style.backgroundPosition = 'center';
          this.body.style.backgroundRepeat = 'no-repeat';
          this.body.style.backgroundAttachment = 'fixed';
          break;
        }
      default:
        this.body.classList.add('bg-none');
        break;
    }
  }

  applyHomepageMode() {
    if (!this.body) return;
    const modeClassMap = {
      default: 'homepage-default',
      fullscreen_gallery: 'homepage-fullscreen-gallery',
      fullscreen_video: 'homepage-fullscreen-video',
    };
    Object.values(modeClassMap).forEach((className) => this.body.classList.remove(className));
    this.body.classList.remove('homepage-gallery', 'homepage-video');
    this.body.classList.add(modeClassMap[this.homepageMode] || `homepage-${String(this.homepageMode).replace(/_/g, '-')}`);
  }

  showThemeToast(message) {
    if (!this.body) return;
    let toast = document.querySelector('.theme-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.className = 'theme-toast';
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      this.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('is-visible');
    clearTimeout(this.themeToastTimer);
    this.themeToastTimer = window.setTimeout(() => {
      toast.classList.remove('is-visible');
    }, 1800);
  }

  bindThemeToggle() {
    document.getElementById('desktop-theme-toggle')?.addEventListener('click', () => this.toggleTheme());
    document.getElementById('mobile-theme-toggle')?.addEventListener('click', () => this.toggleTheme());
  }

  bindMobileMenu() {
    const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
    const mobileNavMenu = document.getElementById('mobile-nav-menu');
    const menuIcon = document.getElementById('menu-icon');
    const mobilePagesToggle = document.getElementById('mobile-pages-toggle');
    const mobilePagesMenu = document.getElementById('mobile-pages-menu');
    const mobilePagesIcon = document.getElementById('mobile-pages-icon');

    mobileMenuToggle?.addEventListener('click', () => {
      if (!mobileNavMenu || !menuIcon) return;
      const isOpen = !mobileNavMenu.classList.contains('hidden');
      mobileNavMenu.classList.toggle('hidden', isOpen);
      menuIcon.classList.toggle('fa-bars', isOpen);
      menuIcon.classList.toggle('fa-times', !isOpen);
      mobileMenuToggle.setAttribute('aria-expanded', String(!isOpen));
    });

    mobileNavMenu?.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        mobileNavMenu.classList.add('hidden');
        menuIcon?.classList.add('fa-bars');
        menuIcon?.classList.remove('fa-times');
        mobileMenuToggle?.setAttribute('aria-expanded', 'false');
      });
    });

    mobilePagesToggle?.addEventListener('click', (event) => {
      event.preventDefault();
      if (!mobilePagesMenu || !mobilePagesIcon) return;
      const isOpen = !mobilePagesMenu.classList.contains('hidden');
      mobilePagesMenu.classList.toggle('hidden', isOpen);
      mobilePagesIcon.classList.toggle('fa-chevron-down', isOpen);
      mobilePagesIcon.classList.toggle('fa-chevron-up', !isOpen);
      mobilePagesToggle.setAttribute('aria-expanded', String(!isOpen));
    });
  }

  bindBackToTop() {
    const button = document.getElementById('back-to-top');
    if (!button) return;
    const onScroll = () => {
      button.classList.toggle('visible', window.scrollY > 360);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    button.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: this.isReducedMotion ? 'auto' : 'smooth' });
    });
  }

  bindVisibilitySync() {
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        this.syncThemeFromServer(false);
      }
    });
    window.addEventListener('focus', () => this.syncThemeFromServer(false));
  }

  async syncThemeFromServer(forceCssReload) {
    try {
      const response = await fetch('/api/v1/theme/sync', {
        credentials: 'include',
        cache: 'no-store',
      });
      if (!response.ok) return;
      const payload = await response.json();

      if (payload.theme && payload.theme !== this.theme) {
        this.applyTheme(payload.theme, { persist: true, sync: false, announce: false, source: 'theme-sync' });
      }
      const nextEffectBodyClass = Array.isArray(payload.resolved_effects?.body_classes) && payload.resolved_effects.body_classes.length > 0
        ? payload.resolved_effects.body_classes[0]
        : '';
      this.applyEffectBodyClass(nextEffectBodyClass);
      // 特效配置未变化时不重启画布，避免每次回到标签页都重建特效与监听器
      // 排序后比较：服务端返回顺序不同不应触发无谓重建
      const nextEffects = Array.isArray(payload.resolved_effects?.effects)
        ? [...payload.resolved_effects.effects].sort()
        : [];
      const currentEffects = [...this.activeEffects].sort();
      if (JSON.stringify(nextEffects) !== JSON.stringify(currentEffects)) {
        await this.applyEffects(payload.resolved_effects?.effects || []);
      }
      this.backgroundType = payload.background?.type || 'none';
      this.backgroundUrl = payload.background?.custom_url || '';
      this.pageBackgroundUrl = this.body?.dataset.pageBackgroundUrl || this.pageBackgroundUrl || '';
      this.homepageMode = payload.homepage_mode || this.homepageMode;
      this.applyBackground();
      this.applyHomepageMode();
      if (this.body) {
        this.body.dataset.glassIntensity = payload.glass_intensity || this.body.dataset.glassIntensity || 'medium';
      }
      if (forceCssReload && this.themeLink) {
        this.refreshThemeStylesheet();
      }
    } catch (_) {
      // ignore sync failures
    }
  }

  bindProfileMotion(root = document) {
    if (this.isReducedMotion) {
      return;
    }

    const scope = root && root.querySelectorAll ? root : document;
    const cards = scope.querySelectorAll('[data-profile-motion]');
    cards.forEach((card) => {
      if (card.dataset.motionBound === 'true') {
        return;
      }

      let rafId = null;

      const resetMotion = () => {
        card.style.setProperty('--motion-shift-x', '0px');
        card.style.setProperty('--motion-shift-y', '0px');
      };

      const updateMotion = (event) => {
        if (rafId) {
          cancelAnimationFrame(rafId);
        }
        rafId = requestAnimationFrame(() => {
          const rect = card.getBoundingClientRect();
          const offsetX = event.clientX - rect.left;
          const offsetY = event.clientY - rect.top;
          const xRatio = rect.width ? (offsetX / rect.width - 0.5) : 0;
          const yRatio = rect.height ? (offsetY / rect.height - 0.5) : 0;
          const shiftX = Math.max(-10, Math.min(10, xRatio * 12));
          const shiftY = Math.max(-8, Math.min(8, yRatio * 10));
          card.style.setProperty('--motion-shift-x', `${shiftX}px`);
          card.style.setProperty('--motion-shift-y', `${shiftY}px`);
        });
      };

      card.addEventListener('pointermove', updateMotion, { passive: true });
      card.addEventListener('pointerleave', () => {
        if (rafId) {
          cancelAnimationFrame(rafId);
          rafId = null;
        }
        resetMotion();
      });

      resetMotion();
      card.dataset.motionBound = 'true';
    });
  }

  setupHighlighting() {
    const highlight = (root = document) => {
      if (!window.hljs) return;
      const scope = root && root.querySelectorAll ? root : document;
      scope.querySelectorAll('pre code').forEach((block) => {
        if (!block || block.dataset.hljsApplied === 'true') return;
        try {
          window.hljs.highlightElement(block);
          block.dataset.hljsApplied = 'true';
          block.closest('pre')?.classList.add('hljs-ready');
        } catch (_) {
          block.classList.add('hljs');
          block.dataset.hljsApplied = 'true';
          block.closest('pre')?.classList.add('hljs-ready');
        }
      });
    };

    window.safeHighlightCodeBlocks = highlight;
    highlight(document);
    document.body?.addEventListener('htmx:afterSwap', (event) => {
      const swapTarget = event?.detail?.target || document;
      highlight(swapTarget);
      this.bindProfileMotion(swapTarget);
    });
  }
}

function bootstrapSiteShell() {
  if (window.siteShellController) {
    return window.siteShellController;
  }
  const controller = new SiteShellController();
  controller.init();
  window.siteShellController = controller;
  return controller;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrapSiteShell, { once: true });
} else {
  bootstrapSiteShell();
}
