/**
 * 羽毛飘落特效
 * 适合七夕与轻柔浪漫场景
 */

class FeathersEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.items = [];
        this.animationId = null;
    }

    init() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'feathers-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9998;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        for (let i = 0; i < 34; i += 1) {
            this.items.push(this.createItem(i > 14));
        }
        this.animate();
    }

    createItem(fromTop = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: fromTop ? -20 - Math.random() * 140 : Math.random() * this.canvas.height,
            vy: Math.random() * 0.9 + 0.35,
            vx: (Math.random() - 0.5) * 0.5,
            size: Math.random() * 8 + 10,
            tilt: (Math.random() - 0.5) * 0.8,
            drift: Math.random() * 0.03 + 0.01,
        };
    }

    drawItem(item, index) {
        const x = item.x + Math.sin(Date.now() * item.drift + index) * 5;
        this.ctx.save();
        this.ctx.translate(x, item.y);
        this.ctx.rotate(item.tilt);
        this.ctx.strokeStyle = 'rgba(255, 248, 245, 0.88)';
        this.ctx.lineWidth = 1;
        this.ctx.beginPath();
        this.ctx.moveTo(0, -item.size);
        this.ctx.lineTo(0, item.size);
        this.ctx.stroke();
        this.ctx.beginPath();
        for (let i = -item.size; i < item.size; i += 4) {
            this.ctx.moveTo(0, i);
            this.ctx.lineTo(item.size * 0.45, i + 3);
            this.ctx.moveTo(0, i);
            this.ctx.lineTo(-item.size * 0.35, i + 2);
        }
        this.ctx.stroke();
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.items.forEach((item, index) => {
            item.x += item.vx;
            item.y += item.vy;
            if (item.y > this.canvas.height + 35) Object.assign(item, this.createItem(true));
            this.drawItem(item, index);
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

window.FeathersEffect = FeathersEffect;
