/**
 * 圣诞树灯串特效
 * 适合圣诞节与节庆灯饰场景
 */

class TreeLightsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.animationId = null;
        this.lights = [];
    }

    init() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'tree-lights-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9997;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        this.generateLights();
        this.animate();
    }

    generateLights() {
        const cx = this.canvas.width * 0.12;
        const cy = this.canvas.height * 0.78;
        this.lights = [];
        for (let row = 0; row < 7; row += 1) {
            const count = 3 + row;
            for (let i = 0; i < count; i += 1) {
                this.lights.push({
                    x: cx + (i - (count - 1) / 2) * 18,
                    y: cy - row * 22,
                    color: ['#f94144', '#f9c74f', '#90be6d', '#4cc9f0'][Math.floor(Math.random() * 4)],
                    pulse: Math.random() * 0.02 + 0.01,
                });
            }
        }
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        const cx = this.canvas.width * 0.12;
        const cy = this.canvas.height * 0.78;
        this.ctx.save();
        this.ctx.fillStyle = 'rgba(32, 94, 55, 0.45)';
        this.ctx.beginPath();
        this.ctx.moveTo(cx, cy - 180);
        this.ctx.lineTo(cx - 90, cy);
        this.ctx.lineTo(cx + 90, cy);
        this.ctx.closePath();
        this.ctx.fill();
        this.ctx.fillStyle = 'rgba(103, 76, 56, 0.55)';
        this.ctx.fillRect(cx - 10, cy, 20, 34);
        this.lights.forEach((light, index) => {
            const alpha = 0.6 + Math.sin(Date.now() * light.pulse + index) * 0.4;
            this.ctx.globalAlpha = alpha;
            this.ctx.fillStyle = light.color;
            this.ctx.shadowBlur = 12;
            this.ctx.shadowColor = light.color;
            this.ctx.beginPath();
            this.ctx.arc(light.x, light.y, 4, 0, Math.PI * 2);
            this.ctx.fill();
        });
        this.ctx.restore();
        this.animationId = requestAnimationFrame(() => this.animate());
    }

    stop() {
        if (this.animationId) cancelAnimationFrame(this.animationId);
        if (this.canvas) document.body.removeChild(this.canvas);
        this.canvas = null;
        this.lights = [];
        this.animationId = null;
    }
}

window.TreeLightsEffect = TreeLightsEffect;
