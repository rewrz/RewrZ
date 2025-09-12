/**
 * 响应式导航和移动端交互功能
 */

class ResponsiveNavigation {
    constructor() {
        this.mobileMenuToggle = null;
        this.mobileNavMenu = null;
        this.searchPanel = null;
        this.categoriesPanel = null;
        this.isMenuOpen = false;
        this.recentSearches = this.loadRecentSearches();
        
        this.init();
    }

    init() {
        this.initMobileMenu();
        this.initSearchPanel();
        this.initCategoriesPanel();
        this.initDropdowns();
        this.initResponsiveAdjustments();
        this.bindEvents();
    }

    /**
     * 初始化移动端菜单
     */
    initMobileMenu() {
        this.mobileMenuToggle = document.getElementById('mobile-menu-toggle');
        this.mobileNavMenu = document.getElementById('mobile-nav-menu');
        
        if (this.mobileMenuToggle && this.mobileNavMenu) {
            this.mobileMenuToggle.addEventListener('click', () => {
                this.toggleMobileMenu();
            });
            
            // 点击菜单外部关闭菜单
            document.addEventListener('click', (e) => {
                if (this.isMenuOpen && 
                    !this.mobileMenuToggle.contains(e.target) && 
                    !this.mobileNavMenu.contains(e.target)) {
                    this.closeMobileMenu();
                }
            });
        }
    }

    toggleMobileMenu() {
        this.isMenuOpen = !this.isMenuOpen;
        
        if (this.isMenuOpen) {
            this.openMobileMenu();
        } else {
            this.closeMobileMenu();
        }
    }

    openMobileMenu() {
        this.mobileNavMenu.classList.add('active');
        this.mobileMenuToggle.setAttribute('aria-expanded', 'true');
        
        // 更新图标
        const icon = this.mobileMenuToggle.querySelector('#menu-icon');
        if (icon) {
            icon.classList.remove('fa-bars');
            icon.classList.add('fa-times');
        }
        
        // 防止背景滚动
        document.body.style.overflow = 'hidden';
    }

    closeMobileMenu() {
        this.isMenuOpen = false;
        this.mobileNavMenu.classList.remove('active');
        this.mobileMenuToggle.setAttribute('aria-expanded', 'false');
        
        // 恢复图标
        const icon = this.mobileMenuToggle.querySelector('#menu-icon');
        if (icon) {
            icon.classList.remove('fa-times');
            icon.classList.add('fa-bars');
        }
        
        // 恢复背景滚动
        document.body.style.overflow = '';
    }

    /**
     * 初始化搜索面板
     */
    initSearchPanel() {
        this.searchPanel = document.getElementById('mobile-search-panel');
        const searchToggle = document.getElementById('mobile-search-toggle');
        const searchClose = document.getElementById('mobile-search-close');
        
        if (searchToggle && this.searchPanel) {
            searchToggle.addEventListener('click', () => {
                this.openSearchPanel();
            });
        }
        
        if (searchClose && this.searchPanel) {
            searchClose.addEventListener('click', () => {
                this.closeSearchPanel();
            });
        }
        
        // 初始化搜索功能
        this.initSearchFeatures();
    }

    openSearchPanel() {
        this.searchPanel.classList.remove('translate-y-full');
        document.body.style.overflow = 'hidden';
        
        // 聚焦搜索输入框
        setTimeout(() => {
            const searchInput = this.searchPanel.querySelector('input[name="q"]');
            if (searchInput) {
                searchInput.focus();
            }
        }, 300);
    }

    closeSearchPanel() {
        this.searchPanel.classList.add('translate-y-full');
        document.body.style.overflow = '';
    }

    initSearchFeatures() {
        const searchInput = this.searchPanel?.querySelector('input[name="q"]');
        if (!searchInput) return;
        
        // 搜索建议
        searchInput.addEventListener('input', (e) => {
            this.handleSearchInput(e.target.value);
        });
        
        // 搜索提交
        const searchForm = this.searchPanel.querySelector('form');
        if (searchForm) {
            searchForm.addEventListener('submit', (e) => {
                const query = searchInput.value.trim();
                if (query) {
                    this.addToRecentSearches(query);
                    this.closeSearchPanel();
                }
            });
        }
        
        // 显示最近搜索
        this.displayRecentSearches();
    }

    handleSearchInput(query) {
        // 这里可以实现搜索建议功能
        if (query.length > 2) {
            // 发送搜索建议请求
            this.fetchSearchSuggestions(query);
        }
    }

    async fetchSearchSuggestions(query) {
        try {
            const response = await fetch(`/api/search/suggestions?q=${encodeURIComponent(query)}`);
            if (response.ok) {
                const suggestions = await response.json();
                this.displaySearchSuggestions(suggestions);
            }
        } catch (error) {
            console.warn('获取搜索建议失败:', error);
        }
    }

    displaySearchSuggestions(suggestions) {
        // 实现搜索建议显示逻辑
        console.log('搜索建议:', suggestions);
    }

    addToRecentSearches(query) {
        this.recentSearches = this.recentSearches.filter(item => item !== query);
        this.recentSearches.unshift(query);
        this.recentSearches = this.recentSearches.slice(0, 5); // 只保留最近5个
        
        localStorage.setItem('rewrz-recent-searches', JSON.stringify(this.recentSearches));
        this.displayRecentSearches();
    }

    loadRecentSearches() {
        try {
            const saved = localStorage.getItem('rewrz-recent-searches');
            return saved ? JSON.parse(saved) : [];
        } catch (error) {
            return [];
        }
    }

    displayRecentSearches() {
        const recentSearchesContainer = document.getElementById('recent-searches');
        const recentSearchesList = document.getElementById('recent-searches-list');
        
        if (!recentSearchesContainer || !recentSearchesList) return;
        
        if (this.recentSearches.length > 0) {
            recentSearchesContainer.classList.remove('hidden');
            recentSearchesList.innerHTML = this.recentSearches.map(query => `
                <button class="flex items-center justify-between w-full p-2 text-left hover:bg-gray-100 dark:hover:bg-gray-700 rounded" 
                        onclick="this.closest('form').querySelector('input[name=q]').value='${query}'; this.closest('form').submit();">
                    <span class="text-gray-700 dark:text-gray-300">${query}</span>
                    <i class="fas fa-arrow-up-right text-gray-400"></i>
                </button>
            `).join('');
        } else {
            recentSearchesContainer.classList.add('hidden');
        }
    }

    /**
     * 初始化分类面板
     */
    initCategoriesPanel() {
        this.categoriesPanel = document.getElementById('mobile-categories-panel');
        const categoriesToggle = document.getElementById('mobile-categories-toggle');
        const categoriesClose = document.getElementById('mobile-categories-close');
        
        if (categoriesToggle && this.categoriesPanel) {
            categoriesToggle.addEventListener('click', () => {
                this.openCategoriesPanel();
            });
        }
        
        if (categoriesClose && this.categoriesPanel) {
            categoriesClose.addEventListener('click', () => {
                this.closeCategoriesPanel();
            });
        }
    }

    openCategoriesPanel() {
        this.categoriesPanel.classList.remove('translate-y-full');
        document.body.style.overflow = 'hidden';
    }

    closeCategoriesPanel() {
        this.categoriesPanel.classList.add('translate-y-full');
        document.body.style.overflow = '';
    }

    /**
     * 初始化下拉菜单
     */
    initDropdowns() {
        const dropdownToggles = document.querySelectorAll('.nav-dropdown-toggle');
        
        dropdownToggles.forEach(toggle => {
            toggle.addEventListener('click', (e) => {
                e.preventDefault();
                this.toggleDropdown(toggle);
            });
        });
        
        // 点击外部关闭下拉菜单
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.nav-dropdown')) {
                this.closeAllDropdowns();
            }
        });
    }

    toggleDropdown(toggle) {
        const isExpanded = toggle.getAttribute('aria-expanded') === 'true';
        
        // 关闭其他下拉菜单
        this.closeAllDropdowns();
        
        if (!isExpanded) {
            toggle.setAttribute('aria-expanded', 'true');
        }
    }

    closeAllDropdowns() {
        const dropdownToggles = document.querySelectorAll('.nav-dropdown-toggle');
        dropdownToggles.forEach(toggle => {
            toggle.setAttribute('aria-expanded', 'false');
        });
    }

    /**
     * 初始化响应式调整
     */
    initResponsiveAdjustments() {
        this.adjustLayoutForDevice();
        this.initScrollBehavior();
    }

    adjustLayoutForDevice() {
        const isMobile = window.innerWidth < 768;
        const isTablet = window.innerWidth >= 768 && window.innerWidth < 1024;
        
        // 根据设备类型调整布局
        if (isMobile) {
            this.enableMobileOptimizations();
        } else if (isTablet) {
            this.enableTabletOptimizations();
        } else {
            this.enableDesktopOptimizations();
        }
    }

    enableMobileOptimizations() {
        // 移动端优化
        const cards = document.querySelectorAll('.modern-card');
        cards.forEach(card => {
            card.style.marginBottom = '16px';
        });
        
        // 调整图片网格
        this.adjustImageGridsForMobile();
    }

    enableTabletOptimizations() {
        // 平板端优化
        const masonryGrid = document.querySelector('.masonry-grid');
        if (masonryGrid) {
            masonryGrid.style.gridTemplateColumns = 'repeat(2, 1fr)';
        }
    }

    enableDesktopOptimizations() {
        // 桌面端优化
        const masonryGrid = document.querySelector('.masonry-grid');
        if (masonryGrid) {
            masonryGrid.style.gridTemplateColumns = 'repeat(auto-fill, minmax(350px, 1fr))';
        }
    }

    adjustImageGridsForMobile() {
        const imageGrids = document.querySelectorAll('.image-grid');
        
        imageGrids.forEach(grid => {
            const imageCount = parseInt(grid.dataset.imageCount);
            
            if (window.innerWidth < 480) {
                // 小屏幕手机
                if (imageCount > 2) {
                    grid.style.gridTemplateColumns = 'repeat(2, 1fr)';
                }
            } else {
                // 大屏幕手机
                if (imageCount === 3) {
                    grid.style.gridTemplateColumns = 'repeat(2, 1fr)';
                } else if (imageCount > 3) {
                    grid.style.gridTemplateColumns = 'repeat(3, 1fr)';
                }
            }
        });
    }

    /**
     * 初始化滚动行为
     */
    initScrollBehavior() {
        let lastScrollY = window.scrollY;
        let ticking = false;
        
        const handleScroll = () => {
            const currentScrollY = window.scrollY;
            const navbar = document.querySelector('.modern-navbar');
            
            if (navbar) {
                if (currentScrollY > lastScrollY && currentScrollY > 100) {
                    // 向下滚动，隐藏导航栏
                    navbar.style.transform = 'translateY(-100%)';
                } else {
                    // 向上滚动，显示导航栏
                    navbar.style.transform = 'translateY(0)';
                }
            }
            
            lastScrollY = currentScrollY;
            ticking = false;
        };
        
        window.addEventListener('scroll', () => {
            if (!ticking) {
                requestAnimationFrame(handleScroll);
                ticking = true;
            }
        });
    }

    /**
     * 绑定事件监听器
     */
    bindEvents() {
        // 窗口大小变化
        window.addEventListener('resize', () => {
            this.handleResize();
        });
        
        // 设备方向变化
        window.addEventListener('orientationchange', () => {
            setTimeout(() => {
                this.handleResize();
            }, 100);
        });
        
        // 键盘事件
        document.addEventListener('keydown', (e) => {
            this.handleKeydown(e);
        });
    }

    handleResize() {
        // 关闭所有打开的面板
        this.closeMobileMenu();
        this.closeSearchPanel();
        this.closeCategoriesPanel();
        this.closeAllDropdowns();
        
        // 重新调整布局
        this.adjustLayoutForDevice();
        
        // 调整图片网格
        if (window.multiFormatInteractions) {
            window.multiFormatInteractions.adjustImageGrid();
        }
    }

    handleKeydown(e) {
        // ESC键关闭所有面板
        if (e.key === 'Escape') {
            this.closeMobileMenu();
            this.closeSearchPanel();
            this.closeCategoriesPanel();
            this.closeAllDropdowns();
        }
        
        // 搜索快捷键
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            if (window.innerWidth < 768) {
                this.openSearchPanel();
            }
        }
    }

    /**
     * 获取当前设备类型
     */
    getDeviceType() {
        const width = window.innerWidth;
        
        if (width < 480) return 'mobile-small';
        if (width < 768) return 'mobile';
        if (width < 1024) return 'tablet';
        if (width < 1200) return 'desktop';
        return 'desktop-large';
    }

    /**
     * 检查是否为触摸设备
     */
    isTouchDevice() {
        return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
    }
}

// 初始化响应式导航
document.addEventListener('DOMContentLoaded', () => {
    window.responsiveNavigation = new ResponsiveNavigation();
});

export default ResponsiveNavigation;