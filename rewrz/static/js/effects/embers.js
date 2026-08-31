/**
 * 余烬火星特效
 * 适合小年、除夕、暖光与灶火氛围
 */

class EmbersEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.embers = [];
        this.animationId = null;
        this.palette = ['#ffb347', '#ff8c42', '#ffd166', '#ff6b35'];
    }

    init() {
        this.createCanvas();
        this.generateEmbers();
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
        this.embers = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'embers-canvas';
        this.canvas.style.cssText = `
            position: fixed;
            inset: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 9998;
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
        };
    }

    createEmber(fromBottom = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: fromBottom ? this.canvas.height + Math.random() * 50 : this.canvas.height * (0.35 + Math.random() * 0.65),
            vx: (Math.random() - 0.5) * 0.8,
            vy: -(Math.random() * 1.2 + 0.55),
            radius: Math.random() * 2.4 + 1.4,
            alpha: Math.random() * 0.48 + 0.22,
            drift: Math.random() * 0.04 + 0.01,
            color: this.palette[Math.floor(Math.random() * this.palette.length)],
        };
    }

    generateEmbers() {
        for (let index = 0; index < 38; index += 1) {
            this.embers.push(this.createEmber(index > 15));
        }
    }

    drawEmber(ember) {
        this.ctx.save();
        this.ctx.globalAlpha = ember.alpha;
        this.ctx.fillStyle = ember.color;
        this.ctx.shadowBlur = ember.radius * 10;
        this.ctx.shadowColor = ember.color;
        this.ctx.beginPath();
        this.ctx.arc(ember.x, ember.y, ember.radius, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        this.embers.forEach((ember, index) => {
            ember.x += ember.vx + Math.sin((Date.now() + index * 110) * ember.drift) * 0.4;
            ember.y += ember.vy;
            ember.alpha -= 0.0022;

            if (ember.y < -25 || ember.alpha <= 0.05) {
                Object.assign(ember, this.createEmber(true));
            }

            this.drawEmber(ember);
        });

        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

window.EmbersEffect = EmbersEffect;
