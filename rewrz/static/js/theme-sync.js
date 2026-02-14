/**
 * 主题同步管理器
 * 负责前端与后台主题设置的实时同步
 */

class ThemeSync {
    constructor() {
        this.syncInterval = null;
        this.lastSyncTime = null;
        this.isPolling = false;
        
        this.init();
    }
    
    init() {
        // 初始同步
        this.syncThemeSettings();
        
        // 启动定期同步（每30秒检查一次）
        this.startPolling();
        
        // 监听页面可见性变化
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                this.syncThemeSettings();
            }
        });
        
        // 监听窗口焦点变化
        window.addEventListener('focus', () => {
            this.syncThemeSettings();
        });
    }
    
    async syncThemeSettings() {
        try {
            const response = await fetch('/api/v1/theme/sync');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            this.applyThemeSettings(data);
            this.lastSyncTime = new Date(data.timestamp);
            
        } catch (error) {
            console.error('主题同步失败:', error);
        }
    }
    
    applyThemeSettings(settings) {
        // 应用主题
        if (settings.theme && window.themeManager) {
            localStorage.setItem('rewrz-theme', settings.theme);
            localStorage.setItem('user_theme_preference', settings.theme);

            // 检查themeManager是否有setTheme方法，如果没有则使用applyTheme
            if (typeof window.themeManager.setTheme === 'function') {
                window.themeManager.setTheme(settings.theme);
            } else if (typeof window.themeManager.applyTheme === 'function') {
                window.themeManager.applyTheme(settings.theme);
            }

            // 主动广播主题变化，确保基础模板里的按钮 UI 同步更新
            window.dispatchEvent(new CustomEvent('themeChanged', {
                detail: { theme: settings.theme, source: 'theme-sync' }
            }));
        }
        
        // 应用氛围模式
        if (settings.atmosphere && window.themeManager) {
            // 检查themeManager是否有setAtmosphere方法
            if (typeof window.themeManager.setAtmosphere === 'function') {
                window.themeManager.setAtmosphere(
                    settings.atmosphere.value,
                    settings.atmosphere.effects || []
                );
            }
        }
        
        // 应用背景图片设置
        if (settings.background) {
            this.applyBackgroundSettings(settings.background);
        }
        
        // 应用主页模式
        if (settings.homepage_mode) {
            this.applyHomepageMode(settings.homepage_mode);
        }
        
        // 触发自定义事件
        window.dispatchEvent(new CustomEvent('themeSync', {
            detail: settings
        }));
    }
    
    applyBackgroundSettings(backgroundSettings) {
        const body = document.body;
        
        // 移除现有的背景类
        body.classList.remove('bg-none', 'bg-gradient', 'bg-custom');
        
        // 根据背景类型应用相应的样式
        if (backgroundSettings.type === 'none') {
            body.classList.add('bg-none');
            body.style.backgroundImage = '';
        } else if (backgroundSettings.type === 'gradient') {
            body.classList.add('bg-gradient');
            body.style.backgroundImage = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
        } else if (backgroundSettings.type === 'custom' && backgroundSettings.custom_url) {
            body.classList.add('bg-custom');
            body.style.backgroundImage = `url('${backgroundSettings.custom_url}')`;
            body.style.backgroundSize = 'cover';
            body.style.backgroundPosition = 'center';
            body.style.backgroundRepeat = 'no-repeat';
        }
    }
    
    applyHomepageMode(mode) {
        const body = document.body;

        const modeClassMap = {
            default: 'homepage-default',
            fullscreen_gallery: 'homepage-fullscreen-gallery',
            fullscreen_video: 'homepage-fullscreen-video'
        };

        // 清理已知的主页模式类
        Object.values(modeClassMap).forEach((cls) => body.classList.remove(cls));
        body.classList.remove('homepage-gallery', 'homepage-video');

        // 添加新的主页模式类
        const normalizedClass = modeClassMap[mode] || `homepage-${String(mode || 'default').replace(/_/g, '-')}`;
        body.classList.add(normalizedClass);
        
        // 如果在主页，重新加载内容
        if (window.location.pathname === '/' || window.location.pathname === '/index') {
            this.reloadHomepageContent(mode);
        }
    }
    
    async reloadHomepageContent(mode) {
        try {
            const response = await fetch(`/?mode=${mode}`, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (response.ok) {
                const html = await response.text();
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                
                // 更新主要内容区域
                const newContent = doc.querySelector('.main-content');
                const currentContent = document.querySelector('.main-content');
                
                if (newContent && currentContent) {
                    currentContent.innerHTML = newContent.innerHTML;
                    
                    // 重新初始化相关功能
                    if (window.multiFormatInteractions) {
                        window.multiFormatInteractions.init();
                    }
                }
            }
        } catch (error) {
            console.error('主页内容重载失败:', error);
        }
    }
    
    startPolling() {
        if (this.isPolling) return;
        
        this.isPolling = true;
        this.syncInterval = setInterval(() => {
            this.syncThemeSettings();
        }, 30000); // 30秒同步一次
    }
    
    stopPolling() {
        if (this.syncInterval) {
            clearInterval(this.syncInterval);
            this.syncInterval = null;
        }
        this.isPolling = false;
    }
    
    // 手动触发同步
    forceSync() {
        return this.syncThemeSettings();
    }
    
    // 获取最后同步时间
    getLastSyncTime() {
        return this.lastSyncTime;
    }
}

// 创建全局实例
window.themeSync = new ThemeSync();

// 导出类供其他模块使用
export default ThemeSync;
