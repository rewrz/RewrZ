/**
 * 齿轮漂浮特效
 * 适合劳动节与工业感场景
 */

class GearIconsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.items = [];
        this.animationId = null;
    }

    init() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'gear-icons-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9998;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        for (let i = 0; i < 14; i += 1) {
            this.items.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                size: Math.random() * 12 + 18,
                rotation: Math.random() * Math.PI,
                spin: (Math.random() - 0.5) * 0.015,
                drift: (Math.random() - 0.5) * 0.35,
            });
        }
        this.animate();
    }

    drawGear(item) {
        this.ctx.save();
        this.ctx.translate(item.x, item.y);
        this.ctx.rotate(item.rotation);
        this.ctx.strokeStyle = 'rgba(132, 148, 175, 0.8)';
        this.ctx.lineWidth = 3;
        for (let i = 0; i < 8; i += 1) {
            this.ctx.rotate(Math.PI / 4);
            this.ctx.beginPath();
            this.ctx.moveTo(item.size * 0.8, 0);
            this.ctx.lineTo(item.size * 1.15, 0);
            this.ctx.stroke();
        }
        this.ctx.beginPath();
        this.ctx.arc(0, 0, item.size, 0, Math.PI * 2);
        this.ctx.stroke();
        this.ctx.beginPath();
        this.ctx.arc(0, 0, item.size * 0.35, 0, Math.PI * 2);
        this.ctx.stroke();
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.items.forEach((item) => {
            item.x += item.drift;
            item.rotation += item.spin;
            if (item.x < -40) item.x = this.canvas.width + 40;
            if (item.x > this.canvas.width + 40) item.x = -40;
            this.drawGear(item);
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

window.GearIconsEffect = GearIconsEffect;
