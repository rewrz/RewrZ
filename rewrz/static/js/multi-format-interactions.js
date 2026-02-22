/**
 * 多格式内容交互系统
 * 处理微博、相册、视频、诗词歌赋等多重身份内容的前端交互功能
 * Version 2.0 - 增强版
 */

class MultiFormatInteractions {
    constructor() {
        this.reactionSummaryCache = new Map();
        this.reactionWidgetsBound = new WeakSet();
        this.openReactionMenus = new Map();
        this.speechSynthesis = window.speechSynthesis || null;
        this.speaking = false;
        this.repositionReactionMenus = this.repositionReactionMenus.bind(this);
        this.init();
    }

    init() {
        this.initMicroPosts();
        this.initMicroArchiveActions();
        this.initPhotoAlbums();
        this.initVideoPlayers();
        this.initAudioPlayers();
        this.initMediaPlayers();
        this.initLazyLoading();
        this.initInfiniteScroll();
        this.initImageGallery();
        this.initResponsiveGrid();
        this.adjustImageGrid();
        this.initReactionSystem();
        this.initPoetryFeatures();
        this.initGalleryFeatures();
        this.initVideoFeatures();
        this.initLightboxFromDataset();
        this.initMicroDetailActions();
        this.initPoetryAutoScroll();
        this.initVideoTheaterMode();
        this.initReadingProgress();
        this.initFloatingTocPanels();
        this.initTocHighlight();
        this.initKeyboardNavigation();
        this.bindGlobalHtmxHooks();
        this.bindReactionMenuDismiss();
        window.addEventListener('resize', () => this.adjustImageGrid(), { passive: true });
    }

    /**
     * 初始化微博功能
     */
    initMicroPosts() {
        // 仅处理显式标记为可折叠的微博内容，避免破坏详情页正文HTML结构
        document.querySelectorAll('.micro-content[data-micro-collapsible="true"]').forEach((content) => {
            const fullText = (content.textContent || '').trim();
            const maxChars = Number(content.dataset.maxChars || '180');
            if (!fullText || fullText.length <= maxChars) return;
            if (content.dataset.microBound === '1') return;

            content.dataset.microBound = '1';
            content.classList.add('micro-collapsible', 'is-collapsed');

            const toggle = document.createElement('button');
            toggle.type = 'button';
            toggle.className = 'micro-expand-btn mt-2 text-xs font-semibold text-blue-600 hover:text-blue-700';
            toggle.textContent = '展开';

            toggle.addEventListener('click', () => {
                const collapsed = content.classList.toggle('is-collapsed');
                toggle.textContent = collapsed ? '展开' : '收起';
            });

            content.insertAdjacentElement('afterend', toggle);
        });
    }

    bindGlobalHtmxHooks() {
        if (document.body.dataset.multiFormatHtmxBound === '1') return;
        document.body.dataset.multiFormatHtmxBound = '1';

        document.body.addEventListener('htmx:afterSwap', (event) => {
            const rawTarget = (event && event.detail && event.detail.target) ? event.detail.target : null;
            const scope = rawTarget && rawTarget.isConnected ? rawTarget : document;
            this.initMicroArchiveActions(scope);
            this.initReactionWidgets(scope);
            this.initLightboxFromDataset(scope);
            this.initFloatingTocPanels(scope);
        });
    }

    bindReactionMenuDismiss() {
        if (document.body.dataset.reactionMenuDismissBound === '1') return;
        document.body.dataset.reactionMenuDismissBound = '1';

        document.addEventListener('click', (event) => {
            if (event.target && event.target.closest('[data-reaction-widget]')) return;
            this.closeAllReactionMenus();
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                this.closeAllReactionMenus();
            }
        });

        window.addEventListener('resize', this.repositionReactionMenus, { passive: true });
        window.addEventListener('scroll', this.repositionReactionMenus, { passive: true, capture: true });
    }

    closeReactionMenu(menu) {
        if (!menu) return;
        menu.classList.add('hidden');
        menu.dataset.open = '0';
        menu.style.left = '';
        menu.style.top = '';
        menu.style.visibility = '';
        this.openReactionMenus.delete(menu);
    }

    closeAllReactionMenus(exceptMenu = null) {
        document.querySelectorAll('[data-reaction-menu]').forEach((menu) => {
            if (exceptMenu && menu === exceptMenu) return;
            this.closeReactionMenu(menu);
        });
    }

    positionReactionMenu(menu, toggle) {
        if (!menu || !toggle) return;
        const toggleRect = toggle.getBoundingClientRect();
        const margin = 10;
        const menuRect = menu.getBoundingClientRect();
        const menuWidth = Math.min(menuRect.width || 300, window.innerWidth - margin * 2);
        const menuHeight = menuRect.height || 92;

        let left = toggleRect.left + (toggleRect.width / 2) - (menuWidth / 2);
        left = Math.max(margin, Math.min(left, window.innerWidth - menuWidth - margin));

        let top = toggleRect.top - menuHeight - 8;
        let placement = 'top';
        if (top < margin) {
            top = Math.min(window.innerHeight - menuHeight - margin, toggleRect.bottom + 8);
            placement = 'bottom';
        }

        menu.style.left = `${Math.round(left)}px`;
        menu.style.top = `${Math.round(top)}px`;
        menu.dataset.placement = placement;
    }

    openReactionMenu(menu, toggle) {
        if (!menu || !toggle) return;
        this.closeAllReactionMenus(menu);
        menu.classList.remove('hidden');
        menu.dataset.open = '1';
        menu.style.visibility = 'hidden';
        this.positionReactionMenu(menu, toggle);
        menu.style.visibility = 'visible';
        this.openReactionMenus.set(menu, toggle);
    }

    toggleReactionMenu(menu, toggle) {
        if (!menu || !toggle) return;
        const isHidden = menu.classList.contains('hidden');
        if (!isHidden) {
            this.closeReactionMenu(menu);
            return;
        }
        this.openReactionMenu(menu, toggle);
    }

    repositionReactionMenus() {
        if (!this.openReactionMenus.size) return;
        this.openReactionMenus.forEach((toggle, menu) => {
            if (!document.body.contains(menu) || !document.body.contains(toggle) || menu.classList.contains('hidden')) {
                this.openReactionMenus.delete(menu);
                return;
            }
            this.positionReactionMenu(menu, toggle);
        });
    }

    initMicroArchiveActions(root = document) {
        const scope = root && root.querySelectorAll ? root : document;

        scope.querySelectorAll('[data-micro-comments-toggle]').forEach((toggle) => {
            if (toggle.dataset.bound === '1') return;
            toggle.dataset.bound = '1';

            toggle.addEventListener('click', async () => {
                const selector = toggle.dataset.target || '';
                if (!selector) return;
                const panel = document.querySelector(selector);
                if (!panel) return;

                const isOpen = !panel.classList.contains('hidden');
                if (isOpen) {
                    panel.classList.add('hidden');
                    toggle.classList.remove('text-sky-600', 'dark:text-sky-300');
                    return;
                }

                panel.classList.remove('hidden');
                toggle.classList.add('text-sky-600', 'dark:text-sky-300');

                if (panel.dataset.loaded === '1') {
                    this.initReactionWidgets(panel);
                    return;
                }

                panel.innerHTML = `
                    <div class="mt-3 flex justify-center">
                        <span class="inline-flex items-center rounded-full border border-sky-200 bg-white px-3 py-1 text-xs text-sky-700 dark:border-sky-700 dark:bg-slate-900 dark:text-sky-300">
                            <i class="fas fa-spinner fa-spin mr-2"></i>加载评论中...
                        </span>
                    </div>
                `;

                const url = toggle.dataset.url;
                if (!url) return;

                try {
                    const response = await fetch(url, {
                        credentials: 'same-origin',
                        headers: { 'HX-Request': 'true' },
                    });
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    const html = await response.text();
                    panel.innerHTML = html;
                    panel.dataset.loaded = '1';
                    if (window.htmx && typeof window.htmx.process === 'function') {
                        window.htmx.process(panel);
                    }
                    this.initReactionWidgets(panel);
                } catch (error) {
                    panel.innerHTML = `
                        <div class="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300">
                            加载评论失败，请稍后重试。
                        </div>
                    `;
                    console.error('加载微博评论失败:', error);
                }
            });
        });

        scope.querySelectorAll('[data-micro-share-btn]').forEach((btn) => {
            if (btn.dataset.bound === '1') return;
            btn.dataset.bound = '1';
            btn.addEventListener('click', async () => {
                const title = btn.dataset.shareTitle || document.title;
                const rawUrl = btn.dataset.shareUrl || window.location.pathname;
                const shareUrl = rawUrl.startsWith('http')
                    ? rawUrl
                    : new URL(rawUrl, window.location.origin).toString();

                if (navigator.share) {
                    try {
                        await navigator.share({ title, text: title, url: shareUrl });
                        return;
                    } catch (_) {
                        // ignore cancel
                    }
                }

                try {
                    if (navigator.clipboard && navigator.clipboard.writeText) {
                        await navigator.clipboard.writeText(shareUrl);
                        this.showToast('链接已复制', 'success', 1200);
                        return;
                    }
                } catch (_) {
                    // ignore and fallback
                }
                this.showToast('当前浏览器不支持分享', 'info', 1200);
            });
        });
    }

    /**
     * 初始化相册功能
     */
    initPhotoAlbums() {
        // 相册网格布局
        document.querySelectorAll('.photo-album-grid').forEach(grid => {
            const photos = grid.querySelectorAll('.photo-item');
            const photoCount = photos.length;
            
            // 根据照片数量调整网格布局
            if (photoCount === 1) {
                grid.classList.add('single-photo');
            } else if (photoCount === 2) {
                grid.classList.add('two-photos');
            } else if (photoCount === 3) {
                grid.classList.add('three-photos');
            } else if (photoCount === 4) {
                grid.classList.add('four-photos');
            } else {
                grid.classList.add('many-photos');
            }
        });
    }

    /**
     * 初始化视频播放器
     */
    initVideoPlayers() {
        // 视频播放控制
        document.querySelectorAll('.video-player').forEach(player => {
            const video = player.querySelector('video');
            const playBtn = player.querySelector('.play-btn');
            const pauseBtn = player.querySelector('.pause-btn');
            
            if (video && playBtn) {
                playBtn.addEventListener('click', () => {
                    video.play();
                    playBtn.classList.add('hidden');
                    if (pauseBtn) pauseBtn.classList.remove('hidden');
                });
            }
            
            if (video && pauseBtn) {
                pauseBtn.addEventListener('click', () => {
                    video.pause();
                    pauseBtn.classList.add('hidden');
                    if (playBtn) playBtn.classList.remove('hidden');
                });
            }
        });
    }

    /**
     * 初始化音频播放器
     */
    initAudioPlayers() {
        // 音频播放控制
        document.querySelectorAll('.audio-player').forEach(player => {
            const audio = player.querySelector('audio');
            const playBtn = player.querySelector('.play-btn');
            const pauseBtn = player.querySelector('.pause-btn');
            const progress = player.querySelector('.progress');
            
            if (audio && playBtn) {
                playBtn.addEventListener('click', () => {
                    audio.play();
                    playBtn.classList.add('hidden');
                    if (pauseBtn) pauseBtn.classList.remove('hidden');
                });
            }
            
            if (audio && pauseBtn) {
                pauseBtn.addEventListener('click', () => {
                    audio.pause();
                    pauseBtn.classList.add('hidden');
                    if (playBtn) playBtn.classList.remove('hidden');
                });
            }
            
            if (audio && progress) {
                audio.addEventListener('timeupdate', () => {
                    const percent = (audio.currentTime / audio.duration) * 100;
                    progress.style.width = `${percent}%`;
                });
            }
        });
    }

    /**
     * 初始化媒体播放器（通用）
     */
    initMediaPlayers() {
        // 媒体播放控制
        document.querySelectorAll('.media-player').forEach(player => {
            const media = player.querySelector('video, audio');
            const playBtn = player.querySelector('.play-btn');
            const pauseBtn = player.querySelector('.pause-btn');
            const volumeBtn = player.querySelector('.volume-btn');
            const muteBtn = player.querySelector('.mute-btn');
            
            if (media && playBtn) {
                playBtn.addEventListener('click', () => {
                    media.play();
                    playBtn.classList.add('hidden');
                    if (pauseBtn) pauseBtn.classList.remove('hidden');
                });
            }
            
            if (media && pauseBtn) {
                pauseBtn.addEventListener('click', () => {
                    media.pause();
                    pauseBtn.classList.add('hidden');
                    if (playBtn) playBtn.classList.remove('hidden');
                });
            }
            
            if (media && volumeBtn && muteBtn) {
                volumeBtn.addEventListener('click', () => {
                    media.muted = true;
                    volumeBtn.classList.add('hidden');
                    muteBtn.classList.remove('hidden');
                });
                
                muteBtn.addEventListener('click', () => {
                    media.muted = false;
                    muteBtn.classList.add('hidden');
                    volumeBtn.classList.remove('hidden');
                });
            }
        });
    }

    /**
     * 初始化懒加载
     */
    initLazyLoading() {
        // 图片懒加载
        const images = document.querySelectorAll('img[data-src]');
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.removeAttribute('data-src');
                    observer.unobserve(img);
                }
            });
        });
        
        images.forEach(img => {
            // 检查元素是否存在再观察
            if (img && typeof img.getBoundingClientRect === 'function') {
                imageObserver.observe(img);
            }
        });
    }

    /**
     * 初始化无限滚动
     */
    initInfiniteScroll() {
        const getLoader = () => document.querySelector('[data-infinite-loader="1"]');
        const hasLoader = !!getLoader();
        if (!hasLoader) return;

        const hasHtmx = window.htmx && typeof window.htmx.process === 'function';

        const processHtmxLoader = () => {
            if (!hasHtmx) return;
            document.querySelectorAll('[data-infinite-loader="1"]').forEach((loader) => {
                if (!loader || loader.dataset.htmxProcessed === '1') return;
                loader.dataset.htmxProcessed = '1';
                window.htmx.process(loader);
            });
        };

        // 优先尝试激活 HTMX loader（某些场景下仅依赖自动扫描可能不触发）
        processHtmxLoader();

        // 当 HTMX 可用时，避免并发 fetch 回退与 HTMX 竞争同一个 loader，
        // 否则可能触发 htmx swapError（目标节点已被替换）。
        if (hasHtmx) {
            document.body.addEventListener('htmx:afterSwap', () => {
                processHtmxLoader();
            });
            return;
        }

        // 安全回退：仅在 HTMX 不可用时使用 fetch 兜底继续加载
        const fallbackLoad = async () => {
            const loader = getLoader();
            if (!loader || loader.dataset.loading === '1') return;
            const rect = loader.getBoundingClientRect();
            if (rect.top > window.innerHeight + 200) return;

            const url = loader.getAttribute('hx-get');
            if (!url) return;
            loader.dataset.loading = '1';
            try {
                const response = await fetch(url, {
                    headers: { 'HX-Request': 'true' },
                    credentials: 'same-origin',
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const html = await response.text();
                loader.outerHTML = html;
                this.initMicroArchiveActions(document);
                this.initReactionWidgets(document);
                this.initLightboxFromDataset(document);
            } catch (error) {
                loader.dataset.loading = '0';
                console.error('加载更多内容失败:', error);
            }
        };

        const onScroll = () => { fallbackLoad(); };
        window.addEventListener('scroll', onScroll, { passive: true });
        window.addEventListener('resize', onScroll, { passive: true });
        fallbackLoad();
    }

    appendPosts(posts) {
        const container = document.querySelector('.masonry-grid, .timeline-container');
        if (!container) return;
        
        posts.forEach(post => {
            const postElement = this.createPostElement(post);
            container.appendChild(postElement);
        });
        
        // 重新初始化新添加的元素
        this.initMediaPlayers();
        this.initLazyLoading();
    }

    createPostElement(post) {
        // 这里应该根据post数据创建对应的HTML元素
        // 简化实现，实际应该根据post.format创建不同的卡片
        const div = document.createElement('div');
        div.className = 'modern-card article-card';
        div.innerHTML = `
            <div class="card-body">
                <h3 class="text-xl font-bold mb-2">${post.title}</h3>
                <p class="text-gray-600 mb-4">${post.excerpt || ''}</p>
                <a href="/${post.format_slug}/${post.slug}" class="text-blue-500 hover:text-blue-700">阅读更多</a>
            </div>
        `;
        return div;
    }

    /**
     * 初始化图片画廊
     */
    initImageGallery() {
        // 图片点击放大功能
        document.querySelectorAll('.gallery-image').forEach(img => {
            img.addEventListener('click', () => {
                // 创建模态框显示大图
                const modal = document.createElement('div');
                modal.className = 'fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50';
                modal.innerHTML = `
                    <div class="relative">
                        <img src="${img.src}" class="max-w-full max-h-full" alt="放大图片">
                        <button class="absolute top-4 right-4 text-white text-2xl">&times;</button>
                    </div>
                `;
                
                modal.querySelector('button').addEventListener('click', () => {
                    modal.remove();
                });
                
                document.body.appendChild(modal);
            });
        });
    }

    /**
     * 初始化响应式网格
     */
    initResponsiveGrid() {
        // 响应式网格调整
        const adjustGrid = () => {
            const grids = document.querySelectorAll('.responsive-grid');
            grids.forEach(grid => {
                const containerWidth = grid.offsetWidth;
                let columns = 1;
                
                if (containerWidth > 1200) {
                    columns = 4;
                } else if (containerWidth > 900) {
                    columns = 3;
                } else if (containerWidth > 600) {
                    columns = 2;
                }
                
                grid.style.gridTemplateColumns = `repeat(${columns}, 1fr)`;
            });
        };
        
        // 初始调整
        adjustGrid();
        
        // 窗口大小改变时调整
        window.addEventListener('resize', adjustGrid);
    }

    /**
     * 响应式图片网格调整
     */
    adjustImageGrid() {
        const imageGrids = document.querySelectorAll('.image-grid');
        
        imageGrids.forEach(grid => {
            if (!grid) return;
            
            const imageCount = parseInt(grid.dataset.imageCount);
            const containerWidth = grid.offsetWidth;
            
            if (containerWidth < 400 && imageCount > 2) {
                grid.style.gridTemplateColumns = 'repeat(2, 1fr)';
            } else if (containerWidth < 300 && imageCount > 1) {
                grid.style.gridTemplateColumns = '1fr';
            }
        });
    }

    // ==================== 互动（点赞/表态） ====================
    initReactionSystem() {
        this.initReactionWidgets(document);
    }

    formatCompactCn(value) {
        const num = Number(value);
        if (!Number.isFinite(num)) return '0';
        const absNum = Math.abs(num);
        if (absNum < 10000) return `${Math.floor(absNum)}`;
        if (absNum < 100000000) return `${(absNum / 10000).toFixed(1).replace(/\.0$/, '')}万`;
        return `${(absNum / 100000000).toFixed(1).replace(/\.0$/, '')}亿`;
    }

    async requestJson(url, options = {}) {
        const response = await fetch(url, {
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                ...(options.headers || {}),
            },
            ...options,
        });
        let payload = {};
        try {
            payload = await response.json();
        } catch (_) {
            payload = {};
        }
        if (!response.ok || !payload || payload.success === false) {
            const message = (payload && payload.detail) ? payload.detail : `请求失败 (${response.status})`;
            throw new Error(message);
        }
        return payload;
    }

    getReactionWidgetTarget(widget) {
        const targetType = (widget.dataset.targetType || '').trim().toLowerCase();
        const targetId = Number(widget.dataset.targetId || 0);
        if (!targetType || !Number.isFinite(targetId) || targetId <= 0) return null;
        return { targetType, targetId };
    }

    reactionSummaryText(summary) {
        const total = Number(summary && summary.total_reaction_count ? summary.total_reaction_count : 0);
        if (total <= 0) return '匿名互动已开启，欢迎点赞或表态。';
        if (total < 5) return `${total} 人已表态`;
        return `🔥 ${total} 人已表态`;
    }

    renderReactionWidget(widget, summary) {
        if (!widget || !summary) return;
        widget.dataset.summary = JSON.stringify(summary);

        const likeBtn = widget.querySelector('[data-reaction-like-btn]');
        const likeCountNode = widget.querySelector('[data-like-count]');
        const likeIcon = widget.querySelector('[data-like-icon]');
        const viewerLiked = !!(summary.viewer && summary.viewer.liked);
        const likeCount = Number(summary.like_count || 0);
        if (likeCountNode) {
            likeCountNode.textContent = likeCount > 0 ? `+${this.formatCompactCn(likeCount)}` : '0';
            likeCountNode.dataset.count = String(likeCount);
        }
        if (likeBtn) {
            likeBtn.classList.toggle('text-rose-600', viewerLiked);
            likeBtn.classList.toggle('dark:text-rose-300', viewerLiked);
            likeBtn.dataset.active = viewerLiked ? '1' : '0';
        }
        if (likeIcon) {
            likeIcon.classList.remove('fas', 'far');
            likeIcon.classList.add(viewerLiked ? 'fas' : 'far');
        }

        const reactionMap = summary.reactions || {};
        widget.querySelectorAll('[data-reaction-count]').forEach((node) => {
            const key = node.dataset.reactionCount;
            const value = Number(reactionMap[key] || 0);
            node.textContent = this.formatCompactCn(value);
            node.dataset.count = String(value);
        });

        const totalReactionCount = Number(summary.total_reaction_count || 0);
        widget.querySelectorAll('[data-reaction-total]').forEach((node) => {
            node.dataset.count = String(totalReactionCount);
            if (totalReactionCount > 0) {
                node.textContent = `+${this.formatCompactCn(totalReactionCount)}`;
                node.classList.remove('hidden');
            } else {
                node.textContent = '+0';
                node.classList.add('hidden');
            }
        });

        const viewerReaction = (summary.viewer && summary.viewer.reaction_type) ? summary.viewer.reaction_type : null;
        widget.querySelectorAll('[data-reaction-option]').forEach((btn) => {
            const selected = btn.dataset.reactionOption === viewerReaction;
            btn.dataset.active = selected ? '1' : '0';
            btn.classList.toggle('bg-indigo-50', selected);
            btn.classList.toggle('text-indigo-700', selected);
            btn.classList.toggle('dark:bg-indigo-900/40', selected);
            btn.classList.toggle('dark:text-indigo-300', selected);
        });

        const summaryNode = widget.querySelector('[data-reaction-summary]');
        if (summaryNode) {
            summaryNode.textContent = this.reactionSummaryText(summary);
        }
    }

    async loadReactionWidgetSummary(widget, force = false) {
        const target = this.getReactionWidgetTarget(widget);
        if (!target) return;
        const cacheKey = `${target.targetType}:${target.targetId}`;
        if (!force && this.reactionSummaryCache.has(cacheKey)) {
            this.renderReactionWidget(widget, this.reactionSummaryCache.get(cacheKey));
            return;
        }
        const url = `/api/v1/reactions/summary?target_type=${encodeURIComponent(target.targetType)}&target_id=${target.targetId}`;
        try {
            const payload = await this.requestJson(url, { method: 'GET', headers: {} });
            if (!payload || !payload.summary) return;
            this.reactionSummaryCache.set(cacheKey, payload.summary);
            this.renderReactionWidget(widget, payload.summary);
        } catch (error) {
            console.error('加载互动数据失败:', error);
        }
    }

    initReactionWidgets(root = document) {
        const scope = root && root.querySelectorAll ? root : document;
        const widgets = scope.querySelectorAll('[data-reaction-widget]');
        if (!widgets.length) return;

        widgets.forEach((widget) => {
            if (!widget || this.reactionWidgetsBound.has(widget)) {
                this.loadReactionWidgetSummary(widget, false);
                return;
            }
            this.reactionWidgetsBound.add(widget);

            const menuToggle = widget.querySelector('[data-reaction-menu-toggle]');
            const menu = widget.querySelector('[data-reaction-menu]');
            if (menuToggle && menu) {
                menuToggle.addEventListener('click', (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    this.toggleReactionMenu(menu, menuToggle);
                });
            }

            const likeBtn = widget.querySelector('[data-reaction-like-btn]');
            if (likeBtn) {
                likeBtn.addEventListener('click', async () => {
                    const target = this.getReactionWidgetTarget(widget);
                    if (!target) return;
                    try {
                        const payload = await this.requestJson('/api/v1/reactions/like', {
                            method: 'POST',
                            body: JSON.stringify({
                                target_type: target.targetType,
                                target_id: target.targetId,
                            }),
                        });
                        if (payload && payload.summary) {
                            const cacheKey = `${target.targetType}:${target.targetId}`;
                            this.reactionSummaryCache.set(cacheKey, payload.summary);
                            this.renderReactionWidget(widget, payload.summary);
                        }
                    } catch (error) {
                        this.showToast(error.message || '点赞失败', 'error', 1300);
                    }
                });
            }

            widget.querySelectorAll('[data-reaction-option]').forEach((btn) => {
                btn.addEventListener('click', async () => {
                    const target = this.getReactionWidgetTarget(widget);
                    if (!target) return;
                    const reactionType = btn.dataset.reactionOption || null;
                    try {
                        const payload = await this.requestJson('/api/v1/reactions/react', {
                            method: 'POST',
                            body: JSON.stringify({
                                target_type: target.targetType,
                                target_id: target.targetId,
                                reaction_type: reactionType,
                            }),
                        });
                        if (payload && payload.summary) {
                            const cacheKey = `${target.targetType}:${target.targetId}`;
                            this.reactionSummaryCache.set(cacheKey, payload.summary);
                            this.renderReactionWidget(widget, payload.summary);
                        }
                        if (menu) this.closeReactionMenu(menu);
                    } catch (error) {
                        this.showToast(error.message || '表态失败', 'error', 1300);
                    }
                });
            });

            this.loadReactionWidgetSummary(widget, false);
        });
    }

    updateInlineCommentCount(postId, delta = 0) {
        if (!postId) return;
        const nodes = document.querySelectorAll(
            `[data-comment-count-for="${postId}"], [data-micro-inline-count="${postId}"]`
        );
        nodes.forEach((node) => {
            const current = parseInt(node.dataset.count || '0', 10) || 0;
            const next = Math.max(0, current + delta);
            node.dataset.count = String(next);
            node.textContent = this.formatCompactCn(next);
        });
    }

    showInlineCommentFeedback(form, message, level = 'info') {
        if (!form) return;
        const postId = form.dataset.postId;
        const feedback = document.querySelector(`[data-inline-comment-feedback="${postId}"]`);
        if (!feedback) return;

        const clsMap = {
            success: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800/60 dark:bg-emerald-900/20 dark:text-emerald-300',
            warning: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800/60 dark:bg-amber-900/20 dark:text-amber-300',
            error: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800/60 dark:bg-rose-900/20 dark:text-rose-300',
            info: 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800/60 dark:bg-sky-900/20 dark:text-sky-300',
        };
        const cls = clsMap[level] || clsMap.info;
        feedback.innerHTML = `<div class="rounded-xl border px-3 py-2 text-xs ${cls}">${message}</div>`;
    }

    handleInlineCommentBeforeRequest(form) {
        if (!form) return;
        const btn = form.querySelector('button[type="submit"]');
        if (btn) {
            btn.disabled = true;
            btn.classList.add('opacity-70', 'cursor-not-allowed');
        }
    }

    handleInlineCommentAfterRequest(event, form) {
        const btn = form ? form.querySelector('button[type="submit"]') : null;
        if (btn) {
            btn.disabled = false;
            btn.classList.remove('opacity-70', 'cursor-not-allowed');
        }
        if (!event || !event.detail || !event.detail.xhr || !form) return;

        const xhr = event.detail.xhr;
        const text = typeof xhr.responseText === 'string' ? xhr.responseText : '';
        if (xhr.status < 200 || xhr.status >= 300) return;

        if (text.includes('id="comment-')) {
            const postId = form.dataset.postId;
            this.updateInlineCommentCount(postId, 1);
            const empty = document.getElementById(`micro-comments-empty-${postId}`);
            if (empty) empty.remove();
            this.showInlineCommentFeedback(form, '评论发布成功。', 'success');
            form.reset();
            const panel = document.getElementById(`micro-comments-panel-${postId}`);
            if (panel) this.initReactionWidgets(panel);
        } else if (text.includes('等待审核')) {
            this.showInlineCommentFeedback(form, '评论已提交，待审核后展示。', 'warning');
            form.reset();
        } else if (text.includes('评论提交成功')) {
            this.showInlineCommentFeedback(form, '评论已提交成功。', 'success');
            form.reset();
        } else {
            this.showInlineCommentFeedback(form, '操作已完成。', 'info');
        }
    }

    handleInlineCommentError(event, form) {
        const btn = form ? form.querySelector('button[type="submit"]') : null;
        if (btn) {
            btn.disabled = false;
            btn.classList.remove('opacity-70', 'cursor-not-allowed');
        }
        let message = '评论提交失败，请稍后重试。';
        try {
            const xhr = event && event.detail ? event.detail.xhr : null;
            if (xhr && xhr.responseText) {
                const payload = JSON.parse(xhr.responseText);
                if (payload && payload.detail) message = String(payload.detail);
            }
        } catch (_) {
            // ignore
        }
        this.showInlineCommentFeedback(form, message, 'error');
    }

    // ==================== 诗词功能 ====================
    initPoetryFeatures() {
        this.initPoetryFontSelector();
        this.initPoetrySpeak();
    }

    initPoetryFontSelector() {
        const fontBtns = document.querySelectorAll('.font-btn');
        const contentEl = document.getElementById('poetry-lyrics-content');
        
        if (!contentEl) return;

        fontBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const font = btn.dataset.font;
                
                // 更新按钮状态
                fontBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                // 更新字体
                contentEl.dataset.font = font;
                contentEl.style.fontFamily = font === 'serif' ? '"Noto Serif SC", serif' :
                                              font === 'kai' ? '"KaiTi", "STKaiti", serif' : '';
            });
        });
    }

    initPoetrySpeak() {
        const speakBtn = document.getElementById('poetry-speak-btn');
        const contentEl = document.getElementById('poetry-lyrics-content');
        
        if (!speakBtn || !contentEl || !this.speechSynthesis) return;

        speakBtn.addEventListener('click', () => {
            if (this.speaking) {
                this.speechSynthesis.cancel();
                this.speaking = false;
                speakBtn.innerHTML = '<i class="fas fa-volume-up mr-1"></i>朗诵';
                contentEl.classList.remove('is-speaking');
                return;
            }

            const text = contentEl.textContent.trim();
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'zh-CN';
            utterance.rate = 0.8;
            utterance.pitch = 1;

            utterance.onstart = () => {
                this.speaking = true;
                speakBtn.innerHTML = '<i class="fas fa-stop mr-1"></i>停止';
                contentEl.classList.add('is-speaking');
            };

            utterance.onend = () => {
                this.speaking = false;
                speakBtn.innerHTML = '<i class="fas fa-volume-up mr-1"></i>朗诵';
                contentEl.classList.remove('is-speaking');
            };

            this.speechSynthesis.speak(utterance);
        });
    }

    // ==================== 画廊功能 ====================
    initGalleryFeatures() {
        const fullscreenBtn = document.getElementById('gallery-fullscreen-btn');
        const slideshowBtn = document.getElementById('gallery-slideshow-btn');
        const gallery = document.getElementById('photo-gallery');

        if (fullscreenBtn && gallery) {
            fullscreenBtn.addEventListener('click', () => {
                if (document.fullscreenElement) {
                    document.exitFullscreen();
                } else {
                    gallery.requestFullscreen().catch(() => {});
                }
            });
        }

        if (slideshowBtn && gallery) {
            let slideshowInterval = null;
            
            slideshowBtn.addEventListener('click', () => {
                if (slideshowInterval) {
                    clearInterval(slideshowInterval);
                    slideshowInterval = null;
                    slideshowBtn.innerHTML = '<i class="fas fa-play mr-1"></i>幻灯片';
                    return;
                }

                slideshowBtn.innerHTML = '<i class="fas fa-pause mr-1"></i>暂停';
                const images = gallery.querySelectorAll('[data-lightbox-image]');
                let currentIndex = 0;

                const showNext = () => {
                    if (images.length === 0) return;
                    currentIndex = (currentIndex + 1) % images.length;
                    images[currentIndex].click();
                };

                showNext();
                slideshowInterval = setInterval(showNext, 4000);
            });
        }
    }

    // ==================== 视频功能 ====================
    initVideoFeatures() {
        const pipBtn = document.getElementById('video-pip-btn');
        
        if (pipBtn) {
            const pipSupported =
                'pictureInPictureEnabled' in document &&
                typeof document.pictureInPictureEnabled === 'boolean' &&
                'requestPictureInPicture' in HTMLVideoElement.prototype;

            if (!pipSupported) {
                pipBtn.classList.add('opacity-60', 'cursor-not-allowed');
                pipBtn.setAttribute('aria-disabled', 'true');
                pipBtn.title = '当前浏览器不支持画中画';
                return;
            }

            const setPipButtonState = (active) => {
                pipBtn.innerHTML = active
                    ? '<i class="fas fa-compress mr-1"></i>退出画中画'
                    : '<i class="fas fa-clone mr-1"></i>画中画';
            };

            setPipButtonState(false);

            pipBtn.addEventListener('click', async () => {
                const video = document.querySelector('video');
                if (!video) {
                    this.showToast('暂无视频内容');
                    return;
                }

                try {
                    if (document.pictureInPictureElement) {
                        await document.exitPictureInPicture();
                        setPipButtonState(false);
                    } else if (video.readyState >= 1) {
                        await video.requestPictureInPicture();
                        setPipButtonState(true);
                    } else {
                        this.showToast('视频尚未加载完成');
                    }
                } catch (error) {
                    this.showToast('画中画暂不可用');
                    console.error('画中画操作失败:', error);
                }
            });

            document.addEventListener('leavepictureinpicture', () => {
                setPipButtonState(false);
            });
        }
    }

    initLightboxFromDataset(root = document) {
        const lightboxButtons = Array.from(document.querySelectorAll('[data-lightbox-image]'));
        if (!lightboxButtons.length) return;

        const lightboxGroups = new Map();
        lightboxButtons.forEach((btn, index) => {
            const groupName = btn.dataset.lightboxGroup || `__single_${index}`;
            const position = Number.isNaN(Number(btn.dataset.lightboxPosition))
                ? (lightboxGroups.get(groupName)?.length || 0)
                : Number(btn.dataset.lightboxPosition);
            if (!lightboxGroups.has(groupName)) {
                lightboxGroups.set(groupName, []);
            }
            lightboxGroups.get(groupName)[position] = {
                src: btn.dataset.lightboxImage || '',
                title: btn.dataset.lightboxTitle || '',
            };
            btn.dataset.lightboxGroup = groupName;
            btn.dataset.lightboxPosition = String(position);
        });

        let activeLightbox = null;
        const closeLightbox = () => {
            if (!activeLightbox) return;
            activeLightbox.modal.remove();
            document.removeEventListener('keydown', activeLightbox.onKeydown);
            activeLightbox = null;
            document.body.classList.remove('overflow-hidden');
        };

        const renderLightboxState = (state) => {
            const groups = lightboxGroups.get(state.group) || [];
            const current = groups[state.index];
            if (!current || !current.src) return;

            state.imageEl.src = current.src;
            state.imageEl.alt = current.title || '';
            state.titleEl.textContent = current.title || '';
            state.counterEl.textContent = `${state.index + 1} / ${groups.length}`;
            state.prevEl.style.visibility = groups.length > 1 ? 'visible' : 'hidden';
            state.nextEl.style.visibility = groups.length > 1 ? 'visible' : 'hidden';
        };

        const openLightbox = (group, index) => {
            const groups = lightboxGroups.get(group) || [];
            if (!groups.length) return;
            const normalizedIndex = Math.max(0, Math.min(index, groups.length - 1));

            const modal = document.createElement('div');
            modal.className = 'fixed inset-0 z-[70] bg-black/90 flex items-center justify-center p-4';
            modal.innerHTML = `
                <button type="button" class="absolute top-4 right-6 text-white text-4xl leading-none" data-close-lightbox>&times;</button>
                <button type="button" class="absolute left-3 md:left-6 text-white text-3xl px-3 py-2 bg-black/35 rounded-lg" data-lightbox-prev><i class="fas fa-chevron-left"></i></button>
                <div class="relative max-w-6xl w-full">
                    <img data-lightbox-img class="max-h-[84vh] w-full object-contain rounded-lg" />
                    <div class="mt-3 text-center text-sm text-white/80" data-lightbox-title></div>
                    <div class="mt-1 text-center text-xs text-white/60" data-lightbox-counter></div>
                </div>
                <button type="button" class="absolute right-3 md:right-6 text-white text-3xl px-3 py-2 bg-black/35 rounded-lg" data-lightbox-next><i class="fas fa-chevron-right"></i></button>
            `;
            document.body.appendChild(modal);
            document.body.classList.add('overflow-hidden');

            const state = {
                modal,
                group,
                index: normalizedIndex,
                imageEl: modal.querySelector('[data-lightbox-img]'),
                titleEl: modal.querySelector('[data-lightbox-title]'),
                counterEl: modal.querySelector('[data-lightbox-counter]'),
                prevEl: modal.querySelector('[data-lightbox-prev]'),
                nextEl: modal.querySelector('[data-lightbox-next]'),
                onKeydown: null,
            };

            const move = (step) => {
                const items = lightboxGroups.get(group) || [];
                if (items.length <= 1) return;
                state.index = (state.index + step + items.length) % items.length;
                renderLightboxState(state);
            };

            state.prevEl.addEventListener('click', () => move(-1));
            state.nextEl.addEventListener('click', () => move(1));
            modal.querySelector('[data-close-lightbox]').addEventListener('click', closeLightbox);
            modal.addEventListener('click', (event) => {
                if (event.target === modal) closeLightbox();
            });

            state.onKeydown = (event) => {
                if (!activeLightbox) return;
                if (event.key === 'Escape') {
                    closeLightbox();
                } else if (event.key === 'ArrowLeft') {
                    move(-1);
                } else if (event.key === 'ArrowRight') {
                    move(1);
                }
            };
            document.addEventListener('keydown', state.onKeydown);

            activeLightbox = state;
            renderLightboxState(state);
        };

        const scope = root && root.querySelectorAll ? root : document;
        const scopedButtons = Array.from(scope.querySelectorAll('[data-lightbox-image]'));
        if (scope && scope.matches && scope.matches('[data-lightbox-image]')) {
            scopedButtons.unshift(scope);
        }

        scopedButtons.forEach((btn) => {
            if (btn.dataset.lightboxBound === '1') return;
            btn.dataset.lightboxBound = '1';
            btn.addEventListener('click', function(event) {
                if (event && typeof event.preventDefault === 'function') {
                    event.preventDefault();
                }
                const group = this.dataset.lightboxGroup;
                const position = Number(this.dataset.lightboxPosition || '0');
                openLightbox(group, Number.isNaN(position) ? 0 : position);
            });
        });
    }

    initMicroDetailActions() {
        const microFocusBtn = document.getElementById('micro-focus-btn');
        const microArticle = document.getElementById('micro-article');
        if (microFocusBtn && microArticle) {
            microFocusBtn.addEventListener('click', function() {
                microArticle.classList.toggle('scale-[1.01]');
                microArticle.classList.toggle('shadow-2xl');
                this.classList.toggle('text-indigo-600');
            });
        }
    }

    initPoetryAutoScroll() {
        const poetryScrollToggle = document.getElementById('poetry-scroll-toggle');
        const poetryLyricsContent = document.getElementById('poetry-lyrics-content');
        if (!poetryScrollToggle || !poetryLyricsContent) return;

        let poetryTimer = null;
        poetryScrollToggle.addEventListener('click', function() {
            const running = this.dataset.running === '1';
            if (running) {
                this.dataset.running = '0';
                this.innerHTML = '<i class="fas fa-wave-square mr-1"></i>自动滚动';
                clearInterval(poetryTimer);
                poetryTimer = null;
                return;
            }

            this.dataset.running = '1';
            this.innerHTML = '<i class="fas fa-pause mr-1"></i>暂停滚动';
            poetryTimer = setInterval(() => {
                const maxScroll = poetryLyricsContent.scrollHeight - poetryLyricsContent.clientHeight;
                if (poetryLyricsContent.scrollTop >= maxScroll) {
                    poetryLyricsContent.scrollTop = 0;
                    return;
                }
                poetryLyricsContent.scrollTop += 1;
            }, 28);
        });
    }

    initVideoTheaterMode() {
        const videoTheaterToggle = document.getElementById('video-theater-toggle');
        const videoPostShell = document.getElementById('video-post-shell');
        if (!videoTheaterToggle || !videoPostShell) return;

        videoTheaterToggle.addEventListener('click', function() {
            const theater = this.dataset.theater === '1';
            if (theater) {
                this.dataset.theater = '0';
                this.innerHTML = '<i class="fas fa-film mr-1"></i>影院模式';
                document.body.classList.remove('bg-black');
                videoPostShell.classList.remove('ring-2', 'ring-indigo-500/50');
                return;
            }

            this.dataset.theater = '1';
            this.innerHTML = '<i class="fas fa-compress mr-1"></i>退出影院';
            document.body.classList.add('bg-black');
            videoPostShell.classList.add('ring-2', 'ring-indigo-500/50');
        });
    }

    initReadingProgress() {
        const detailPageMarkers = [
            '#micro-article',
            '.photo-album-article',
            '#video-post-shell',
            '#poetry-lyrics-content',
            'nav[aria-label="文章目录"]',
            '.prose.prose-lg',
        ];
        const isDetailPage = detailPageMarkers.some((selector) => document.querySelector(selector));
        if (!isDetailPage) return;

        if (document.getElementById('reading-progress-container')) return;

        const progressContainer = document.createElement('div');
        progressContainer.id = 'reading-progress-container';
        progressContainer.innerHTML = '<div id="reading-progress-bar"></div>';
        document.body.appendChild(progressContainer);

        let progressRafId = null;
        const updateReadingProgress = () => {
            const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
            const scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
            const progress = Math.max(0, Math.min(100, (scrollTop / Math.max(scrollHeight, 1)) * 100));
            const progressBar = document.getElementById('reading-progress-bar');
            if (progressBar) {
                progressBar.style.transform = `scaleX(${progress / 100})`;
            }
        };

        const handleScroll = () => {
            if (progressRafId) {
                cancelAnimationFrame(progressRafId);
            }
            progressRafId = requestAnimationFrame(updateReadingProgress);
        };

        window.addEventListener('scroll', handleScroll, { passive: true });
        window.addEventListener('resize', handleScroll, { passive: true });
        updateReadingProgress();
    }

    initFloatingTocPanels(root = document) {
        const scope = root && root.querySelectorAll ? root : document;
        const panels = scope.querySelectorAll('[data-floating-toc]');
        if (!panels.length) return;

        panels.forEach((panel, index) => {
            if (panel.dataset.floatingTocBound === '1') return;
            panel.dataset.floatingTocBound = '1';

            const toggle = panel.querySelector('[data-floating-toc-toggle]');
            if (!toggle) return;

            const tocTitle = panel.dataset.tocTitle || '目录';
            const storageKey = `rewrz_toc_collapsed_${window.location.pathname}_${index}`;

            const applyState = (collapsed) => {
                panel.classList.toggle('is-collapsed', collapsed);
                toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
                toggle.setAttribute('aria-label', collapsed ? `展开${tocTitle}` : `收起${tocTitle}`);

                const icon = toggle.querySelector('i');
                if (icon) {
                    icon.classList.toggle('fa-angles-right', collapsed);
                    icon.classList.toggle('fa-angles-left', !collapsed);
                }

                const label = toggle.querySelector('span');
                if (label) {
                    label.textContent = collapsed ? '目录' : '收起目录';
                }
            };

            let collapsed = panel.classList.contains('is-collapsed');
            try {
                const saved = window.localStorage.getItem(storageKey);
                if (saved === '1') collapsed = true;
                if (saved === '0') collapsed = false;
            } catch (_) {
                // 隐私模式下 localStorage 可能不可用，忽略即可
            }
            applyState(collapsed);

            toggle.addEventListener('click', () => {
                const nextCollapsed = !panel.classList.contains('is-collapsed');
                applyState(nextCollapsed);
                try {
                    window.localStorage.setItem(storageKey, nextCollapsed ? '1' : '0');
                } catch (_) {
                    // localStorage 不可用时不阻塞交互
                }
            });
        });
    }

    initTocHighlight() {
        const tocLinks = document.querySelectorAll('[data-toc-link]');
        if (!tocLinks.length) return;

        const headings = Array.from(tocLinks)
            .map((link) => document.getElementById(link.dataset.tocLink))
            .filter(Boolean);
        if (!headings.length) return;

        const activate = (id) => {
            tocLinks.forEach((link) => {
                if (link.dataset.tocLink === id) {
                    link.classList.add('font-semibold', 'text-blue-900');
                } else {
                    link.classList.remove('font-semibold', 'text-blue-900');
                }
            });
        };

        const observer = new IntersectionObserver(
            (entries) => {
                const visible = entries
                    .filter((entry) => entry.isIntersecting)
                    .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
                if (visible.length) {
                    activate(visible[0].target.id);
                }
            },
            {
                rootMargin: '0px 0px -70% 0px',
                threshold: 0.1,
            }
        );

        headings.forEach((h) => observer.observe(h));
    }

    // ==================== 键盘导航 ====================
    initKeyboardNavigation() {
        document.addEventListener('keydown', (event) => {
            const tagName = (event.target && event.target.tagName) || '';
            const isTypingTarget =
                ['INPUT', 'TEXTAREA', 'SELECT'].includes(tagName) ||
                (event.target && event.target.isContentEditable);
            if (isTypingTarget) return;

            if (event.key === 'k') {
                const firstMedia = document.querySelector('video, audio');
                if (!firstMedia) return;
                event.preventDefault();
                if (firstMedia.paused) {
                    firstMedia.play().catch(() => {});
                } else {
                    firstMedia.pause();
                }
            }

            if (event.key === 'm') {
                const firstMedia = document.querySelector('video, audio');
                if (!firstMedia) return;
                firstMedia.muted = !firstMedia.muted;
                this.showToast(firstMedia.muted ? '已静音' : '已取消静音', 'info', 1200);
            }
        });
    }

    showToast(message, type = 'info', duration = 1800) {
        const toast = document.createElement('div');
        toast.className = `multi-format-toast multi-format-toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            top: 1.25rem;
            left: 50%;
            transform: translateX(-50%);
            z-index: 100;
            padding: 0.6rem 1rem;
            border-radius: 999px;
            color: #fff;
            font-size: 0.82rem;
            font-weight: 600;
            background: rgba(15, 23, 42, 0.92);
            box-shadow: 0 8px 25px rgba(2, 6, 23, 0.35);
            opacity: 0;
            transition: opacity 0.2s ease;
            pointer-events: none;
        `;

        if (type === 'error') {
            toast.style.background = 'rgba(185, 28, 28, 0.95)';
        } else if (type === 'success') {
            toast.style.background = 'rgba(22, 163, 74, 0.95)';
        }

        document.body.appendChild(toast);
        requestAnimationFrame(() => {
            toast.style.opacity = '1';
        });

        window.setTimeout(() => {
            toast.style.opacity = '0';
            window.setTimeout(() => toast.remove(), 220);
        }, Math.max(800, duration));
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (!window.multiFormatInteractions) {
        window.multiFormatInteractions = new MultiFormatInteractions();
    }
});

export default MultiFormatInteractions;

