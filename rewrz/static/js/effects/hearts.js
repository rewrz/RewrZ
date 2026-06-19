/**
 * 爱心飘动特效
 * 适合情人节、七夕与温柔节庆场景
 */

class HeartsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.hearts = [];
        this.animationId = null;
        this.colors = ['#ff5c8a', '#ff7aa2', '#ff9cbc', '#ffc1d6'];
    }

    init() {
        this.createCanvas();
        this.generateHearts();
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

        this.hearts = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'hearts-canvas';
        this.canvas.style.cssText = `
            position: fixed;
            inset: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 9999;
        `;

        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');

        document.body.appendChild(this.canvas);

        window.addEventListener('resize', () => {
            if (!this.canvas) {
                return;
            }
            this.canvas.width = window.innerWidth;
            this.canvas.height = window.innerHeight;
        });
    }

    generateHearts() {
        for (let index = 0; index < 28; index += 1) {
            this.hearts.push(this.createHeart(Math.random() * this.canvas.width, Math.random() * this.canvas.height));
        }
    }

    createHeart(x, y) {
        return {
            x,
            y,
            vx: (Math.random() - 0.5) * 0.9,
            vy: -(Math.random() * 0.8 + 0.55),
            drift: Math.random() * 0.02 + 0.008,
            size: Math.random() * 10 + 12,
            alpha: Math.random() * 0.35 + 0.45,
            color: this.colors[Math.floor(Math.random() * this.colors.length)],
        };
    }

    drawHeart(heart) {
        const { x, y, size } = heart;
        this.ctx.save();
        this.ctx.translate(x, y);
        this.ctx.scale(size / 18, size / 18);
        this.ctx.globalAlpha = heart.alpha;
        this.ctx.fillStyle = heart.color;
        this.ctx.beginPath();
        this.ctx.moveTo(0, 6);
        this.ctx.bezierCurveTo(0, 1, -8, -4, -8, -10);
        this.ctx.bezierCurveTo(-8, -16, -1, -18, 0, -12);
        this.ctx.bezierCurveTo(1, -18, 8, -16, 8, -10);
        this.ctx.bezierCurveTo(8, -4, 0, 1, 0, 6);
        this.ctx.closePath();
        this.ctx.fill();
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        this.hearts.forEach((heart) => {
            heart.x += heart.vx + Math.sin(Date.now() * heart.drift) * 0.45;
            heart.y += heart.vy;
            heart.alpha -= 0.0008;

            if (heart.y < -40 || heart.alpha <= 0.08) {
                Object.assign(heart, this.createHeart(Math.random() * this.canvas.width, this.canvas.height + Math.random() * 120));
                heart.alpha = Math.random() * 0.35 + 0.45;
            }

            this.drawHeart(heart);
        });

        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

window.HeartsEffect = HeartsEffect;
