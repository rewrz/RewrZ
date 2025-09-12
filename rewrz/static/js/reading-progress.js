/**
 * 阅读进度条组件
 * 使用requestAnimationFrame优化性能
 */

class ReadingProgress {
    constructor() {
        this.progressBar = null;
        this.contentElement = null;
        this.isInitialized = false;
        this.rafId = null;
        
        // 创建进度条元素
        this.createProgressBar();
        
        // 等待DOM加载完成后初始化
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.init());
        } else {
            this.init();
        }
        
        // 监听滚动事件（使用requestAnimationFrame优化）
        this.handleScroll = this.handleScroll.bind(this);
        window.addEventListener('scroll', () => {
            if (this.rafId) {
                cancelAnimationFrame(this.rafId);
            }
            this.rafId = requestAnimationFrame(this.handleScroll);
        }, { passive: true });
        
        // 监听窗口大小变化
        window.addEventListener('resize', () => {
            if (this.rafId) {
                cancelAnimationFrame(this.rafId);
            }
            this.rafId = requestAnimationFrame(this.handleScroll);
        }, { passive: true });
    }
    
    /**
     * 创建进度条元素
     */
    createProgressBar() {
        // 创建进度条容器
        const progressContainer = document.createElement('div');
        progressContainer.id = 'reading-progress-container';
        progressContainer.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 3px;
            z-index: 9999;
            pointer-events: none;
        `;
        
        // 创建进度条
        this.progressBar = document.createElement('div');
        this.progressBar.id = 'reading-progress-bar';
        this.progressBar.style.cssText = `
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            transition: width 0.1s ease-out;
            box-shadow: 0 0 10px rgba(102, 126, 234, 0.5);
        `;
        
        progressContainer.appendChild(this.progressBar);
        document.body.appendChild(progressContainer);
    }
    
    /**
     * 初始化阅读进度条
     */
    init() {
        // 查找文章内容元素
        this.contentElement = document.querySelector('.post-content') || 
                             document.querySelector('.article-content') || 
                             document.querySelector('article') || 
                             document.body;
        
        if (this.contentElement) {
            this.isInitialized = true;
            this.updateProgress();
        }
    }
    
    /**
     * 处理滚动事件
     */
    handleScroll() {
        if (!this.isInitialized) return;
        
        this.updateProgress();
    }
    
    /**
     * 更新进度条
     */
    updateProgress() {
        if (!this.contentElement || !this.progressBar) return;
        
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
        const progress = Math.max(0, Math.min(100, (scrollTop / scrollHeight) * 100));
        
        // 使用transform来优化性能
        this.progressBar.style.transform = `scaleX(${progress / 100})`;
        this.progressBar.style.transformOrigin = 'left';
    }
    
    /**
     * 平滑滚动到顶部
     */
    scrollToTop() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    }
    
    /**
     * 销毁进度条
     */
    destroy() {
        if (this.rafId) {
            cancelAnimationFrame(this.rafId);
        }
        
        window.removeEventListener('scroll', this.handleScroll);
        window.removeEventListener('resize', this.handleScroll);
        
        const progressContainer = document.getElementById('reading-progress-container');
        if (progressContainer) {
            progressContainer.remove();
        }
        
        this.isInitialized = false;
    }
}

// 初始化阅读进度条
const readingProgress = new ReadingProgress();

// 导出供其他模块使用
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ReadingProgress;
} else if (typeof window !== 'undefined') {
    window.ReadingProgress = ReadingProgress;
}