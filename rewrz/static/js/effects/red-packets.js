/**
 * 红包飘落特效
 * 适合春节、新春与喜庆红包场景
 */

class RedPacketsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.items = [];
        this.animationId = null;
    }

    init() {
        this.createCanvas();
        this.generateItems();
        this.animate();
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'red-packets-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9998;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        this.handleWindowResize = () => {
            if (!this.canvas) return;
            this.canvas.width = window.innerWidth;
            this.canvas.height = window.innerHeight;
        };
    }

    createPacket(fromTop = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: fromTop ? -40 - Math.random() * 160 : Math.random() * this.canvas.height,
            vy: Math.random() * 1.6 + 1,
            vx: (Math.random() - 0.5) * 0.8,
            width: Math.random() * 10 + 18,
            height: Math.random() * 10 + 26,
            rotation: Math.random() * Math.PI,
            spin: (Math.random() - 0.5) * 0.03,
        };
    }

    generateItems() {
        for (let i = 0; i < 30; i += 1) {
            this.items.push(this.createPacket(i > 12));
        }
    }

    drawPacket(item) {
        this.ctx.save();
        this.ctx.translate(item.x, item.y);
        this.ctx.rotate(item.rotation);
        this.ctx.fillStyle = '#d62828';
        this.ctx.fillRect(-item.width / 2, -item.height / 2, item.width, item.height);
        this.ctx.fillStyle = '#f4d35e';
        this.ctx.fillRect(-item.width / 2, -item.height / 2 + 4, item.width, 5);
        this.ctx.font = `${Math.max(10, Math.floor(item.width * 0.7))}px serif`;
        this.ctx.textAlign = 'center';
        this.ctx.fillText('福', 0, 4);
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.items.forEach((item) => {
            item.x += item.vx + Math.sin(Date.now() * 0.001 + item.y * 0.01) * 0.3;
            item.y += item.vy;
            item.rotation += item.spin;
            if (item.y > this.canvas.height + 50) {
                Object.assign(item, this.createPacket(true));
            }
            this.drawPacket(item);
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

window.RedPacketsEffect = RedPacketsEffect;
