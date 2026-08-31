/**
 * 星光特效
 * 适合七夕、中秋、圣诞与夜景节庆
 */

class StarsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.stars = [];
        this.animationId = null;
    }

    init() {
        this.createCanvas();
        this.generateStars();
        this.animate();
    }

    stop() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
            this.animationId = null;
        }
        if (this.canvas) {
            document.body.removeChild(this.canvas);
            this.canvas = null;
        }
        this.stars = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'stars-canvas';
        this.canvas.style.cssText = `
            position: fixed;
            inset: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 9997;
        `;
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);

        this.handleWindowResize = () => {
            if (!this.canvas) {
                return;
            }
            this.canvas.width = window.innerWidth;
            this.canvas.height = window.innerHeight;
            this.generateStars();
        };
    }

    generateStars() {
        this.stars = [];
        const count = Math.max(40, Math.floor(this.canvas.width / 24));
        for (let index = 0; index < count; index += 1) {
            this.stars.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * (this.canvas.height * 0.72),
                radius: Math.random() * 1.8 + 0.8,
                alpha: Math.random() * 0.55 + 0.25,
                pulse: Math.random() * 0.03 + 0.01,
                hue: Math.random() > 0.86 ? '#ffe7a8' : '#fff7e3',
            });
        }
    }

    drawStar(star, index) {
        const flicker = 0.72 + Math.sin((Date.now() + index * 90) * star.pulse) * 0.28;
        const radius = star.radius * flicker;

        this.ctx.save();
        this.ctx.globalAlpha = star.alpha;
        this.ctx.fillStyle = star.hue;
        this.ctx.shadowBlur = radius * 6;
        this.ctx.shadowColor = star.hue;
        this.ctx.beginPath();
        this.ctx.arc(star.x, star.y, radius, 0, Math.PI * 2);
        this.ctx.fill();

        this.ctx.strokeStyle = 'rgba(255,255,255,0.3)';
        this.ctx.lineWidth = 0.8;
        this.ctx.beginPath();
        this.ctx.moveTo(star.x - radius * 2, star.y);
        this.ctx.lineTo(star.x + radius * 2, star.y);
        this.ctx.moveTo(star.x, star.y - radius * 2);
        this.ctx.lineTo(star.x, star.y + radius * 2);
        this.ctx.stroke();
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.stars.forEach((star, index) => this.drawStar(star, index));
        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

window.StarsEffect = StarsEffect;
