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

class SiteShellController {
  constructor() {
    this.root = document.documentElement;
    this.body = document.body;
    this.themeLink = document.getElementById('theme-variables-link');
    this.theme = this.body?.dataset.currentTheme || this.root.dataset.currentTheme || 'light';
    this.atmosphereClass = this.body?.dataset.atmosphereClass || '';
    this.themeCsrfToken = this.body?.dataset.themeCsrfToken || '';
    this.canPersistTheme = this.body?.dataset.themePersistAllowed === 'true';
    this.backgroundType = this.body?.dataset.backgroundType || 'none';
    this.backgroundUrl = this.body?.dataset.backgroundUrl || '';
    this.homepageMode = this.body?.dataset.homepageMode || 'default';
    this.isReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.themeToastTimer = null;
    this.themeSyncInFlight = null;
  }

  init() {
    this.applyTheme(this.theme, { persist: false, sync: false, announce: false });
    this.applyAtmosphere(this.atmosphereClass);
    this.applyBackground();
    this.applyHomepageMode();
    this.bindThemeToggle();
    this.bindMobileMenu();
    this.bindBackToTop();
    this.bindVisibilitySync();
    this.setupHighlighting();
    window.themeManager = {
      getCurrentTheme: () => this.theme,
      setTheme: (theme) => this.applyTheme(theme, { persist: true, sync: true, announce: false }),
      setAtmosphere: (atmosphereClass) => this.applyAtmosphere(atmosphereClass || ''),
      toggleTheme: () => this.toggleTheme(),
      syncFromServer: () => this.syncThemeFromServer(true),
    };
  }

  normalizeTheme(theme) {
    return AVAILABLE_THEMES.includes(theme) ? theme : 'light';
  }

  getThemeMeta(theme) {
    return THEME_UI_META[theme] || { name: theme || '浅色', icon: 'fa-palette' };
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
    if (this.body) {
      this.body.dataset.currentTheme = normalizedTheme;
      this.body.dataset.activeTheme = normalizedTheme;
    }

    this.root.classList.remove(...AVAILABLE_THEMES);
    this.root.classList.add(normalizedTheme);
    if (this.body) {
      this.body.classList.remove(...AVAILABLE_THEMES);
      this.body.classList.add(normalizedTheme);
    }

    this.updateThemeToggleUI(normalizedTheme);

    if (options.persist !== false) {
      localStorage.setItem('rewrz-theme', normalizedTheme);
      localStorage.setItem('user_theme_preference', normalizedTheme);
    }

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

  applyAtmosphere(className) {
    if (!this.body) return;
    Array.from(this.body.classList)
      .filter((value) => value.startsWith('atmosphere-'))
      .forEach((value) => this.body.classList.remove(value));
    if (className) {
      this.body.classList.add(className);
      this.body.dataset.atmosphereClass = className;
    } else {
      delete this.body.dataset.atmosphereClass;
    }
  }

  applyBackground() {
    if (!this.body) return;
    this.body.classList.remove('bg-none', 'bg-gradient', 'bg-gradient-1', 'bg-gradient-2', 'bg-gradient-3', 'bg-gradient-4', 'bg-custom');
    this.body.style.backgroundImage = '';
    this.body.style.backgroundSize = '';
    this.body.style.backgroundPosition = '';
    this.body.style.backgroundRepeat = '';

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
      const nextAtmosphereClass = payload.atmosphere && payload.atmosphere.normalized
        ? `atmosphere-${payload.atmosphere.normalized}`
        : '';
      this.applyAtmosphere(nextAtmosphereClass);
      this.backgroundType = payload.background?.type || 'none';
      this.backgroundUrl = payload.background?.custom_url || '';
      this.homepageMode = payload.homepage_mode || this.homepageMode;
      this.applyBackground();
      this.applyHomepageMode();
      if (this.body) {
        this.body.dataset.glassIntensity = payload.glass_intensity || this.body.dataset.glassIntensity || 'medium';
      }
      if (forceCssReload && this.themeLink) {
        this.themeLink.href = `/api/v1/theme/variables.css?v=${Date.now()}`;
      }
    } catch (_) {
      // ignore sync failures
    }
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
      highlight(event?.detail?.target || document);
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const controller = new SiteShellController();
  controller.init();
  window.siteShellController = controller;
});
