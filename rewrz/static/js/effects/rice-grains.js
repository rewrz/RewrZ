/**
 * 米粒飘落特效
 * 适合腊八、细碎粮食与轻颗粒节日氛围
 */

class RiceGrainsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.grains = [];
        this.animationId = null;
        this.palette = ['#f6f0dd', '#ede2bf', '#f8ebcb', '#f3e0a6'];
    }

    init() {
        this.createCanvas();
        this.generateGrains();
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
        this.grains = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'rice-grains-canvas';
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

    createGrain(fromTop = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: fromTop ? -20 - Math.random() * 120 : Math.random() * this.canvas.height,
            vx: (Math.random() - 0.5) * 0.7,
            vy: Math.random() * 0.75 + 0.45,
            width: Math.random() * 4 + 3,
            height: Math.random() * 1.8 + 1.6,
            rotation: Math.random() * Math.PI,
            spin: (Math.random() - 0.5) * 0.05,
            color: this.palette[Math.floor(Math.random() * this.palette.length)],
        };
    }

    generateGrains() {
        for (let index = 0; index < 72; index += 1) {
            this.grains.push(this.createGrain(index > 40));
        }
    }

    drawGrain(grain) {
        this.ctx.save();
        this.ctx.translate(grain.x, grain.y);
        this.ctx.rotate(grain.rotation);
        this.ctx.fillStyle = grain.color;
        this.ctx.shadowBlur = 4;
        this.ctx.shadowColor = 'rgba(255, 244, 210, 0.55)';
        this.ctx.beginPath();
        this.ctx.ellipse(0, 0, grain.width, grain.height, 0, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        this.grains.forEach((grain) => {
            grain.x += grain.vx;
            grain.y += grain.vy;
            grain.rotation += grain.spin;

            if (grain.y > this.canvas.height + 30) {
                Object.assign(grain, this.createGrain(true));
            }

            this.drawGrain(grain);
        });

        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

window.RiceGrainsEffect = RiceGrainsEffect;
