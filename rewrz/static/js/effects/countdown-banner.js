/**
 * 倒计时横幅特效
 * 适合元旦、跨年与倒数场景
 */

class CountdownBannerEffect {
    constructor() {
        this.container = null;
        this.intervalId = null;
    }

    init() {
        this.container = document.createElement('div');
        this.container.id = 'countdown-banner-effect';
        this.container.style.cssText = `
            position: fixed;
            top: 18px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 10000;
            pointer-events: none;
            padding: 12px 18px;
            border-radius: 999px;
            background: rgba(15, 23, 42, 0.74);
            color: #fff6d8;
            box-shadow: 0 14px 34px rgba(15, 23, 42, 0.28);
            font-size: 14px;
            font-weight: 600;
            letter-spacing: 0.08em;
            backdrop-filter: blur(10px);
        `;
        document.body.appendChild(this.container);
        this.render();
        this.intervalId = window.setInterval(() => this.render(), 1000);
    }

    render() {
        if (!this.container) {
            return;
        }
        const now = new Date();
        const nextYear = new Date(now.getFullYear() + 1, 0, 1, 0, 0, 0);
        const diff = Math.max(0, nextYear.getTime() - now.getTime());
        const hours = String(Math.floor(diff / 3600000)).padStart(2, '0');
        const minutes = String(Math.floor((diff % 3600000) / 60000)).padStart(2, '0');
        const seconds = String(Math.floor((diff % 60000) / 1000)).padStart(2, '0');
        this.container.textContent = `跨年倒计时 ${hours}:${minutes}:${seconds}`;
    }

    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
        if (this.container) {
            document.body.removeChild(this.container);
            this.container = null;
        }
    }
}

window.CountdownBannerEffect = CountdownBannerEffect;
