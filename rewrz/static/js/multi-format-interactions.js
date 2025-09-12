/**
 * 多格式内容交互功能
 * 支持微博、相册、视频、音乐等不同格式的专属交互
 */

class MultiFormatInteractions {
    constructor() {
        this.lightbox = null;
        this.mediaPlayers = new Map();
        this.init();
    }

    init() {
        this.initImageLightbox();
        this.initMediaPlayers();
        this.initWeiboInteractions();
        this.initLazyLoading();
        this.initInfiniteScroll();
    }

    /**
     * 初始化图片灯箱功能
     */
    initImageLightbox() {
        // 创建灯箱容器
        this.createLightboxContainer();
        
        // 绑定图片点击事件
        document.addEventListener('click', (e) => {
            const img = e.target.closest('.photo-card img, .image-grid img');
            if (img) {
                e.preventDefault();
                this.openLightbox(img);
            }
        });
    }

    createLightboxContainer() {
        const lightbox = document.createElement('div');
        lightbox.id = 'image-lightbox';
        lightbox.className = 'fixed inset-0 z-50 hidden bg-black bg-opacity-90 flex items-center justify-center p-4';
        lightbox.innerHTML = `
            <div class="relative max-w-full max-h-full">
                <img id="lightbox-image" class="max-w-full max-h-full object-contain rounded-lg">
                <button id="lightbox-close" class="absolute top-4 right-4 text-white text-2xl hover:text-gray-300 transition-colors">
                    <i class="fas fa-times"></i>
                </button>
                <button id="lightbox-prev" class="absolute left-4 top-1/2 transform -translate-y-1/2 text-white text-2xl hover:text-gray-300 transition-colors">
                    <i class="fas fa-chevron-left"></i>
                </button>
                <button id="lightbox-next" class="absolute right-4 top-1/2 transform -translate-y-1/2 text-white text-2xl hover:text-gray-300 transition-colors">
                    <i class="fas fa-chevron-right"></i>
                </button>
                <div id="lightbox-info" class="absolute bottom-4 left-4 right-4 text-white text-center">
                    <p id="lightbox-title" class="text-lg font-semibold mb-1"></p>
                    <p id="lightbox-description" class="text-sm opacity-75"></p>
                </div>
            </div>
        `;
        
        document.body.appendChild(lightbox);
        this.lightbox = lightbox;
        
        // 绑定关闭事件
        lightbox.addEventListener('click', (e) => {
            if (e.target === lightbox || e.target.id === 'lightbox-close') {
                this.closeLightbox();
            }
        });
        
        // 键盘事件
        document.addEventListener('keydown', (e) => {
            if (this.lightbox && !this.lightbox.classList.contains('hidden')) {
                switch (e.key) {
                    case 'Escape':
                        this.closeLightbox();
                        break;
                    case 'ArrowLeft':
                        this.prevImage();
                        break;
                    case 'ArrowRight':
                        this.nextImage();
                        break;
                }
            }
        });
    }

    openLightbox(img) {
        const lightboxImg = document.getElementById('lightbox-image');
        const lightboxTitle = document.getElementById('lightbox-title');
        const lightboxDescription = document.getElementById('lightbox-description');
        
        lightboxImg.src = img.src;
        lightboxTitle.textContent = img.alt || '';
        lightboxDescription.textContent = img.dataset.description || '';
        
        this.lightbox.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        
        // 添加打开动画
        this.lightbox.style.opacity = '0';
        setTimeout(() => {
            this.lightbox.style.opacity = '1';
        }, 10);
    }

    closeLightbox() {
        this.lightbox.style.opacity = '0';
        setTimeout(() => {
            this.lightbox.classList.add('hidden');
            document.body.style.overflow = '';
        }, 200);
    }

    /**
     * 初始化媒体播放器
     */
    initMediaPlayers() {
        const mediaCards = document.querySelectorAll('.media-card');
        
        mediaCards.forEach(card => {
            const playButton = card.querySelector('.play-button');
            if (playButton) {
                playButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.handleMediaPlay(card);
                });
            }
        });
    }

    handleMediaPlay(card) {
        const format = card.dataset.format;
        const postUrl = card.querySelector('a').href;
        
        if (format === 'video') {
            this.playVideo(card, postUrl);
        } else if (format === 'music') {
            this.playMusic(card, postUrl);
        }
    }

    playVideo(card, postUrl) {
        // 创建视频播放器
        const videoPlayer = document.createElement('div');
        videoPlayer.className = 'absolute inset-0 bg-black flex items-center justify-center';
        videoPlayer.innerHTML = `
            <video controls autoplay class="w-full h-full object-contain">
                <source src="${postUrl}/video" type="video/mp4">
                您的浏览器不支持视频播放。
            </video>
            <button class="absolute top-4 right-4 text-white text-xl hover:text-gray-300">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        card.appendChild(videoPlayer);
        
        // 绑定关闭事件
        const closeBtn = videoPlayer.querySelector('button');
        closeBtn.addEventListener('click', () => {
            videoPlayer.remove();
        });
    }

    playMusic(card, postUrl) {
        // 创建音乐播放器
        const musicPlayer = document.createElement('div');
        musicPlayer.className = 'absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black to-transparent p-4';
        musicPlayer.innerHTML = `
            <audio controls class="w-full">
                <source src="${postUrl}/audio" type="audio/mpeg">
                您的浏览器不支持音频播放。
            </audio>
        `;
        
        card.appendChild(musicPlayer);
        
        // 自动播放
        const audio = musicPlayer.querySelector('audio');
        audio.play().catch(e => {
            console.log('自动播放被阻止:', e);
        });
    }

    /**
     * 初始化微博交互功能
     */
    initWeiboInteractions() {
        // 点赞功能
        document.addEventListener('click', (e) => {
            const likeBtn = e.target.closest('.weibo-card button[class*="fa-heart"]');
            if (likeBtn) {
                e.preventDefault();
                this.handleLike(likeBtn);
            }
        });
        
        // 评论功能
        document.addEventListener('click', (e) => {
            const commentBtn = e.target.closest('.weibo-card button[class*="fa-comment"]');
            if (commentBtn) {
                e.preventDefault();
                this.handleComment(commentBtn);
            }
        });
    }

    handleLike(button) {
        const icon = button.querySelector('i');
        const count = button.querySelector('span');
        
        if (icon.classList.contains('far')) {
            // 点赞
            icon.classList.remove('far');
            icon.classList.add('fas');
            button.classList.add('text-red-500');
            count.textContent = parseInt(count.textContent) + 1;
            
            // 添加点赞动画
            this.addLikeAnimation(button);
        } else {
            // 取消点赞
            icon.classList.remove('fas');
            icon.classList.add('far');
            button.classList.remove('text-red-500');
            count.textContent = parseInt(count.textContent) - 1;
        }
    }

    addLikeAnimation(button) {
        const heart = document.createElement('i');
        heart.className = 'fas fa-heart absolute text-red-500 pointer-events-none';
        heart.style.left = '50%';
        heart.style.top = '50%';
        heart.style.transform = 'translate(-50%, -50%)';
        heart.style.fontSize = '20px';
        heart.style.opacity = '1';
        
        button.style.position = 'relative';
        button.appendChild(heart);
        
        // 动画效果
        let scale = 1;
        let opacity = 1;
        let translateY = 0;
        
        const animate = () => {
            scale += 0.1;
            opacity -= 0.05;
            translateY -= 2;
            
            heart.style.transform = `translate(-50%, -50%) translateY(${translateY}px) scale(${scale})`;
            heart.style.opacity = opacity;
            
            if (opacity > 0) {
                requestAnimationFrame(animate);
            } else {
                heart.remove();
            }
        };
        
        requestAnimationFrame(animate);
    }

    handleComment(button) {
        // 这里可以实现评论功能
        console.log('评论功能待实现');
    }

    /**
     * 初始化懒加载
     */
    initLazyLoading() {
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        if (img.dataset.src) {
                            img.src = img.dataset.src;
                            img.removeAttribute('data-src');
                            img.classList.remove('lazy');
                            observer.unobserve(img);
                        }
                    }
                });
            });

            document.querySelectorAll('img[data-src]').forEach(img => {
                imageObserver.observe(img);
            });
        }
    }

    /**
     * 初始化无限滚动
     */
    initInfiniteScroll() {
        let loading = false;
        let page = 1;
        
        const loadMoreContent = async () => {
            if (loading) return;
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
            if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 1000) {
                loadMoreContent();
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
                <a href="/posts/${post.slug}" class="text-blue-500 hover:text-blue-700">阅读更多</a>
            </div>
        `;
        return div;
    }

    /**
     * 响应式图片网格调整
     */
    adjustImageGrid() {
        const imageGrids = document.querySelectorAll('.image-grid');
        
        imageGrids.forEach(grid => {
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
        window.multiFormatInteractions.adjustImageGrid();
    });
});

export default MultiFormatInteractions;