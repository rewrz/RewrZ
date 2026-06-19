/**
 * 饺子飘落特效
 * 适合冬至与北方团圆场景
 */

class DumplingsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.items = [];
        this.animationId = null;
    }

    init() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'dumplings-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9998;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        for (let i = 0; i < 22; i += 1) {
            this.items.push(this.createItem(i > 10));
        }
        this.animate();
    }

    createItem(fromTop = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: fromTop ? -20 - Math.random() * 120 : Math.random() * this.canvas.height,
            vy: Math.random() * 1.05 + 0.55,
            rotation: (Math.random() - 0.5) * 0.6,
            size: Math.random() * 8 + 14,
        };
    }

    drawItem(item) {
        this.ctx.save();
        this.ctx.translate(item.x, item.y);
        this.ctx.rotate(item.rotation);
        this.ctx.fillStyle = '#fbf5ea';
        this.ctx.beginPath();
        this.ctx.moveTo(-item.size, 0);
        this.ctx.quadraticCurveTo(0, -item.size * 1.15, item.size, 0);
        this.ctx.quadraticCurveTo(0, item.size * 0.75, -item.size, 0);
        this.ctx.fill();
        this.ctx.strokeStyle = 'rgba(215, 204, 189, 0.7)';
        this.ctx.lineWidth = 1.2;
        this.ctx.beginPath();
        this.ctx.moveTo(-item.size * 0.5, 0);
        this.ctx.lineTo(item.size * 0.5, 0);
        this.ctx.stroke();
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

window.DumplingsEffect = DumplingsEffect;
