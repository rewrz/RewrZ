/**
 * 气泡特效
 * 适合儿童节、夏季与轻盈氛围
 */

class BubblesEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.bubbles = [];
        this.animationId = null;
    }

    init() {
        this.createCanvas();
        this.generateBubbles();
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
        this.bubbles = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'bubbles-canvas';
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

    createBubble(fromBottom = false) {
        return {
            x: Math.random() * this.canvas.width,
            y: fromBottom ? this.canvas.height + Math.random() * 60 : Math.random() * this.canvas.height,
            radius: Math.random() * 16 + 6,
            vx: (Math.random() - 0.5) * 0.5,
            vy: -(Math.random() * 0.7 + 0.3),
            alpha: Math.random() * 0.32 + 0.16,
            wobble: Math.random() * 0.03 + 0.01,
        };
    }

    generateBubbles() {
        for (let index = 0; index < 36; index += 1) {
            this.bubbles.push(this.createBubble(index > 20));
        }
    }

    drawBubble(bubble, index) {
        const offsetX = Math.sin((Date.now() + index * 70) * bubble.wobble) * 5;
        const x = bubble.x + offsetX;
        const y = bubble.y;

        this.ctx.save();
        this.ctx.globalAlpha = bubble.alpha;
        this.ctx.lineWidth = 1.5;
        this.ctx.strokeStyle = 'rgba(210, 242, 255, 0.9)';
        this.ctx.fillStyle = 'rgba(196, 237, 255, 0.15)';
        this.ctx.beginPath();
        this.ctx.arc(x, y, bubble.radius, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.stroke();

        this.ctx.fillStyle = 'rgba(255,255,255,0.55)';
        this.ctx.beginPath();
        this.ctx.arc(x - bubble.radius * 0.3, y - bubble.radius * 0.35, bubble.radius * 0.18, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        this.bubbles.forEach((bubble, index) => {
            bubble.y += bubble.vy;
            bubble.x += bubble.vx;

            if (bubble.y < -30) {
                Object.assign(bubble, this.createBubble(true));
            }

            this.drawBubble(bubble, index);
        });

        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

window.BubblesEffect = BubblesEffect;
