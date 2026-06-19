/**
 * 粉笔字横幅特效
 * 适合教师节场景
 */

class ChalkWritingEffect {
    constructor() {
        this.container = null;
        this.intervalId = null;
        this.messages = ['老师，您辛苦了', '桃李满天下', '致敬每一位引路人'];
        this.index = 0;
    }

    init() {
        this.container = document.createElement('div');
        this.container.id = 'chalk-writing-effect';
        this.container.style.cssText = `
            position: fixed;
            top: 22px;
            right: 24px;
            z-index: 10000;
            pointer-events: none;
            padding: 14px 18px;
            min-width: 220px;
            border-radius: 18px;
            background: rgba(34, 54, 42, 0.76);
            color: rgba(245, 248, 241, 0.96);
            box-shadow: 0 16px 36px rgba(16, 24, 20, 0.28);
            font-size: 18px;
            font-family: 'KaiTi', 'STKaiti', serif;
            letter-spacing: 0.08em;
        `;
        document.body.appendChild(this.container);
        this.render();
        this.intervalId = window.setInterval(() => this.render(), 2600);
    }

    render() {
        if (!this.container) return;
        this.container.textContent = this.messages[this.index % this.messages.length];
        this.index += 1;
    }

    stop() {
        if (this.intervalId) clearInterval(this.intervalId);
        if (this.container) document.body.removeChild(this.container);
        this.container = null;
        this.intervalId = null;
    }
}

window.ChalkWritingEffect = ChalkWritingEffect;
