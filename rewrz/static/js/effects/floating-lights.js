/**
 * 漂浮光点特效
 * 适合中元、中秋、冬夜等静态氛围场景
 */

class FloatingLightsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.lights = [];
        this.animationId = null;
        this.palette = ['#ffdca8', '#ffefc9', '#ffe0a3', '#fff4d8'];
    }

    init() {
        this.createCanvas();
        this.generateLights();
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
        this.lights = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'floating-lights-canvas';
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

    createLight(reset = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: reset ? this.canvas.height + Math.random() * 40 : Math.random() * this.canvas.height,
            vx: (Math.random() - 0.5) * 0.45,
            vy: -(Math.random() * 0.35 + 0.15),
            radius: Math.random() * 10 + 8,
            core: Math.random() * 2.2 + 1.5,
            alpha: Math.random() * 0.28 + 0.18,
            drift: Math.random() * 0.02 + 0.006,
            color: this.palette[Math.floor(Math.random() * this.palette.length)],
        };
    }

    generateLights() {
        for (let index = 0; index < 24; index += 1) {
            this.lights.push(this.createLight(false));
        }
    }

    drawLight(light) {
        this.ctx.save();
        this.ctx.globalAlpha = light.alpha;
        this.ctx.fillStyle = light.color;
        this.ctx.shadowBlur = light.radius;
        this.ctx.shadowColor = light.color;
        this.ctx.beginPath();
        this.ctx.arc(light.x, light.y, light.core, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        this.lights.forEach((light, index) => {
            light.x += light.vx + Math.sin((Date.now() + index * 120) * light.drift) * 0.5;
            light.y += light.vy;

            if (light.y < -30) {
                Object.assign(light, this.createLight(true));
            }

            this.drawLight(light);
        });

        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

window.FloatingLightsEffect = FloatingLightsEffect;
