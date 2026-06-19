/**
 * 星桥特效
 * 适合七夕与星桥场景
 */

class StarBridgeEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.points = [];
        this.animationId = null;
    }

    init() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'star-bridge-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9997;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        this.generatePoints();
        this.animate();
    }

    generatePoints() {
        this.points = [];
        const width = this.canvas.width;
        const height = this.canvas.height;
        for (let i = 0; i < 26; i += 1) {
            const t = i / 25;
            this.points.push({
                x: width * 0.15 + t * width * 0.7,
                y: height * 0.68 - Math.sin(t * Math.PI) * height * 0.16,
                size: Math.random() * 2 + 1.5,
            });
        }
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.ctx.save();
        this.ctx.strokeStyle = 'rgba(255, 233, 166, 0.34)';
        this.ctx.lineWidth = 1.5;
        this.ctx.beginPath();
        this.points.forEach((point, index) => {
            if (index === 0) this.ctx.moveTo(point.x, point.y);
            else this.ctx.lineTo(point.x, point.y);
        });
        this.ctx.stroke();
        this.points.forEach((point, index) => {
            const flicker = 0.8 + Math.sin(Date.now() * 0.003 + index) * 0.2;
            this.ctx.fillStyle = 'rgba(255, 245, 210, 0.92)';
            this.ctx.shadowBlur = 10;
            this.ctx.shadowColor = '#ffe39d';
            this.ctx.beginPath();
            this.ctx.arc(point.x, point.y, point.size * flicker, 0, Math.PI * 2);
            this.ctx.fill();
        });
        this.ctx.restore();
        this.animationId = requestAnimationFrame(() => this.animate());
    }

    stop() {
        if (this.animationId) cancelAnimationFrame(this.animationId);
        if (this.canvas) document.body.removeChild(this.canvas);
        this.canvas = null;
        this.points = [];
        this.animationId = null;
    }
}

window.StarBridgeEffect = StarBridgeEffect;
