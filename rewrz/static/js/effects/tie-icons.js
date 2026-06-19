/**
 * 领带漂浮特效
 * 适合父亲节场景
 */

class TieIconsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.items = [];
        this.animationId = null;
        this.palette = ['#2563eb', '#1d4ed8', '#0f766e', '#334155'];
    }

    init() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'tie-icons-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9998;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        for (let i = 0; i < 24; i += 1) {
            this.items.push(this.createItem(i > 10));
        }
        this.animate();
    }

    createItem(fromTop = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: fromTop ? -30 - Math.random() * 160 : Math.random() * this.canvas.height,
            vy: Math.random() * 1 + 0.45,
            rotation: (Math.random() - 0.5) * 0.35,
            size: Math.random() * 8 + 16,
            color: this.palette[Math.floor(Math.random() * this.palette.length)],
        };
    }

    drawItem(item) {
        this.ctx.save();
        this.ctx.translate(item.x, item.y);
        this.ctx.rotate(item.rotation);
        this.ctx.fillStyle = item.color;
        this.ctx.beginPath();
        this.ctx.moveTo(0, -item.size);
        this.ctx.lineTo(item.size * 0.55, -item.size * 0.3);
        this.ctx.lineTo(0, item.size * 1.2);
        this.ctx.lineTo(-item.size * 0.55, -item.size * 0.3);
        this.ctx.closePath();
        this.ctx.fill();
        this.ctx.fillRect(-item.size * 0.25, -item.size * 1.25, item.size * 0.5, item.size * 0.45);
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.items.forEach((item) => {
            item.y += item.vy;
            if (item.y > this.canvas.height + 40) Object.assign(item, this.createItem(true));
            this.drawItem(item);
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

window.TieIconsEffect = TieIconsEffect;
