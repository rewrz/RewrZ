/**
 * RewrZ 增强版动态主题管理系统
 * 支持纪念日氛围模式、明暗主题切换和自定义主题
 */

class EnhancedThemeManager {
    constructor() {
        this.currentTheme = 'light';
        this.anniversaryMode = null;
        this.customTheme = null;
        this.effectManager = null;
        this.effectsStarted = false; // 防止重复启动特效
        
        this.init();
    }

    async init() {
        // 动态导入特效管理器
        try {
            await import('./effects/effect-manager.js');
            // 使用全局实例
            this.effectManager = window.effectManager;
        } catch (error) {
            console.warn('特效管理器加载失败:', error);
        }

        this.loadThemeFromStorage();
        await this.checkAnniversaryMode();
        await this.applyTheme();
        this.bindEvents();
    }

    /**
     * 从本地存储加载主题设置
     */
    loadThemeFromStorage() {
        const savedTheme = localStorage.getItem('rewrz-theme');
        const savedAnniversary = localStorage.getItem('rewrz-anniversary-mode');
        
        if (savedTheme) {
            this.currentTheme = savedTheme;
        }
        
        if (savedAnniversary) {
            try {
                this.anniversaryMode = JSON.parse(savedAnniversary);
            } catch (error) {
                console.warn('纪念日模式数据解析失败:', error);
            }
        }
    }

    /**
     * 保存主题设置到本地存储
     */
    saveThemeToStorage() {
        localStorage.setItem('rewrz-theme', this.currentTheme);
        if (this.anniversaryMode) {
            localStorage.setItem('rewrz-anniversary-mode', JSON.stringify(this.anniversaryMode));
        } else {
            localStorage.removeItem('rewrz-anniversary-mode');
        }
    }

    /**
     * 切换主题
     */
    toggleTheme() {
        // 纪念日模式优先级最高，不允许切换
        if (this.anniversaryMode && this.anniversaryMode.active) {
            this.showMessage('当前处于纪念日氛围模式，无法切换主题');
            return;
        }

        this.currentTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        this.applyTheme();
        this.saveThemeToStorage();
    }

    /**
     * 应用主题
     */
    async applyTheme(theme = null) {
        // 如果传入了主题参数，则使用该主题
        if (theme) {
            this.currentTheme = theme;
        }
        
        const html = document.documentElement;
        const body = document.body;
        
        // 移除所有主题类
        html.classList.remove('light', 'dark');
        body.classList.remove('spring-festival-theme', 'cherry-blossom-theme', 'winter-theme', 'celebration-theme');
        
        // 应用纪念日氛围模式（最高优先级）
        if (this.anniversaryMode && this.anniversaryMode.active) {
            await this.applyAnniversaryMode();
            return;
        }
        
        // 应用明暗主题
        html.classList.add(this.currentTheme);
        
        // 更新主题切换按钮图标
        this.updateThemeToggleIcon();
        
        // 应用自定义主题（如果有）
        if (this.customTheme) {
            this.applyCustomTheme();
        }
    }

    /**
     * 更新主题切换按钮图标
     */
    updateThemeToggleIcon() {
        const lightIcon = document.querySelector('.theme-icon-light');
        const darkIcon = document.querySelector('.theme-icon-dark');
        
        if (lightIcon && darkIcon) {
            if (this.currentTheme === 'dark') {
                lightIcon.classList.add('hidden');
                darkIcon.classList.remove('hidden');
            } else {
                lightIcon.classList.remove('hidden');
                darkIcon.classList.add('hidden');
            }
        }
    }

    /**
     * 检查纪念日模式
     */
    async checkAnniversaryMode() {
        try {
            const response = await fetch('/api/anniversary-mode/current');
            if (response.ok) {
                const data = await response.json();
                if (data.active) {
                    this.anniversaryMode = data;
                    await this.applyAnniversaryMode();
                }
            }
        } catch (error) {
            console.warn('获取纪念日模式失败:', error);
        }
    }

    /**
     * 应用纪念日氛围模式
     */
    async applyAnniversaryMode() {
        if (!this.anniversaryMode || !this.anniversaryMode.active) {
            return;
        }

        const html = document.documentElement;
        const body = document.body;
        
        // 应用纪念日主题类
        if (this.anniversaryMode.theme_class) {
            body.classList.add(this.anniversaryMode.theme_class);
        }
        
        // 应用滤镜效果
        if (this.effectManager && this.anniversaryMode.filter_type) {
            this.effectManager.applyFilter(this.anniversaryMode.filter_type);
        }
        
        // 启动特效（防止重复启动）
        if (this.effectManager && this.anniversaryMode.effects && this.anniversaryMode.effects.length > 0 && !this.effectsStarted) {
            // 逐个启动特效
            for (const effect of this.anniversaryMode.effects) {
                await this.effectManager.startEffect(effect);
            }
            this.effectsStarted = true;
        }
    }

    /**
     * 停用纪念日模式
     */
    async deactivateAnniversaryMode() {
        if (this.anniversaryMode) {
            // 停止特效
            if (this.effectManager) {
                this.effectManager.stopEffect();
                // 移除滤镜效果
                this.effectManager.disableGrayscale();
            }
            
            // 移除主题类
            const body = document.body;
            body.classList.remove('spring-festival-theme', 'cherry-blossom-theme', 'winter-theme', 'celebration-theme', 'grayscale-effect');
            
            this.anniversaryMode = null;
            this.effectsStarted = false; // 重置特效启动标志
            localStorage.removeItem('rewrz-anniversary-mode');
            
            // 重新应用普通主题
            await this.applyTheme();
        }
    }

    /**
     * 应用自定义主题
     */
    applyCustomTheme() {
        if (!this.customTheme) return;
        
        const root = document.documentElement;
        
        // 应用CSS变量
        Object.entries(this.customTheme.variables || {}).forEach(([key, value]) => {
            root.style.setProperty(`--${key}`, value);
        });
    }

    /**
     * 设置自定义主题
     */
    setCustomTheme(themeData) {
        this.customTheme = themeData;
        this.applyCustomTheme();
        localStorage.setItem('rewrz-custom-theme', JSON.stringify(themeData));
    }

    /**
     * 设置主题（供外部调用）
     */
    setTheme(theme) {
        this.applyTheme(theme);
        this.saveThemeToStorage();
    }

    /**
     * 设置氛围模式（供外部调用）
     */
    setAtmosphere(atmosphere, effects = []) {
        if (atmosphere) {
            this.anniversaryMode = {
                active: true,
                theme_class: atmosphere,
                effects: effects
            };
        } else {
            this.anniversaryMode = null;
        }
        this.applyTheme();
        this.saveThemeToStorage();
    }

    /**
     * 绑定事件监听器
     */
    bindEvents() {
        // 监听系统主题变化
        if (window.matchMedia) {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            mediaQuery.addEventListener('change', (e) => {
                if (!this.anniversaryMode || !this.anniversaryMode.active) {
                    this.currentTheme = e.matches ? 'dark' : 'light';
                    this.applyTheme();
                    this.saveThemeToStorage();
                }
            });
        }

        // 监听窗口大小变化，调整特效
        window.addEventListener('resize', () => {
            if (this.effectManager) {
                // 检查effectManager是否有getActiveEffects方法
                if (typeof this.effectManager.getActiveEffects === 'function') {
                    // 重启特效以适应新的窗口大小
                    const activeEffects = this.effectManager.getActiveEffects();
                    if (activeEffects.length > 0) {
                        this.effectManager.stopAll();
                        setTimeout(() => {
                            // 逐个启动每个特效
                            activeEffects.forEach(effect => {
                                this.effectManager.startEffect(effect);
                            });
                        }, 100);
                    }
                }
            }
        });
        
        // 监听DOM变化，为新添加的元素应用灰度效果
        const observer = new MutationObserver((mutations) => {
            if (this.effectManager && document.documentElement.style.filter.includes('grayscale')) {
                // 检查是否有新添加的节点
                let hasNewNodes = false;
                for (const mutation of mutations) {
                    if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                        hasNewNodes = true;
                        break;
                    }
                }
                
                // 如果有新添加的节点，应用灰度效果
                if (hasNewNodes) {
                    setTimeout(() => {
                        this.effectManager.applyGrayscaleToNewElements();
                    }, 0);
                }
            }
        });
        
        // 开始观察DOM变化
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    /**
     * 显示消息提示
     */
    showMessage(message, type = 'info') {
        // 移除已存在的消息
        const existingMessage = document.querySelector('.theme-message');
        if (existingMessage) {
            existingMessage.remove();
        }
        
        const messageEl = document.createElement('div');
        messageEl.className = `fixed top-16 right-4 z-50 p-3 rounded-lg shadow-lg max-w-sm theme-message ${
            type === 'error' ? 'bg-red-500 text-white' : 
            type === 'success' ? 'bg-green-500 text-white' : 
            'bg-blue-500 text-white'
        }`;
        messageEl.textContent = message;
        
        document.body.appendChild(messageEl);
        
        setTimeout(() => {
            if (messageEl.parentElement) {
                messageEl.remove();
            }
        }, 3000);
    }

    /**
     * 获取当前主题信息
     */
    getCurrentTheme() {
        return {
            theme: this.currentTheme,
            anniversaryMode: this.anniversaryMode,
            customTheme: this.customTheme
        };
    }
}

// 创建全局实例
window.themeManager = new EnhancedThemeManager();

// 导出类供其他模块使用
export default EnhancedThemeManager;
