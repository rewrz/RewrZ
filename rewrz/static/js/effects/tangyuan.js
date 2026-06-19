/**
 * 汤圆漂浮特效
 * 适合元宵与团圆场景
 */

class TangyuanEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.items = [];
        this.animationId = null;
    }

    init() {
        this.createCanvas();
        for (let i = 0; i < 18; i += 1) {
            this.items.push(this.createTangyuan());
        }
        this.animate();
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'tangyuan-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9998;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
    }

    createTangyuan() {
        return {
            x: Math.random() * this.canvas.width,
            y: Math.random() * this.canvas.height,
            radius: Math.random() * 8 + 12,
            drift: Math.random() * 0.02 + 0.008,
            speed: Math.random() * 0.4 + 0.2,
        };
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.items.forEach((item, index) => {
            item.x += Math.sin(Date.now() * item.drift + index) * item.speed;
            item.y += Math.cos(Date.now() * item.drift + index) * item.speed * 0.5;
            this.ctx.save();
            this.ctx.fillStyle = '#fff9ef';
            this.ctx.shadowBlur = 8;
            this.ctx.shadowColor = 'rgba(255, 244, 220, 0.8)';
            this.ctx.beginPath();
            this.ctx.arc(item.x, item.y, item.radius, 0, Math.PI * 2);
            this.ctx.fill();
            this.ctx.fillStyle = 'rgba(230, 220, 210, 0.28)';
            this.ctx.beginPath();
            this.ctx.arc(item.x - item.radius * 0.2, item.y - item.radius * 0.15, item.radius * 0.35, 0, Math.PI * 2);
            this.ctx.fill();
            this.ctx.restore();
        });
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

window.TangyuanEffect = TangyuanEffect;
