// 统一响应式导航系统 - 简化版本
class ResponsiveNavigation {
    constructor() {
        this.menuToggle = document.getElementById('mobile-menu-toggle');
        this.mainNav = document.getElementById('main-nav-menu');
        this.mobileThemeToggle = document.getElementById('mobile-theme-toggle');
        
        this.init();
    }

    init() {
        this.bindEvents();
        this.initDropdowns();
    }

    // 初始化所有下拉菜单
    initDropdowns() {
        const dropdowns = document.querySelectorAll('.nav-dropdown');
        
        dropdowns.forEach(dropdown => {
            const toggle = dropdown.querySelector('.nav-dropdown-toggle');
            const menu = dropdown.querySelector('.nav-dropdown-menu');
            
            if (toggle && menu) {
                // 设置初始状态
                menu.style.display = 'none';
                toggle.setAttribute('aria-expanded', 'false');

                // 绑定事件
                toggle.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.toggleDropdown(menu, toggle);
                });

                // 点击外部关闭下拉菜单
                document.addEventListener('click', (e) => {
                    if (!dropdown.contains(e.target)) {
                        menu.style.display = 'none';
                        toggle.setAttribute('aria-expanded', 'false');
                        toggle.querySelector('.fa-chevron-down').style.transform = 'rotate(0deg)';
                    }
                });
            }
        });
    }

    // 切换下拉菜单
    toggleDropdown(menu, toggle) {
        const isExpanded = toggle.getAttribute('aria-expanded') === 'true';
        
        if (isExpanded) {
            menu.style.display = 'none';
            toggle.setAttribute('aria-expanded', 'false');
            toggle.querySelector('.fa-chevron-down').style.transform = 'rotate(0deg)';
        } else {
            menu.style.display = 'block';
            toggle.setAttribute('aria-expanded', 'true');
            toggle.querySelector('.fa-chevron-down').style.transform = 'rotate(180deg)';
        }
    }

    // 主题切换功能
    toggleTheme() {
        const currentTheme = localStorage.getItem('user_theme_preference');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        if (newTheme === 'dark') {
            document.documentElement.classList.add('dark');
            localStorage.setItem('user_theme_preference', 'dark');
        } else {
            document.documentElement.classList.remove('dark');
            localStorage.setItem('user_theme_preference', 'light');
        }
    }

    // 切换移动端菜单
    toggleMobileMenu() {
        this.mainNav.classList.toggle('nav-menu-open');
        
        // 更新汉堡菜单图标
        if (this.menuToggle) {
            const icon = this.menuToggle.querySelector('i');
            if (icon) {
                if (this.mainNav.classList.contains('nav-menu-open')) {
                    icon.className = 'fas fa-times text-xl';
                    document.body.style.overflow = 'hidden';
                } else {
                    icon.className = 'fas fa-bars text-xl';
                    document.body.style.overflow = '';
                }
            }
        }
    }

    // 绑定事件
    bindEvents() {
        // 移动端菜单切换
        if (this.menuToggle) {
            this.menuToggle.addEventListener('click', () => {
                this.toggleMobileMenu();
            });
        }

        // 移动端主题切换
        if (this.mobileThemeToggle) {
            this.mobileThemeToggle.addEventListener('click', () => {
                this.toggleTheme();
            });
        }

        // 点击外部关闭移动端菜单
        document.addEventListener('click', (e) => {
            if (this.mainNav.classList.contains('nav-menu-open') && 
                !this.mainNav.contains(e.target) && 
                e.target !== this.menuToggle) {
                this.toggleMobileMenu();
            }
        });

        // ESC键关闭菜单
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.mainNav.classList.contains('nav-menu-open')) {
                this.toggleMobileMenu();
            }
        });

        // 窗口大小变化时调整导航
        window.addEventListener('resize', () => {
            this.handleResize();
        });
    }

    // 处理窗口大小变化
    handleResize() {
        if (window.innerWidth >= 768 && this.mainNav.classList.contains('nav-menu-open')) {
            this.toggleMobileMenu();
        }
    }
}

// 初始化导航系统
document.addEventListener('DOMContentLoaded', () => {
    new ResponsiveNavigation();
});

// 导出供其他模块使用
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ResponsiveNavigation;
}