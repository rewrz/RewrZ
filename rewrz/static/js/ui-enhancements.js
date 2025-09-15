/**
 * UI增强功能
 * 提供流畅的交互体验和视觉细节优化
 */

class UIEnhancements {
    constructor() {
        this.init();
    }
    
    init() {
        this.setupPageLoader();
        this.setupScrollEffects();
        this.setupLazyLoading();
        this.setupAnimations();
        this.setupBackToTop();
        this.setupTooltips();
        this.setupDropdowns();
        this.setupNotifications();
        this.setupKeyboardNavigation();
    }
    
    // 页面加载器
    setupPageLoader() {
        window.addEventListener('load', () => {
            const loader = document.querySelector('.page-loader');
            if (loader) {
                loader.classList.add('fade-out');
                setTimeout(() => {
                    loader.remove();
                }, 500);
            }
        });
    }
    
    // 滚动效果
    setupScrollEffects() {
        let ticking = false;
        
        const updateScrollEffects = () => {
            const scrollY = window.scrollY;
            
            // 导航栏滚动效果
            const navbar = document.querySelector('.navbar');
            if (navbar) {
                if (scrollY > 50) {
                    navbar.classList.add('scrolled');
                } else {
                    navbar.classList.remove('scrolled');
                }
            }
            
            // 滚动进度指示器
            const scrollIndicator = document.querySelector('.scroll-indicator');
            if (scrollIndicator) {
                const winScroll = document.body.scrollTop || document.documentElement.scrollTop;
                const height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
                const scrolled = (winScroll / height) * 100;
                scrollIndicator.style.width = scrolled + '%';
            }
            
            // 时间轴项目动画
            this.animateTimelineItems();
            
            ticking = false;
        };
        
        window.addEventListener('scroll', () => {
            if (!ticking) {
                requestAnimationFrame(updateScrollEffects);
                ticking = true;
            }
        });
        
        // 创建滚动进度指示器
        if (!document.querySelector('.scroll-indicator')) {
            const indicator = document.createElement('div');
            indicator.className = 'scroll-indicator';
            document.body.appendChild(indicator);
        }
    }
    
    // 时间轴项目动画
    animateTimelineItems() {
        const items = document.querySelectorAll('.timeline-item:not(.animate-in)');
        const windowHeight = window.innerHeight;
        
        items.forEach(item => {
            const rect = item.getBoundingClientRect();
            if (rect.top < windowHeight * 0.8) {
                item.classList.add('animate-in');
            }
        });
    }
    
    // 懒加载
    setupLazyLoading() {
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        img.src = img.dataset.src;
                        img.classList.add('loaded');
                        observer.unobserve(img);
                    }
                });
            });
            
            document.querySelectorAll('img[data-src]').forEach(img => {
                img.classList.add('lazy-image');
                imageObserver.observe(img);
            });
        }
    }
    
    // 动画设置
    setupAnimations() {
        // 检查用户是否偏好减少动画
        const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        
        if (!prefersReducedMotion) {
            // 为新加载的内容添加动画
            const observer = new MutationObserver(mutations => {
                mutations.forEach(mutation => {
                    mutation.addedNodes.forEach(node => {
                        if (node.nodeType === 1) { // Element node
                            const cards = node.querySelectorAll ? node.querySelectorAll('.timeline-card') : [];
                            cards.forEach((card, index) => {
                                card.style.animationDelay = `${index * 0.1}s`;
                                card.classList.add('fade-in-up');
                            });
                        }
                    });
                });
            });
            
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        }
    }
    
    // 返回顶部按钮
    setupBackToTop() {
        let backToTopBtn = document.querySelector('.back-to-top');
        
        if (!backToTopBtn) {
            backToTopBtn = document.createElement('button');
            backToTopBtn.className = 'back-to-top';
            backToTopBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
            backToTopBtn.setAttribute('aria-label', '返回顶部');
            document.body.appendChild(backToTopBtn);
        }
        
        // 显示/隐藏按钮
        window.addEventListener('scroll', () => {
            if (window.scrollY > 300) {
                backToTopBtn.classList.add('visible');
            } else {
                backToTopBtn.classList.remove('visible');
            }
        });
        
        // 点击返回顶部
        backToTopBtn.addEventListener('click', () => {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }
    
    // 工具提示
    setupTooltips() {
        const tooltipElements = document.querySelectorAll('[data-tooltip]');
        
        tooltipElements.forEach(element => {
            let tooltip = null;
            
            element.addEventListener('mouseenter', (e) => {
                tooltip = document.createElement('div');
                tooltip.className = 'tooltip';
                tooltip.textContent = element.dataset.tooltip;
                tooltip.style.cssText = `
                    position: absolute;
                    background: var(--color-text);
                    color: var(--color-background);
                    padding: 8px 12px;
                    border-radius: 6px;
                    font-size: 14px;
                    white-space: nowrap;
                    z-index: 1000;
                    opacity: 0;
                    transform: translateY(10px);
                    transition: all 0.2s ease;
                    pointer-events: none;
                `;
                
                document.body.appendChild(tooltip);
                
                const rect = element.getBoundingClientRect();
                tooltip.style.left = rect.left + (rect.width / 2) - (tooltip.offsetWidth / 2) + 'px';
                tooltip.style.top = rect.top - tooltip.offsetHeight - 8 + 'px';
                
                setTimeout(() => {
                    tooltip.style.opacity = '1';
                    tooltip.style.transform = 'translateY(0)';
                }, 10);
            });
            
            element.addEventListener('mouseleave', () => {
                if (tooltip) {
                    tooltip.style.opacity = '0';
                    tooltip.style.transform = 'translateY(10px)';
                    setTimeout(() => {
                        if (tooltip && tooltip.parentNode) {
                            tooltip.parentNode.removeChild(tooltip);
                        }
                    }, 200);
                }
            });
        });
    }
    
    // 下拉菜单
    setupDropdowns() {
        document.addEventListener('click', (e) => {
            const dropdown = e.target.closest('.dropdown');
            
            if (dropdown) {
                const toggle = dropdown.querySelector('.dropdown-toggle');
                const menu = dropdown.querySelector('.dropdown-menu');
                
                if (e.target === toggle || toggle.contains(e.target)) {
                    e.preventDefault();
                    dropdown.classList.toggle('open');
                    
                    // 更新 aria-expanded
                    const expanded = dropdown.classList.contains('open');
                    toggle.setAttribute('aria-expanded', expanded);
                }
            } else {
                // 点击外部关闭所有下拉菜单
                document.querySelectorAll('.dropdown.open').forEach(dropdown => {
                    dropdown.classList.remove('open');
                    const toggle = dropdown.querySelector('.dropdown-toggle');
                    if (toggle) {
                        toggle.setAttribute('aria-expanded', 'false');
                    }
                });
            }
        });
    }
    
    // 通知系统
    setupNotifications() {
        window.showNotification = (message, type = 'info', duration = 3000) => {
            const notification = document.createElement('div');
            notification.className = `notification notification-${type}`;
            notification.innerHTML = `
                <div class="notification-content">
                    <span class="notification-message">${message}</span>
                    <button class="notification-close" aria-label="关闭">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `;
            
            notification.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: var(--color-card-bg);
                border: 1px solid var(--color-border);
                border-radius: 8px;
                padding: 16px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                z-index: 1000;
                min-width: 300px;
                max-width: 400px;
            `;
            
            // 类型样式
            if (type === 'success') {
                notification.style.borderLeftColor = '#10b981';
            } else if (type === 'error') {
                notification.style.borderLeftColor = '#ef4444';
            } else if (type === 'warning') {
                notification.style.borderLeftColor = '#f59e0b';
            } else {
                notification.style.borderLeftColor = '#3b82f6';
            }
            
            document.body.appendChild(notification);
            
            // 显示动画
            setTimeout(() => notification.classList.add('show'), 10);
            
            // 关闭按钮
            const closeBtn = notification.querySelector('.notification-close');
            closeBtn.addEventListener('click', () => {
                this.hideNotification(notification);
            });
            
            // 自动关闭
            if (duration > 0) {
                setTimeout(() => {
                    this.hideNotification(notification);
                }, duration);
            }
            
            return notification;
        };
    }
    
    hideNotification(notification) {
        notification.classList.add('hide');
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }
    
    // 键盘导航
    setupKeyboardNavigation() {
        document.addEventListener('keydown', (e) => {
            // ESC 键关闭模态框和下拉菜单
            if (e.key === 'Escape') {
                document.querySelectorAll('.modal.open').forEach(modal => {
                    modal.classList.remove('open');
                });
                
                document.querySelectorAll('.dropdown.open').forEach(dropdown => {
                    dropdown.classList.remove('open');
                    const toggle = dropdown.querySelector('.dropdown-toggle');
                    if (toggle) {
                        toggle.setAttribute('aria-expanded', 'false');
                    }
                });
            }
            
            // Ctrl/Cmd + K 打开搜索
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                const searchInput = document.querySelector('.search-input');
                if (searchInput) {
                    searchInput.focus();
                }
            }
        });
    }
    
    // 添加加载状态
    addLoadingState(element, text = '加载中...') {
        element.classList.add('loading');
        element.disabled = true;
        element.dataset.originalText = element.textContent;
        element.textContent = text;
    }
    
    // 移除加载状态
    removeLoadingState(element) {
        element.classList.remove('loading');
        element.disabled = false;
        if (element.dataset.originalText) {
            element.textContent = element.dataset.originalText;
            delete element.dataset.originalText;
        }
    }
    
    // 平滑滚动到元素
    scrollToElement(element, offset = 0) {
        const rect = element.getBoundingClientRect();
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const targetTop = rect.top + scrollTop - offset;
        
        window.scrollTo({
            top: targetTop,
            behavior: 'smooth'
        });
    }
}

// 初始化UI增强功能
document.addEventListener('DOMContentLoaded', () => {
    window.uiEnhancements = new UIEnhancements();
});

// 导出类供其他模块使用
export default UIEnhancements;