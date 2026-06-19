/**
 * 金色流光特效
 * 适合春节、国庆、庆典与追光类节日场景
 */

class GoldenDustEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.particles = [];
        this.animationId = null;
        this.palette = ['#ffd166', '#ffbf3c', '#ffec99', '#fff2c2'];
    }

    init() {
        this.createCanvas();
        this.generateParticles();
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

        this.particles = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'golden-dust-canvas';
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

        window.addEventListener('resize', () => {
            if (!this.canvas) {
                return;
            }
            this.canvas.width = window.innerWidth;
            this.canvas.height = window.innerHeight;
        });
    }

    createParticle(resetFromBottom = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: resetFromBottom ? this.canvas.height + Math.random() * 80 : Math.random() * this.canvas.height,
            vx: (Math.random() - 0.5) * 0.7,
            vy: -(Math.random() * 0.75 + 0.3),
            radius: Math.random() * 2.4 + 1.1,
            blur: Math.random() * 10 + 8,
            alpha: Math.random() * 0.35 + 0.3,
            pulse: Math.random() * 0.02 + 0.01,
            color: this.palette[Math.floor(Math.random() * this.palette.length)],
        };
    }

    generateParticles() {
        for (let index = 0; index < 42; index += 1) {
            this.particles.push(this.createParticle(false));
        }
    }

    drawParticle(particle) {
        this.ctx.save();
        this.ctx.globalAlpha = particle.alpha;
        this.ctx.fillStyle = particle.color;
        this.ctx.shadowBlur = particle.blur;
        this.ctx.shadowColor = particle.color;
        this.ctx.beginPath();
        this.ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        this.particles.forEach((particle, index) => {
            particle.x += particle.vx + Math.sin((Date.now() + index * 90) * particle.pulse) * 0.3;
            particle.y += particle.vy;

            if (particle.y < -50) {
                Object.assign(particle, this.createParticle(true));
            }

            this.drawParticle(particle);
        });

        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

window.GoldenDustEffect = GoldenDustEffect;
