/**
 * UI增强功能
 * 提供流畅的交互体验和视觉细节优化
 *
 * 说明：
 * - 懒加载依赖模板输出 img[data-src]；
 * - 键盘导航仅保留 Ctrl/Cmd+K 聚焦站内搜索框；
 * - 死代码（.navbar 滚动态、.timeline-item 入场动画、.page-loader、
 *   .modal/.dropdown Esc 关闭）已按模板现状清理。
 */

class UIEnhancements {
    constructor() {
        this.init();
    }

    init() {
        this.setupLazyLoading();
        this.setupTooltips();
        this.setupNotifications();
        this.setupKeyboardNavigation();
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

    // 工具提示
    setupTooltips() {
        const tooltipElements = document.querySelectorAll('[data-tooltip]');

        tooltipElements.forEach(element => {
            let tooltip = null;

            element.addEventListener('mouseenter', () => {
                tooltip = document.createElement('div');
                tooltip.className = 'tooltip';
                tooltip.setAttribute('role', 'tooltip');
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

    // 通知系统
    setupNotifications() {
        if (window.showNotification) {
            return;
        }
        window.showNotification = (message, type = 'info', duration = 3000) => {
            const notification = document.createElement('div');
            notification.className = `notification notification-${type}`;
            notification.setAttribute('role', 'status');
            // 用文本节点承载消息，避免把调用方传入的内容当作 HTML 解析
            const content = document.createElement('div');
            content.className = 'notification-content';
            const messageSpan = document.createElement('span');
            messageSpan.className = 'notification-message';
            messageSpan.textContent = message;
            const closeBtn = document.createElement('button');
            closeBtn.className = 'notification-close';
            closeBtn.setAttribute('aria-label', '关闭');
            closeBtn.innerHTML = '<i class="fas fa-times"></i>';
            content.append(messageSpan, closeBtn);
            notification.append(content);

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

            // 语义强调色仅用于左侧提示条
            const accentColors = {
                success: '#10b981',
                error: '#ef4444',
                warning: '#f59e0b',
                info: '#3b82f6',
            };
            notification.style.borderLeftColor = accentColors[type] || accentColors.info;
            notification.style.borderLeftWidth = '4px';

            document.body.appendChild(notification);

            // 显示动画
            setTimeout(() => notification.classList.add('show'), 10);

            // 关闭按钮
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
            // Ctrl/Cmd + K 聚焦站内搜索框
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                const searchInput = document.querySelector('.search-input');
                if (searchInput) {
                    e.preventDefault();
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
