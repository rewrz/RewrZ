/**
 * 柳絮飘落特效
 * 适合清明与轻柔追思场景
 */

class WillowCatkinsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.items = [];
        this.animationId = null;
    }

    init() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'willow-catkins-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9998;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        for (let i = 0; i < 48; i += 1) {
            this.items.push(this.createItem(i > 18));
        }
        this.animate();
    }

    createItem(fromTop = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: fromTop ? -20 - Math.random() * 140 : Math.random() * this.canvas.height,
            vy: Math.random() * 0.9 + 0.35,
            vx: (Math.random() - 0.5) * 0.7,
            size: Math.random() * 8 + 6,
            drift: Math.random() * 0.03 + 0.01,
        };
    }

    drawItem(item, index) {
        const x = item.x + Math.sin(Date.now() * item.drift + index) * 6;
        this.ctx.save();
        this.ctx.translate(x, item.y);
        this.ctx.rotate(Math.sin(Date.now() * 0.001 + index) * 0.5);
        this.ctx.strokeStyle = 'rgba(242, 246, 244, 0.9)';
        this.ctx.lineWidth = 1.2;
        this.ctx.beginPath();
        this.ctx.moveTo(0, -item.size * 0.5);
        this.ctx.lineTo(0, item.size * 0.5);
        this.ctx.stroke();
        this.ctx.beginPath();
        this.ctx.arc(0, item.size * 0.55, item.size * 0.36, 0, Math.PI * 2);
        this.ctx.fillStyle = 'rgba(255,255,255,0.78)';
        this.ctx.fill();
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.items.forEach((item, index) => {
            item.x += item.vx;
            item.y += item.vy;
            if (item.y > this.canvas.height + 30) Object.assign(item, this.createItem(true));
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

window.WillowCatkinsEffect = WillowCatkinsEffect;
