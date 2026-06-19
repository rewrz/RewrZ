/**
 * 粽子飘落特效
 * 适合端午节场景
 */

class ZongziEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.items = [];
        this.animationId = null;
    }

    init() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'zongzi-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9998;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        for (let i = 0; i < 26; i += 1) {
            this.items.push(this.createItem(i > 12));
        }
        this.animate();
    }

    createItem(fromTop = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: fromTop ? -30 - Math.random() * 140 : Math.random() * this.canvas.height,
            vy: Math.random() * 1.2 + 0.7,
            rotation: Math.random() * Math.PI,
            spin: (Math.random() - 0.5) * 0.02,
            size: Math.random() * 8 + 12,
        };
    }

    drawItem(item) {
        this.ctx.save();
        this.ctx.translate(item.x, item.y);
        this.ctx.rotate(item.rotation);
        this.ctx.fillStyle = '#2b9348';
        this.ctx.beginPath();
        this.ctx.moveTo(0, -item.size);
        this.ctx.lineTo(item.size, item.size * 0.6);
        this.ctx.lineTo(-item.size, item.size * 0.6);
        this.ctx.closePath();
        this.ctx.fill();
        this.ctx.strokeStyle = '#e9d8a6';
        this.ctx.lineWidth = 1.5;
        this.ctx.beginPath();
        this.ctx.moveTo(-item.size * 0.55, -item.size * 0.1);
        this.ctx.lineTo(item.size * 0.55, item.size * 0.15);
        this.ctx.stroke();
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.items.forEach((item) => {
            item.y += item.vy;
            item.rotation += item.spin;
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

window.ZongziEffect = ZongziEffect;
