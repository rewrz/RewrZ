/**
 * 月光特效
 * 适合中秋、冬至与夜景静态氛围
 */

class MoonlightEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.animationId = null;
        this.haloPulse = 0;
    }

    init() {
        this.createCanvas();
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
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'moonlight-canvas';
        this.canvas.style.cssText = `
            position: fixed;
            inset: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 9996;
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

    animate() {
        const width = this.canvas.width;
        const height = this.canvas.height;
        const moonX = width * 0.82;
        const moonY = height * 0.18;
        const radius = Math.max(42, Math.min(width, height) * 0.055);

        this.haloPulse += 0.012;
        this.ctx.clearRect(0, 0, width, height);

        const overlay = this.ctx.createLinearGradient(0, 0, 0, height);
        overlay.addColorStop(0, 'rgba(82, 109, 168, 0.08)');
        overlay.addColorStop(1, 'rgba(15, 23, 42, 0.02)');
        this.ctx.fillStyle = overlay;
        this.ctx.fillRect(0, 0, width, height);

        const haloRadius = radius * (2.5 + Math.sin(this.haloPulse) * 0.12);
        const halo = this.ctx.createRadialGradient(moonX, moonY, radius * 0.15, moonX, moonY, haloRadius);
        halo.addColorStop(0, 'rgba(255, 249, 214, 0.45)');
        halo.addColorStop(0.6, 'rgba(255, 244, 190, 0.14)');
        halo.addColorStop(1, 'rgba(255, 244, 190, 0)');
        this.ctx.fillStyle = halo;
        this.ctx.beginPath();
        this.ctx.arc(moonX, moonY, haloRadius, 0, Math.PI * 2);
        this.ctx.fill();

        const moon = this.ctx.createRadialGradient(moonX - radius * 0.25, moonY - radius * 0.25, radius * 0.2, moonX, moonY, radius);
        moon.addColorStop(0, '#fffdf0');
        moon.addColorStop(0.75, '#fff1bf');
        moon.addColorStop(1, '#f5db8f');
        this.ctx.fillStyle = moon;
        this.ctx.beginPath();
        this.ctx.arc(moonX, moonY, radius, 0, Math.PI * 2);
        this.ctx.fill();

        this.ctx.fillStyle = 'rgba(220, 199, 138, 0.18)';
        [
            { x: moonX - radius * 0.22, y: moonY - radius * 0.08, r: radius * 0.16 },
            { x: moonX + radius * 0.18, y: moonY + radius * 0.05, r: radius * 0.12 },
            { x: moonX + radius * 0.02, y: moonY - radius * 0.26, r: radius * 0.09 },
        ].forEach((crater) => {
            this.ctx.beginPath();
            this.ctx.arc(crater.x, crater.y, crater.r, 0, Math.PI * 2);
            this.ctx.fill();
        });

        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

window.MoonlightEffect = MoonlightEffect;
