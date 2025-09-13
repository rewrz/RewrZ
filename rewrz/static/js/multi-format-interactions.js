/**
 * 多格式内容交互系统
 * 处理微博、相册、视频、诗词歌赋等多重身份内容的前端交互功能
 */

class MultiFormatInteractions {
    constructor() {
        this.init();
    }

    init() {
        this.initMicroPosts();
        this.initPhotoAlbums();
        this.initVideoPlayers();
        this.initAudioPlayers();
        this.initMediaPlayers();
        this.initLazyLoading();
        this.initInfiniteScroll();
        this.initImageGallery();
        this.initResponsiveGrid();
    }

    /**
     * 初始化微博功能
     */
    initMicroPosts() {
        // 微博展开/收起功能
        document.querySelectorAll('.micro-post-content').forEach(content => {
            const fullText = content.textContent.trim();
            const shortText = fullText.substring(0, 140);
            
            if (fullText.length > 140) {
                content.innerHTML = `
                    <span class="short-text">${shortText}...</span>
                    <span class="full-text hidden">${fullText}</span>
                    <button class="expand-btn text-blue-500 hover:text-blue-700 text-sm mt-1">展开</button>
                `;
                
                const expandBtn = content.querySelector('.expand-btn');
                expandBtn.addEventListener('click', () => {
                    const shortTextEl = content.querySelector('.short-text');
                    const fullTextEl = content.querySelector('.full-text');
                    const isExpanded = !shortTextEl.classList.contains('hidden');
                    
                    if (isExpanded) {
                        shortTextEl.classList.add('hidden');
                        fullTextEl.classList.remove('hidden');
                        expandBtn.textContent = '收起';
                    } else {
                        shortTextEl.classList.remove('hidden');
                        fullTextEl.classList.add('hidden');
                        expandBtn.textContent = '展开';
                    }
                });
            }
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
        let loading = false;
        let page = 1;
        
        const loadMoreContent = async () => {
            if (loading) return;
            
            // 检查是否已滚动到页面底部附近
            if (window.innerHeight + window.scrollY < document.body.offsetHeight - 1000) {
                return;
            }
            
            loading = true;
            
            try {
                // 由于当前系统没有公开的posts API，暂时禁用无限滚动
                // 后续可以根据需要添加专门的分页API
                console.log('无限滚动功能需要额外的API实现');
                return; // 直接返回，不执行加载
            } catch (error) {
                console.error('加载更多内容失败:', error);
            } finally {
                loading = false;
            }
        };
        
        // 滚动监听
        window.addEventListener('scroll', () => {
            // 添加检查确保window和document对象存在
            if (window && document && document.body) {
                if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 1000) {
                    loadMoreContent();
                }
            }
        });
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
            // 检查grid元素是否存在
            if (!grid) return;
            
            const imageCount = parseInt(grid.dataset.imageCount);
            const containerWidth = grid.offsetWidth;
            
            // 根据容器宽度调整网格布局
            if (containerWidth < 400 && imageCount > 2) {
                grid.style.gridTemplateColumns = 'repeat(2, 1fr)';
            } else if (containerWidth < 300 && imageCount > 1) {
                grid.style.gridTemplateColumns = '1fr';
            }
        });
    }
}

// 初始化多格式交互功能
document.addEventListener('DOMContentLoaded', () => {
    window.multiFormatInteractions = new MultiFormatInteractions();
    
    // 响应式调整
    window.addEventListener('resize', () => {
        // 检查对象是否存在再调用方法
        if (window.multiFormatInteractions && typeof window.multiFormatInteractions.adjustImageGrid === 'function') {
            window.multiFormatInteractions.adjustImageGrid();
        }
    });
});

export default MultiFormatInteractions;