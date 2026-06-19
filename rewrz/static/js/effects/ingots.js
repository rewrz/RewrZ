/**
 * 元宝飘落特效
 * 适合破五、财运与新春场景
 */

class IngotsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.items = [];
        this.animationId = null;
    }

    init() {
        this.createCanvas();
        for (let i = 0; i < 24; i += 1) {
            this.items.push(this.createIngot(i > 10));
        }
        this.animate();
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'ingots-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9998;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
    }

    createIngot(fromTop = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: fromTop ? -30 - Math.random() * 140 : Math.random() * this.canvas.height,
            vy: Math.random() * 1.3 + 0.8,
            vx: (Math.random() - 0.5) * 0.5,
            size: Math.random() * 8 + 14,
            rotation: Math.random() * Math.PI,
            spin: (Math.random() - 0.5) * 0.02,
        };
    }

    drawIngot(item) {
        this.ctx.save();
        this.ctx.translate(item.x, item.y);
        this.ctx.rotate(item.rotation);
        this.ctx.fillStyle = '#f6c453';
        this.ctx.beginPath();
        this.ctx.moveTo(-item.size, 0);
        this.ctx.quadraticCurveTo(-item.size * 0.45, -item.size * 0.6, 0, -item.size * 0.2);
        this.ctx.quadraticCurveTo(item.size * 0.45, -item.size * 0.6, item.size, 0);
        this.ctx.quadraticCurveTo(item.size * 0.4, item.size * 0.65, 0, item.size * 0.45);
        this.ctx.quadraticCurveTo(-item.size * 0.4, item.size * 0.65, -item.size, 0);
        this.ctx.fill();
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.items.forEach((item) => {
            item.x += item.vx;
            item.y += item.vy;
            item.rotation += item.spin;
            if (item.y > this.canvas.height + 40) {
                Object.assign(item, this.createIngot(true));
            }
            this.drawIngot(item);
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

window.IngotsEffect = IngotsEffect;
