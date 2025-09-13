/**
 * 前端主题切换器
 * 处理用户在前端的明暗主题切换功能
 */

class ThemeSwitcher {
    constructor() {
        this.currentTheme = localStorage.getItem('user-theme') || 'auto';
        this.init();
    }

    init() {
        // 应用保存的主题
        this.applyTheme(this.currentTheme);
        
        // 监听系统主题变化（仅在auto模式下）
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                if (this.currentTheme === 'auto') {
                    this.applySystemTheme();
                }
            });
        }
        
        // 创建主题切换按钮
        this.createThemeToggle();
    }

    applyTheme(theme) {
        const html = document.documentElement;
        const body = document.body;
        
        // 移除所有主题类
        html.classList.remove('theme-light', 'theme-dark', 'theme-auto');
        body.classList.remove('theme-light', 'theme-dark', 'theme-auto');
        
        if (theme === 'auto') {
            this.applySystemTheme();
        } else {
            // 应用指定主题
            html.classList.add(`theme-${theme}`);
            body.classList.add(`theme-${theme}`);
            html.setAttribute('data-theme', theme);
            
            // 更新CSS变量
            this.updateThemeVariables(theme);
        }
        
        this.currentTheme = theme;
        localStorage.setItem('user-theme', theme);
    }

    applySystemTheme() {
        const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        const systemTheme = prefersDark ? 'dark' : 'light';
        
        const html = document.documentElement;
        const body = document.body;
        
        html.classList.add(`theme-${systemTheme}`);
        body.classList.add(`theme-${systemTheme}`);
        html.setAttribute('data-theme', systemTheme);
        
        this.updateThemeVariables(systemTheme);
    }

    updateThemeVariables(theme) {
        const root = document.documentElement;
        
        if (theme === 'dark') {
            // 暗色主题变量
            root.style.setProperty('--color-background', '#0f172a');
            root.style.setProperty('--color-background-alt', '#1e293b');
            root.style.setProperty('--color-text', '#f1f5f9');
            root.style.setProperty('--color-text-light', '#cbd5e1');
            root.style.setProperty('--color-text-muted', '#94a3b8');
            root.style.setProperty('--color-border', '#334155');
            root.style.setProperty('--color-border-light', '#475569');
            root.style.setProperty('--color-card-bg', '#1e293b');
            root.style.setProperty('--color-card-shadow', 'rgba(0, 0, 0, 0.3)');
            root.style.setProperty('--color-nav-bg', 'rgba(15, 23, 42, 0.8)');
            root.style.setProperty('--color-footer-bg', '#1e293b');
        } else {
            // 浅色主题变量
            root.style.setProperty('--color-background', '#ffffff');
            root.style.setProperty('--color-background-alt', '#f8fafc');
            root.style.setProperty('--color-text', '#1e293b');
            root.style.setProperty('--color-text-light', '#64748b');
            root.style.setProperty('--color-text-muted', '#94a3b8');
            root.style.setProperty('--color-border', '#e2e8f0');
            root.style.setProperty('--color-border-light', '#f1f5f9');
            root.style.setProperty('--color-card-bg', '#ffffff');
            root.style.setProperty('--color-card-shadow', 'rgba(0, 0, 0, 0.1)');
            root.style.setProperty('--color-nav-bg', 'rgba(255, 255, 255, 0.8)');
            root.style.setProperty('--color-footer-bg', '#f8fafc');
        }
        
        // 强制更新所有元素
        this.forceUpdateElements();
    }

    forceUpdateElements() {
        // 更新所有可能的元素
        const elementsToUpdate = [
            'body', 'main', 'header', 'nav', 'footer', 'aside',
            '.navbar', '.header', '.main-content', '.content-wrapper', '.footer',
            '.card', '.post-card', '.article-card', '.comment-card',
            '.bg-white', '.bg-gray-50', '.bg-gray-100', '.bg-gray-200',
            '.text-gray-900', '.text-gray-800', '.text-gray-700', '.text-gray-600', '.text-gray-500'
        ];
        
        elementsToUpdate.forEach(selector => {
            const elements = document.querySelectorAll(selector);
            elements.forEach(el => {
                // 触发重绘
                el.style.display = 'none';
                el.offsetHeight; // 强制重排
                el.style.display = '';
            });
        });
    }

    createThemeToggle() {
        // 检查是否已存在主题切换按钮
        if (document.getElementById('theme-toggle')) {
            return;
        }
        
        // 创建主题切换按钮
        const toggleButton = document.createElement('button');
        toggleButton.id = 'theme-toggle';
        toggleButton.className = 'fixed top-4 right-4 z-50 p-3 rounded-full bg-white dark:bg-gray-800 shadow-lg border border-gray-200 dark:border-gray-700 hover:shadow-xl transition-all duration-300';
        toggleButton.innerHTML = this.getThemeIcon();
        toggleButton.title = '切换主题';
        
        // 添加点击事件
        toggleButton.addEventListener('click', () => {
            this.toggleTheme();
        });
        
        // 添加到页面
        document.body.appendChild(toggleButton);
    }

    getThemeIcon() {
        const icons = {
            light: '<i class="fas fa-sun text-yellow-500"></i>',
            dark: '<i class="fas fa-moon text-blue-500"></i>',
            auto: '<i class="fas fa-adjust text-gray-500"></i>'
        };
        return icons[this.currentTheme] || icons.auto;
    }

    toggleTheme() {
        const themes = ['light', 'dark', 'auto'];
        const currentIndex = themes.indexOf(this.currentTheme);
        const nextIndex = (currentIndex + 1) % themes.length;
        const nextTheme = themes[nextIndex];
        
        this.applyTheme(nextTheme);
        
        // 更新按钮图标
        const toggleButton = document.getElementById('theme-toggle');
        if (toggleButton) {
            toggleButton.innerHTML = this.getThemeIcon();
        }
        
        // 显示切换提示
        this.showThemeNotification(nextTheme);
    }

    showThemeNotification(theme) {
        const themeNames = {
            light: '浅色主题',
            dark: '深色主题',
            auto: '自动切换'
        };
        
        // 移除现有通知
        const existingNotification = document.querySelector('.theme-notification');
        if (existingNotification) {
            existingNotification.remove();
        }
        
        // 创建新通知
        const notification = document.createElement('div');
        notification.className = 'theme-notification fixed top-16 right-4 z-50 bg-white dark:bg-gray-800 text-gray-900 dark:text-white px-4 py-2 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700';
        notification.innerHTML = `
            <div class="flex items-center space-x-2">
                ${this.getThemeIcon()}
                <span>已切换到${themeNames[theme]}</span>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // 3秒后自动移除
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }

    // 获取当前主题
    getCurrentTheme() {
        return this.currentTheme;
    }

    // 设置主题（供外部调用）
    setTheme(theme) {
        if (['light', 'dark', 'auto'].includes(theme)) {
            this.applyTheme(theme);
            
            // 更新按钮图标
            const toggleButton = document.getElementById('theme-toggle');
            if (toggleButton) {
                toggleButton.innerHTML = this.getThemeIcon();
            }
        }
    }
}

// 创建全局实例
window.themeSwitcher = new ThemeSwitcher();

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    if (!window.themeSwitcher) {
        window.themeSwitcher = new ThemeSwitcher();
    }
});

// 导出类
window.ThemeSwitcher = ThemeSwitcher;