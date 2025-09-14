/**
 * RewrZ 动态主题管理系统
 * 支持纪念日氛围模式、明暗主题切换和自定义主题
 */

class ThemeManager {
    constructor() {
        this.currentTheme = 'light';
        this.anniversaryMode = null;
        this.customTheme = null;
        this.effectsContainer = null;
        
        this.init();
    }

    init() {
        this.loadThemeFromStorage();
        this.checkAnniversaryMode();
        this.applyTheme();
        this.bindEvents();
    }

    /**
     * 从本地存储加载主题设置
     */
    loadThemeFromStorage() {
        const savedTheme = localStorage.getItem('rewrz-theme');
        if (savedTheme) {
            this.currentTheme = savedTheme;
        }
    }

    /**
     * 检查纪念日氛围模式
     */
    async checkAnniversaryMode() {
        try {
            const response = await fetch('/api/anniversary-mode/current');
            const data = await response.json();
            
            if (data.active) {
                this.anniversaryMode = data;
                this.applyAnniversaryMode();
            }
        } catch (error) {
            console.log('Anniversary mode check failed:', error);
        }
    }

    /**
     * 应用纪念日氛围模式
     */
    applyAnniversaryMode() {
        if (!this.anniversaryMode) return;

        const { type, name, effects } = this.anniversaryMode;
        
        // 添加纪念日模式类
        document.documentElement.classList.add(`anniversary-${type.toLowerCase()}`);
        
        // 追悼模式：全站灰白
        if (type === 'Mourn') {
            this.applyMournMode();
        }
        
        // 喜庆模式：应用特效
        if (type === 'Festive' && effects) {
            this.applyFestiveEffects(effects);
        }

        // 显示纪念日提示
        this.showAnniversaryNotice(name, type);
    }

    /**
     * 应用追悼模式
     */
    applyMournMode() {
        const style = document.createElement('style');
        style.id = 'mourn-mode-styles';
        style.textContent = `
            .anniversary-mourn {
                filter: grayscale(100%);
            }
            .anniversary-mourn img,
            .anniversary-mourn video {
                filter: grayscale(100%) !important;
            }
            .anniversary-mourn .bg-gradient-to-r,
            .anniversary-mourn .bg-gradient-to-br {
                background: linear-gradient(to right, #6b7280, #9ca3af) !important;
            }
        `;
        document.head.appendChild(style);
    }

    /**
     * 应用喜庆特效
     */
    applyFestiveEffects(effects) {
        if (!this.effectsContainer) {
            this.effectsContainer = document.createElement('div');
            this.effectsContainer.id = 'anniversary-effects';
            this.effectsContainer.className = 'fixed inset-0 pointer-events-none z-40';
            document.body.appendChild(this.effectsContainer);
        }

        effects.forEach(effect => {
            this.loadEffect(effect);
        });
    }

    /**
     * 加载特效
     */
    async loadEffect(effectName) {
        try {
            const effectModule = await import(`/static/js/effects/${effectName}.js`);
            const effect = new effectModule.default(this.effectsContainer);
            effect.start();
        } catch (error) {
            console.log(`Failed to load effect: ${effectName}`, error);
        }
    }

    /**
     * 显示纪念日通知
     */
    showAnniversaryNotice(name, type) {
        // 移除已存在的通知
        const existingNotice = document.querySelector('.anniversary-notice');
        if (existingNotice) {
            existingNotice.remove();
        }
        
        const notice = document.createElement('div');
        notice.className = `fixed top-20 left-1/2 transform -translate-x-1/2 z-50 px-6 py-3 rounded-lg shadow-lg anniversary-notice ${
            type === 'Mourn' ? 'bg-gray-800 text-white' : 'bg-red-600 text-white'
        } transition-all duration-500`;
        notice.innerHTML = `
            <div class="flex items-center space-x-2">
                <span class="text-sm font-medium">${name}</span>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-2 text-xs opacity-70 hover:opacity-100">×</button>
            </div>
        `;
        
        document.body.appendChild(notice);
        
        // 3秒后自动消失
        setTimeout(() => {
            if (notice.parentElement) {
                notice.remove();
            }
        }, 3000);
    }

    /**
     * 切换主题
     */
    toggleTheme() {
        // 纪念日模式优先级最高，不允许切换
        if (this.anniversaryMode) {
            this.showMessage('纪念日氛围模式激活中，无法切换主题');
            return;
        }

        this.currentTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        this.applyTheme();
        this.saveThemeToStorage();
    }

    /**
     * 应用主题
     */
    applyTheme() {
        const html = document.documentElement;
        
        // 移除所有主题类
        html.classList.remove('light', 'dark');
        
        // 应用当前主题
        html.classList.add(this.currentTheme);
        
        // 更新主题切换按钮图标
        this.updateThemeToggleIcon();
        
        // 应用自定义主题变量
        if (this.customTheme) {
            this.applyCustomTheme();
        }
    }

    /**
     * 更新主题切换按钮图标
     */
    updateThemeToggleIcon() {
        const toggleButton = document.getElementById('theme-toggle');
        if (!toggleButton) return;

        const icon = this.currentTheme === 'light' ? 
            `<svg class="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"></path>
            </svg>` :
            `<svg class="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"></path>
            </svg>`;
        
        toggleButton.innerHTML = icon;
    }

    /**
     * 应用自定义主题
     */
    applyCustomTheme() {
        if (!this.customTheme) return;

        const style = document.getElementById('custom-theme-styles') || document.createElement('style');
        style.id = 'custom-theme-styles';
        
        const { primaryColor, secondaryColor, accentColor, fontSize } = this.customTheme;
        
        style.textContent = `
            :root {
                --color-primary: ${primaryColor};
                --color-secondary: ${secondaryColor};
                --color-accent: ${accentColor};
                --font-size-base: ${fontSize}px;
            }
            .bg-primary { background-color: var(--color-primary) !important; }
            .text-primary { color: var(--color-primary) !important; }
            .border-primary { border-color: var(--color-primary) !important; }
            .bg-accent { background-color: var(--color-accent) !important; }
            .text-accent { color: var(--color-accent) !important; }
            body { font-size: var(--font-size-base); }
        `;
        
        if (!document.getElementById('custom-theme-styles')) {
            document.head.appendChild(style);
        }
    }

    /**
     * 加载自定义主题
     */
    async loadCustomTheme() {
        try {
            const response = await fetch('/api/custom-theme');
            const theme = await response.json();
            
            if (theme.active) {
                this.customTheme = theme;
                this.applyCustomTheme();
            }
        } catch (error) {
            console.log('Custom theme load failed:', error);
        }
    }

    /**
     * 保存主题到本地存储
     */
    saveThemeToStorage() {
        localStorage.setItem('rewrz-theme', this.currentTheme);
    }

    /**
     * 显示消息提示
     */
    showMessage(message) {
        // 移除已存在的消息
        const existingToast = document.querySelector('.theme-toast');
        if (existingToast) {
            existingToast.remove();
        }
        
        const toast = document.createElement('div');
        toast.className = 'fixed top-4 left-1/2 transform -translate-x-1/2 z-50 px-4 py-2 bg-gray-800 text-white rounded-lg shadow-lg transition-all duration-300 theme-toast';
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            if (toast.parentElement) {
                toast.remove();
            }
        }, 2000);
    }

    /**
     * 设置主题（供外部调用）
     */
    setTheme(theme) {
        this.currentTheme = theme;
        this.applyTheme();
        this.saveThemeToStorage();
    }

    /**
     * 设置氛围模式（供外部调用）
     */
    setAtmosphere(atmosphere, effects = []) {
        if (atmosphere) {
            this.anniversaryMode = {
                active: true,
                type: atmosphere,
                effects: effects
            };
        } else {
            this.anniversaryMode = null;
        }
        this.applyTheme();
    }

    /**
     * 绑定事件
     */
    bindEvents() {
        // 监听系统主题变化
        if (window.matchMedia) {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            mediaQuery.addListener((e) => {
                if (!localStorage.getItem('rewrz-theme')) {
                    this.currentTheme = e.matches ? 'dark' : 'light';
                    this.applyTheme();
                }
            });
        }

        // 监听主题更新事件
        document.addEventListener('theme-updated', (e) => {
            this.customTheme = e.detail;
            this.applyCustomTheme();
        });

        // 监听纪念日模式更新
        document.addEventListener('anniversary-updated', (e) => {
            this.anniversaryMode = e.detail;
            this.applyAnniversaryMode();
        });
    }
}

// 初始化主题管理器
document.addEventListener('DOMContentLoaded', () => {
    window.themeManager = new ThemeManager();
});

// 导出供其他模块使用
export default ThemeManager;