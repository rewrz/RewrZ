/**
 * 龙形轮廓特效
 * 适合龙抬头与传统龙元素场景
 */

class DragonShapeEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.animationId = null;
        this.offset = 0;
    }

    init() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'dragon-shape-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9997;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        this.animate();
    }

    animate() {
        const width = this.canvas.width;
        const height = this.canvas.height;
        this.offset += 0.02;
        this.ctx.clearRect(0, 0, width, height);
        this.ctx.save();
        this.ctx.translate(width * 0.18, height * 0.28);
        this.ctx.strokeStyle = 'rgba(245, 190, 72, 0.55)';
        this.ctx.lineWidth = 6;
        this.ctx.lineCap = 'round';
        this.ctx.beginPath();
        for (let x = 0; x < width * 0.55; x += 8) {
            const y = Math.sin((x * 0.02) + this.offset) * 34 + Math.sin((x * 0.04) + this.offset * 0.6) * 12;
            if (x === 0) this.ctx.moveTo(x, y);
            else this.ctx.lineTo(x, y);
        }
        this.ctx.stroke();
        this.ctx.fillStyle = 'rgba(255, 220, 120, 0.68)';
        this.ctx.beginPath();
        this.ctx.arc(width * 0.55, Math.sin(this.offset) * 20, 16, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.restore();
        this.animationId = requestAnimationFrame(() => this.animate());
    }

    stop() {
        if (this.animationId) cancelAnimationFrame(this.animationId);
        if (this.canvas) document.body.removeChild(this.canvas);
        this.canvas = null;
        this.animationId = null;
    }
}

window.DragonShapeEffect = DragonShapeEffect;
