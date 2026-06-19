/**
 * 桂花飘落特效
 * 适合中秋与秋夜香气场景
 */

class OsmanthusEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.items = [];
        this.animationId = null;
    }

    init() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'osmanthus-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9998;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        for (let i = 0; i < 60; i += 1) {
            this.items.push(this.createItem(i > 28));
        }
        this.animate();
    }

    createItem(fromTop = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: fromTop ? -20 - Math.random() * 120 : Math.random() * this.canvas.height,
            vy: Math.random() * 0.9 + 0.45,
            vx: (Math.random() - 0.5) * 0.5,
            size: Math.random() * 2 + 2.2,
            drift: Math.random() * 0.02 + 0.01,
        };
    }

    drawFlower(item, index) {
        const x = item.x + Math.sin(Date.now() * item.drift + index) * 4;
        this.ctx.save();
        this.ctx.translate(x, item.y);
        this.ctx.fillStyle = 'rgba(245, 203, 92, 0.9)';
        for (let i = 0; i < 4; i += 1) {
            this.ctx.save();
            this.ctx.rotate((Math.PI / 2) * i);
            this.ctx.beginPath();
            this.ctx.ellipse(0, item.size, item.size * 0.75, item.size * 1.15, 0, 0, Math.PI * 2);
            this.ctx.fill();
            this.ctx.restore();
        }
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.items.forEach((item, index) => {
            item.x += item.vx;
            item.y += item.vy;
            if (item.y > this.canvas.height + 24) Object.assign(item, this.createItem(true));
            this.drawFlower(item, index);
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

window.OsmanthusEffect = OsmanthusEffect;
