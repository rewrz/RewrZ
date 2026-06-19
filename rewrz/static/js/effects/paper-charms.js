/**
 * 纸符飘落特效
 * 适合中元与肃穆传统场景
 */

class PaperCharmsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.items = [];
        this.animationId = null;
    }

    init() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'paper-charms-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9998;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        for (let i = 0; i < 28; i += 1) {
            this.items.push(this.createItem(i > 10));
        }
        this.animate();
    }

    createItem(fromTop = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: fromTop ? -20 - Math.random() * 140 : Math.random() * this.canvas.height,
            vy: Math.random() * 1 + 0.45,
            vx: (Math.random() - 0.5) * 0.45,
            width: Math.random() * 8 + 14,
            height: Math.random() * 14 + 22,
            rotation: (Math.random() - 0.5) * 0.35,
        };
    }

    drawItem(item) {
        this.ctx.save();
        this.ctx.translate(item.x, item.y);
        this.ctx.rotate(item.rotation);
        this.ctx.fillStyle = 'rgba(242, 214, 173, 0.82)';
        this.ctx.fillRect(-item.width / 2, -item.height / 2, item.width, item.height);
        this.ctx.fillStyle = 'rgba(120, 72, 32, 0.58)';
        this.ctx.fillRect(-1, -item.height / 2 + 4, 2, item.height - 8);
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.items.forEach((item) => {
            item.x += item.vx;
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

window.PaperCharmsEffect = PaperCharmsEffect;
