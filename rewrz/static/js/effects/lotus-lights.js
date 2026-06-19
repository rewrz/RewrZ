/**
 * 河灯漂浮特效
 * 适合中元与水面静景场景
 */

class LotusLightsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.items = [];
        this.animationId = null;
    }

    init() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'lotus-lights-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9997;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        for (let i = 0; i < 12; i += 1) {
            this.items.push({
                x: Math.random() * this.canvas.width,
                y: this.canvas.height * (0.72 + Math.random() * 0.18),
                size: Math.random() * 8 + 16,
                drift: Math.random() * 0.02 + 0.008,
            });
        }
        this.animate();
    }

    drawItem(item, index) {
        const x = item.x + Math.sin(Date.now() * item.drift + index) * 14;
        this.ctx.save();
        this.ctx.translate(x, item.y);
        this.ctx.fillStyle = 'rgba(255, 214, 136, 0.85)';
        this.ctx.beginPath();
        this.ctx.arc(0, 0, item.size * 0.18, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.shadowBlur = 14;
        this.ctx.shadowColor = '#ffd48a';
        this.ctx.fillStyle = 'rgba(250, 184, 160, 0.6)';
        for (let i = 0; i < 6; i += 1) {
            this.ctx.save();
            this.ctx.rotate((Math.PI * 2 * i) / 6);
            this.ctx.beginPath();
            this.ctx.ellipse(0, item.size * 0.45, item.size * 0.24, item.size * 0.5, 0, 0, Math.PI * 2);
            this.ctx.fill();
            this.ctx.restore();
        }
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.items.forEach((item, index) => this.drawItem(item, index));
        this.animationId = requestAnimationFrame(() => this.animate());
    }

    stop() {
        if (this.animationId) cancelAnimationFrame(this.animationId);
        if (this.canvas) document.body.removeChild(this.canvas);
        this.canvas = null;
        this.items = [];
        this.animationId = null;
    }
}

window.LotusLightsEffect = LotusLightsEffect;
