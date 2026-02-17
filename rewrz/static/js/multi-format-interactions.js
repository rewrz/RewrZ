/**
 * 多格式内容交互系统
 * 处理微博、相册、视频、诗词歌赋等多重身份内容的前端交互功能
 * Version 2.0 - 增强版
 */

class MultiFormatInteractions {
    constructor() {
        this.reactionStorage = this.getStorage('reactions');
        this.speechSynthesis = window.speechSynthesis || null;
        this.speaking = false;
        this.init();
    }

    init() {
        this.initMicroPosts();
        this.initPhotoAlbums();
        this.initVideoPlayers();
        this.initAudioPlayers();
        this.initMediaPlayers();
        this.initLazyLoading();
        this.initAjaxPaginationBridge();
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
        this.initTocHighlight();
        this.initKeyboardNavigation();
        window.addEventListener('resize', () => this.adjustImageGrid(), { passive: true });
    }

    // ==================== 存储工具 ====================
    getStorage(key) {
        try {
            const data = localStorage.getItem(`rewrz_${key}`);
            return data ? JSON.parse(data) : {};
        } catch (e) {
            return {};
        }
    }

    setStorage(key, data) {
        try {
            localStorage.setItem(`rewrz_${key}`, JSON.stringify(data));
        } catch (e) {
            // 忽略存储错误
        }
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
     * 初始化无刷新分页增强（兜底）
     * 当页面处于 ajax 模式时，为缺失 hx 属性的分页链接补齐配置
     */
    initAjaxPaginationBridge() {
        const mode = String(document.body?.dataset?.listNavigationMode || '').trim().toLowerCase();
        if (mode !== 'ajax') return;

        const patchPaginationLinks = (root = document) => {
            const scope = root && typeof root.querySelectorAll === 'function' ? root : document;
            const links = scope.querySelectorAll('nav[aria-label="pagination"] a[href], #pagination a[href*="page="]');

            links.forEach((link) => {
                if (link.dataset.ajaxPatched === '1') return;

                const href = link.getAttribute('href');
                if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;

                const panel =
                    link.closest('#search-panel, [id$="-posts-panel"]') ||
                    document.querySelector('#search-panel, [id$="-posts-panel"]');
                if (!panel || !panel.id) return;

                link.setAttribute('hx-get', href);
                link.setAttribute('hx-target', `#${panel.id}`);
                link.setAttribute('hx-push-url', 'true');

                if (panel.id === 'search-panel') {
                    link.setAttribute('hx-swap', 'innerHTML');
                    link.removeAttribute('hx-select');
                } else {
                    link.setAttribute('hx-select', `#${panel.id}`);
                    link.setAttribute('hx-swap', 'outerHTML');
                }

                link.dataset.ajaxPatched = '1';
            });
        };

        patchPaginationLinks(document);
        document.body.addEventListener('htmx:afterSwap', (event) => {
            patchPaginationLinks(event?.target || document);
        });
    }

    /**
     * 初始化无限滚动
     */
    initInfiniteScroll() {
        const mode = String(document.body?.dataset?.listNavigationMode || '').trim().toLowerCase();
        if (mode !== 'infinite_scroll') return;

        let ticking = false;
        const getLoader = () => document.querySelector('[data-infinite-loader="1"]');

        const fetchAndReplaceLoader = async (loader) => {
            const url = loader?.getAttribute('hx-get');
            if (!url) return;

            loader.dataset.loading = '1';
            try {
                const response = await fetch(url, {
                    headers: { 'HX-Request': 'true' },
                    credentials: 'same-origin',
                });
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                const html = await response.text();
                loader.outerHTML = html;
            } catch (error) {
                console.error('加载更多内容失败:', error);
                if (loader && loader.isConnected) {
                    loader.dataset.loading = '0';
                }
            }
        };

        const triggerLoadMore = () => {
            const loader = getLoader();
            if (!loader || loader.dataset.loading === '1') return;

            const rect = loader.getBoundingClientRect();
            if (rect.top > window.innerHeight + 220) return;

            loader.dataset.loading = '1';
            if (window.htmx && typeof window.htmx.trigger === 'function') {
                window.htmx.trigger(loader, 'revealed');
            } else {
                fetchAndReplaceLoader(loader);
            }
        };

        const scheduleCheck = () => {
            if (ticking) return;
            ticking = true;
            window.requestAnimationFrame(() => {
                ticking = false;
                triggerLoadMore();
            });
        };

        window.addEventListener('scroll', scheduleCheck, { passive: true });
        window.addEventListener('resize', scheduleCheck, { passive: true });

        document.body.addEventListener('htmx:beforeRequest', (event) => {
            const source = event?.detail?.elt;
            if (source && source.matches && source.matches('[data-infinite-loader="1"]')) {
                source.dataset.loading = '1';
            }
        });

        document.body.addEventListener('htmx:responseError', (event) => {
            const source = event?.detail?.elt;
            if (source && source.matches && source.matches('[data-infinite-loader="1"]')) {
                source.dataset.loading = '0';
            }
        });

        document.body.addEventListener('htmx:afterSwap', () => {
            scheduleCheck();
        });

        scheduleCheck();
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

    // ==================== 表情反应系统 ====================
    initReactionSystem() {
        const container = document.getElementById('reaction-container');
        if (!container) return;

        const postId = document.body.dataset.postId || window.location.pathname;
        const buttons = container.querySelectorAll('.reaction-btn');
        const summaryEl = document.getElementById('reaction-summary');

        // 加载已保存的反应
        const savedReactions = this.reactionStorage[postId] || {};
        let totalCount = 0;

        buttons.forEach(btn => {
            const reaction = btn.dataset.reaction;
            const countEl = btn.querySelector('.reaction-count');
            const saved = savedReactions[reaction] || { count: 0, active: false };
            
            if (countEl) countEl.textContent = saved.count;
            if (saved.active) btn.classList.add('active');
            totalCount += saved.count;

            btn.addEventListener('click', () => {
                const isActive = btn.classList.toggle('active');
                const currentCount = parseInt(countEl.textContent || '0');
                const newCount = isActive ? currentCount + 1 : Math.max(0, currentCount - 1);
                
                if (countEl) countEl.textContent = newCount;
                
                // 保存状态
                if (!this.reactionStorage[postId]) this.reactionStorage[postId] = {};
                this.reactionStorage[postId][reaction] = { count: newCount, active: isActive };
                this.setStorage('reactions', this.reactionStorage);

                // 更新总结
                this.updateReactionSummary(container, summaryEl);
                
                // 添加动画效果
                btn.style.transform = 'scale(1.2)';
                setTimeout(() => btn.style.transform = '', 200);
            });
        });

        this.updateReactionSummary(container, summaryEl);
    }

    updateReactionSummary(container, summaryEl) {
        if (!summaryEl || !container) return;
        
        let total = 0;
        container.querySelectorAll('.reaction-count').forEach(el => {
            total += parseInt(el.textContent || '0');
        });

        if (total === 0) {
            summaryEl.textContent = '还没有人表态，快来抢沙发！';
        } else if (total < 5) {
            summaryEl.textContent = `${total} 人表态`;
        } else {
            summaryEl.textContent = `🔥 ${total} 人觉得赞`;
        }
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

    initLightboxFromDataset() {
        if (document.getElementById('format-lightbox')) return;

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

        lightboxButtons.forEach((btn) => {
            btn.addEventListener('click', function() {
                const group = this.dataset.lightboxGroup;
                const position = Number(this.dataset.lightboxPosition || '0');
                openLightbox(group, Number.isNaN(position) ? 0 : position);
            });
        });
    }

    initMicroDetailActions() {
        const microLikeBtn = document.getElementById('micro-like-btn');
        if (microLikeBtn) {
            microLikeBtn.addEventListener('click', function() {
                const liked = this.dataset.liked === '1';
                this.dataset.liked = liked ? '0' : '1';
                this.classList.toggle('text-rose-500', !liked);
                this.innerHTML = liked
                    ? '<i class="far fa-heart mr-1"></i>喜欢'
                    : '<i class="fas fa-heart mr-1"></i>已喜欢';
            });
        }

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

