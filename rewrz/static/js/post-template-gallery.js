/**
 * 图文展览文章模板交互：
 * - 把正文图片包装成带图注的作品卡片
 * - 滚动入场动画与章节导航
 * - 点击作品打开大图浏览（支持键盘与左右切换）
 */

(function () {
    const root = document.getElementById('articleGalleryRoot');
    const content = document.getElementById('articleGalleryContent');
    if (!root || !content) return;

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const figures = Array.from(content.querySelectorAll('img')).map((img, index) => {
        const link = img.parentElement && img.parentElement.tagName === 'A' ? img.parentElement : img;
        const paragraph = link.closest('p');
        const isSoloParagraph =
            paragraph &&
            paragraph.querySelectorAll('img').length === 1 &&
            !paragraph.textContent.trim() &&
            paragraph.children.length <= 2;

        const figure = document.createElement('figure');
        figure.className = 'article-gallery-shot';
        figure.dataset.index = String(index + 1).padStart(2, '0');
        figure.tabIndex = 0;
        figure.setAttribute('role', 'button');

        const block = isSoloParagraph ? paragraph : link;
        block.parentNode.insertBefore(figure, block);
        figure.appendChild(link);
        if (isSoloParagraph) {
            paragraph.remove();
        }

        const captionText = (img.alt || '').trim();
        if (captionText) {
            const caption = document.createElement('figcaption');
            caption.textContent = captionText;
            figure.appendChild(caption);
        }
        figure.setAttribute('aria-label', captionText ? `放大查看：${captionText}` : '放大查看作品');

        return { figure, img };
    });

    root.classList.add('article-gallery-ready');

    // 滚动入场
    const revealTargets = content.querySelectorAll('.article-gallery-shot, h2, blockquote');
    if (prefersReducedMotion || !('IntersectionObserver' in window)) {
        revealTargets.forEach((element) => element.classList.add('is-visible'));
    } else {
        const revealObserver = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (!entry.isIntersecting) return;
                    entry.target.classList.add('is-visible');
                    revealObserver.unobserve(entry.target);
                });
            },
            { rootMargin: '0px 0px -12% 0px', threshold: 0.08 }
        );
        revealTargets.forEach((element) => revealObserver.observe(element));
    }

    // 章节导航
    const headings = Array.from(content.querySelectorAll('h2'));
    if (headings.length > 1) {
        const nav = document.createElement('nav');
        nav.className = 'article-gallery-nav';
        nav.setAttribute('aria-label', '展览章节导航');

        const links = headings.map((heading, index) => {
            const id = `article-gallery-chapter-${index + 1}`;
            heading.id = id;
            const link = document.createElement('a');
            link.href = `#${id}`;

            const label = document.createElement('span');
            label.className = 'label';
            label.textContent = heading.textContent || `章节 ${index + 1}`;

            const dot = document.createElement('span');
            dot.className = 'dot';

            link.appendChild(label);
            link.appendChild(dot);
            link.addEventListener('click', (event) => {
                event.preventDefault();
                heading.scrollIntoView({
                    behavior: prefersReducedMotion ? 'auto' : 'smooth',
                    block: 'start',
                });
            });
            nav.appendChild(link);
            return link;
        });

        document.body.appendChild(nav);

        if ('IntersectionObserver' in window) {
            const navObserver = new IntersectionObserver(
                (entries) => {
                    entries.forEach((entry) => {
                        if (!entry.isIntersecting) return;
                        const activeIndex = headings.indexOf(entry.target);
                        links.forEach((link, index) => {
                            link.classList.toggle('is-active', index === activeIndex);
                        });
                    });
                },
                { rootMargin: '-28% 0px -58% 0px', threshold: 0 }
            );
            headings.forEach((heading) => navObserver.observe(heading));
        }
    }

    // 大图浏览
    const lightbox = document.getElementById('articleGalleryLightbox');
    if (!lightbox || !figures.length) return;

    const lightboxImage = lightbox.querySelector('img');
    const lightboxCaption = lightbox.querySelector('.article-gallery-lightbox-caption');
    const lightboxCount = lightbox.querySelector('.article-gallery-lightbox-count');
    const closeButton = lightbox.querySelector('[data-gallery-close]');
    let currentIndex = 0;

    function renderLightbox(index) {
        currentIndex = (index + figures.length) % figures.length;
        const activeImage = figures[currentIndex].img;
        lightboxImage.src = activeImage.currentSrc || activeImage.src;
        lightboxImage.alt = activeImage.alt || '';
        if (lightboxCaption) {
            lightboxCaption.textContent = activeImage.alt || '';
        }
        if (lightboxCount) {
            lightboxCount.textContent = `${String(currentIndex + 1).padStart(2, '0')} / ${String(figures.length).padStart(2, '0')}`;
        }
    }

    function openLightbox(index) {
        renderLightbox(index);
        lightbox.classList.add('is-open');
        lightbox.setAttribute('aria-hidden', 'false');
        document.body.classList.add('article-gallery-lock');
        closeButton?.focus({ preventScroll: true });
    }

    function closeLightbox() {
        lightbox.classList.remove('is-open');
        lightbox.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('article-gallery-lock');
    }

    figures.forEach(({ figure }, index) => {
        figure.addEventListener('click', (event) => {
            event.preventDefault();
            openLightbox(index);
        });
        figure.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                openLightbox(index);
            }
        });
    });

    closeButton?.addEventListener('click', closeLightbox);
    lightbox.querySelector('[data-gallery-prev]')?.addEventListener('click', (event) => {
        event.stopPropagation();
        renderLightbox(currentIndex - 1);
    });
    lightbox.querySelector('[data-gallery-next]')?.addEventListener('click', (event) => {
        event.stopPropagation();
        renderLightbox(currentIndex + 1);
    });
    lightbox.addEventListener('click', (event) => {
        if (event.target === lightbox) {
            closeLightbox();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (!lightbox.classList.contains('is-open')) return;
        if (event.key === 'Escape') {
            closeLightbox();
        } else if (event.key === 'ArrowLeft') {
            renderLightbox(currentIndex - 1);
        } else if (event.key === 'ArrowRight') {
            renderLightbox(currentIndex + 1);
        }
    });
})();
