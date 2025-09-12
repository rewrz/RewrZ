/**
 * RewrZ 主页动画系统
 * 实现视差滚动、微交互和性能优化的动画效果
 */

class HomepageAnimations {
  constructor() {
    this.isInitialized = false;
    this.rafId = null;
    this.scrollY = 0;
    this.ticking = false;
    this.observers = new Map();
    this.parallaxElements = [];
    this.timelineItems = [];
    
    // 性能监控
    this.performanceMetrics = {
      frameCount: 0,
      lastTime: performance.now(),
      fps: 60
    };
    
    this.init();
  }
  
  /**
   * 初始化动画系统
   */
  init() {
    if (this.isInitialized) return;
    
    this.setupParallaxElements();
    this.setupTimelineAnimation();
    this.setupScrollListeners();
    this.setupIntersectionObservers();
    this.setupMicroInteractions();
    this.setupPerformanceMonitoring();
    
    this.isInitialized = true;
    
    // 标记页面已加载
    document.body.classList.add('loaded');
    
    console.log('🚀 Homepage animations initialized');
  }
  
  /**
   * 设置视差滚动元素
   */
  setupParallaxElements() {
    const parallaxLayers = document.querySelectorAll('.parallax-layer');
    
    parallaxLayers.forEach((layer, index) => {
      this.parallaxElements.push({
        element: layer,
        speed: 0.2 + (index * 0.1), // 不同层级不同速度
        offset: 0
      });
    });
  }
  
  /**
   * 设置时间轴动画
   */
  setupTimelineAnimation() {
    this.timelineItems = Array.from(document.querySelectorAll('.timeline-item'));
    
    // 为每个时间轴项目添加延迟动画
    this.timelineItems.forEach((item, index) => {
      item.style.transitionDelay = `${index * 0.1}s`;
    });
  }
  
  /**
   * 设置滚动监听器
   */
  setupScrollListeners() {
    // 使用 passive 监听器优化性能
    window.addEventListener('scroll', this.handleScroll.bind(this), { passive: true });
    window.addEventListener('resize', this.handleResize.bind(this), { passive: true });
  }
  
  /**
   * 设置交叉观察器
   */
  setupIntersectionObservers() {
    // 时间轴项目观察器
    const timelineObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('animate-in');
            // 添加微交互效果
            this.addMicroInteraction(entry.target);
          }
        });
      },
      {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
      }
    );
    
    this.timelineItems.forEach(item => {
      timelineObserver.observe(item);
    });
    
    this.observers.set('timeline', timelineObserver);
    
    // 图片懒加载观察器
    const imageObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const img = entry.target;
            if (img.dataset.src) {
              img.src = img.dataset.src;
              img.classList.add('loaded');
              imageObserver.unobserve(img);
            }
          }
        });
      },
      { threshold: 0.1 }
    );
    
    document.querySelectorAll('img[data-src]').forEach(img => {
      imageObserver.observe(img);
    });
    
    this.observers.set('images', imageObserver);
  }
  
  /**
   * 设置微交互
   */
  setupMicroInteractions() {
    // 社交链接悬浮效果
    document.querySelectorAll('.hero-social-link').forEach(link => {
      link.addEventListener('mouseenter', this.handleSocialLinkHover.bind(this));
      link.addEventListener('mouseleave', this.handleSocialLinkLeave.bind(this));
    });
    
    // 时间轴内容卡片交互
    document.querySelectorAll('.timeline-content').forEach(content => {
      content.addEventListener('mouseenter', this.handleCardHover.bind(this));
      content.addEventListener('mouseleave', this.handleCardLeave.bind(this));
    });
    
    // 标签悬浮效果
    document.querySelectorAll('.post-tag').forEach(tag => {
      tag.addEventListener('mouseenter', this.handleTagHover.bind(this));
    });
  }
  
  /**
   * 设置性能监控
   */
  setupPerformanceMonitoring() {
    // 监控 FPS
    const monitorFPS = () => {
      const now = performance.now();
      this.performanceMetrics.frameCount++;
      
      if (now - this.performanceMetrics.lastTime >= 1000) {
        this.performanceMetrics.fps = Math.round(
          (this.performanceMetrics.frameCount * 1000) / (now - this.performanceMetrics.lastTime)
        );
        this.performanceMetrics.frameCount = 0;
        this.performanceMetrics.lastTime = now;
        
        // 如果 FPS 过低，降低动画质量
        if (this.performanceMetrics.fps < 30) {
          document.body.classList.add('low-performance');
        } else {
          document.body.classList.remove('low-performance');
        }
      }
      
      requestAnimationFrame(monitorFPS);
    };
    
    requestAnimationFrame(monitorFPS);
  }
  
  /**
   * 处理滚动事件
   */
  handleScroll() {
    this.scrollY = window.pageYOffset;
    
    if (!this.ticking) {
      requestAnimationFrame(this.updateAnimations.bind(this));
      this.ticking = true;
    }
  }
  
  /**
   * 处理窗口大小变化
   */
  handleResize() {
    // 重新计算视差元素
    this.setupParallaxElements();
  }
  
  /**
   * 更新动画
   */
  updateAnimations() {
    this.updateParallax();
    this.updateScrollProgress();
    this.ticking = false;
  }
  
  /**
   * 更新视差效果
   */
  updateParallax() {
    const viewportHeight = window.innerHeight;
    
    this.parallaxElements.forEach(({ element, speed }) => {
      const rect = element.getBoundingClientRect();
      
      // 只在元素可见时计算视差
      if (rect.bottom >= 0 && rect.top <= viewportHeight) {
        const yPos = -(this.scrollY * speed);
        element.style.transform = `translate3d(0, ${yPos}px, 0)`;
      }
    });
  }
  
  /**
   * 更新滚动进度
   */
  updateScrollProgress() {
    const scrollProgress = Math.min(
      this.scrollY / (document.documentElement.scrollHeight - window.innerHeight),
      1
    );
    
    // 更新 CSS 自定义属性
    document.documentElement.style.setProperty('--scroll-progress', scrollProgress);
  }
  
  /**
   * 社交链接悬浮处理
   */
  handleSocialLinkHover(event) {
    const link = event.currentTarget;
    
    // 添加浮动动画
    link.classList.add('anim-float');
    
    // 创建粒子效果
    this.createParticleEffect(link);
  }
  
  /**
   * 社交链接离开处理
   */
  handleSocialLinkLeave(event) {
    const link = event.currentTarget;
    link.classList.remove('anim-float');
  }
  
  /**
   * 卡片悬浮处理
   */
  handleCardHover(event) {
    const card = event.currentTarget;
    
    // 添加倾斜效果
    card.addEventListener('mousemove', this.handleCardMouseMove.bind(this));
  }
  
  /**
   * 卡片离开处理
   */
  handleCardLeave(event) {
    const card = event.currentTarget;
    
    // 重置变换
    card.style.transform = '';
    card.removeEventListener('mousemove', this.handleCardMouseMove.bind(this));
  }
  
  /**
   * 卡片鼠标移动处理
   */
  handleCardMouseMove(event) {
    const card = event.currentTarget;
    const rect = card.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    
    const rotateX = (y - centerY) / 10;
    const rotateY = (centerX - x) / 10;
    
    card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-4px)`;
  }
  
  /**
   * 标签悬浮处理
   */
  handleTagHover(event) {
    const tag = event.currentTarget;
    
    // 创建涟漪效果
    this.createRippleEffect(tag, event);
  }
  
  /**
   * 添加微交互效果
   */
  addMicroInteraction(element) {
    // 添加弹跳进入效果
    element.classList.add('anim-bounceIn');
    
    // 为内部元素添加延迟动画
    const children = element.querySelectorAll('.post-title, .post-excerpt, .post-meta');
    children.forEach((child, index) => {
      child.classList.add('anim-fadeInUp');
      child.style.animationDelay = `${index * 0.1}s`;
    });
  }
  
  /**
   * 创建粒子效果
   */
  createParticleEffect(element) {
    const rect = element.getBoundingClientRect();
    const particleCount = 6;
    
    for (let i = 0; i < particleCount; i++) {
      const particle = document.createElement('div');
      particle.className = 'particle';
      particle.style.cssText = `
        position: fixed;
        width: 4px;
        height: 4px;
        background: var(--color-primary);
        border-radius: 50%;
        pointer-events: none;
        z-index: 9999;
        left: ${rect.left + rect.width / 2}px;
        top: ${rect.top + rect.height / 2}px;
      `;
      
      document.body.appendChild(particle);
      
      // 动画粒子
      const angle = (i / particleCount) * Math.PI * 2;
      const velocity = 50 + Math.random() * 50;
      const vx = Math.cos(angle) * velocity;
      const vy = Math.sin(angle) * velocity;
      
      particle.animate([
        { transform: 'translate(0, 0) scale(1)', opacity: 1 },
        { transform: `translate(${vx}px, ${vy}px) scale(0)`, opacity: 0 }
      ], {
        duration: 800,
        easing: 'cubic-bezier(0.25, 0.46, 0.45, 0.94)'
      }).onfinish = () => {
        particle.remove();
      };
    }
  }
  
  /**
   * 创建涟漪效果
   */
  createRippleEffect(element, event) {
    const rect = element.getBoundingClientRect();
    const ripple = document.createElement('div');
    
    const size = Math.max(rect.width, rect.height);
    const x = event.clientX - rect.left - size / 2;
    const y = event.clientY - rect.top - size / 2;
    
    ripple.style.cssText = `
      position: absolute;
      width: ${size}px;
      height: ${size}px;
      left: ${x}px;
      top: ${y}px;
      background: radial-gradient(circle, rgba(255,255,255,0.3) 0%, transparent 70%);
      border-radius: 50%;
      transform: scale(0);
      pointer-events: none;
      z-index: 1;
    `;
    
    element.style.position = 'relative';
    element.style.overflow = 'hidden';
    element.appendChild(ripple);
    
    ripple.animate([
      { transform: 'scale(0)', opacity: 1 },
      { transform: 'scale(1)', opacity: 0 }
    ], {
      duration: 600,
      easing: 'ease-out'
    }).onfinish = () => {
      ripple.remove();
    };
  }
  
  /**
   * 销毁动画系统
   */
  destroy() {
    // 移除事件监听器
    window.removeEventListener('scroll', this.handleScroll.bind(this));
    window.removeEventListener('resize', this.handleResize.bind(this));
    
    // 断开观察器
    this.observers.forEach(observer => observer.disconnect());
    this.observers.clear();
    
    // 取消动画帧
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
    }
    
    this.isInitialized = false;
    console.log('🛑 Homepage animations destroyed');
  }
}

// 自动初始化
let homepageAnimations;

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    homepageAnimations = new HomepageAnimations();
  });
} else {
  homepageAnimations = new HomepageAnimations();
}

// 导出供外部使用
window.HomepageAnimations = HomepageAnimations;
window.homepageAnimations = homepageAnimations;

// 页面卸载时清理
window.addEventListener('beforeunload', () => {
  if (homepageAnimations) {
    homepageAnimations.destroy();
  }
});