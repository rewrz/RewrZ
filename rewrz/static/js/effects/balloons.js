/**
 * 气球上升特效
 * 适合儿童节、生日与欢庆场景
 */

class BalloonsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.balloons = [];
        this.animationId = null;
        this.palette = ['#ff6b6b', '#ffd166', '#4ecdc4', '#6ea8fe', '#c77dff', '#ff8fab'];
    }

    init() {
        this.createCanvas();
        this.generateBalloons();
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
        this.balloons = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'balloons-canvas';
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

    createBalloon(fromBottom = false) {
        const radius = Math.random() * 18 + 18;
        return {
            x: Math.random() * this.canvas.width,
            y: fromBottom ? this.canvas.height + radius + Math.random() * 120 : Math.random() * this.canvas.height,
            vx: (Math.random() - 0.5) * 0.45,
            vy: -(Math.random() * 0.6 + 0.55),
            sway: Math.random() * 0.02 + 0.01,
            radius,
            color: this.palette[Math.floor(Math.random() * this.palette.length)],
            stringLength: Math.random() * 28 + 24,
        };
    }

    generateBalloons() {
        for (let index = 0; index < 18; index += 1) {
            this.balloons.push(this.createBalloon(index > 8));
        }
    }

    drawBalloon(balloon, index) {
        const swayX = Math.sin((Date.now() + index * 120) * balloon.sway) * 8;
        const x = balloon.x + swayX;
        const y = balloon.y;

        this.ctx.save();

        const gradient = this.ctx.createRadialGradient(x - balloon.radius * 0.3, y - balloon.radius * 0.35, 2, x, y, balloon.radius);
        gradient.addColorStop(0, 'rgba(255,255,255,0.78)');
        gradient.addColorStop(0.22, balloon.color);
        gradient.addColorStop(1, 'rgba(0,0,0,0.08)');

        this.ctx.fillStyle = gradient;
        this.ctx.beginPath();
        this.ctx.ellipse(x, y, balloon.radius * 0.9, balloon.radius * 1.12, 0, 0, Math.PI * 2);
        this.ctx.fill();

        this.ctx.fillStyle = balloon.color;
        this.ctx.beginPath();
        this.ctx.moveTo(x, y + balloon.radius * 1.1);
        this.ctx.lineTo(x - 4, y + balloon.radius * 1.36);
        this.ctx.lineTo(x + 4, y + balloon.radius * 1.36);
        this.ctx.closePath();
        this.ctx.fill();

        this.ctx.strokeStyle = 'rgba(255,255,255,0.5)';
        this.ctx.lineWidth = 1.3;
        this.ctx.beginPath();
        this.ctx.moveTo(x, y + balloon.radius * 1.36);
        this.ctx.quadraticCurveTo(x + swayX * 0.35, y + balloon.radius * 2.15, x + Math.sin(index + Date.now() * 0.001) * 10, y + balloon.radius * 1.36 + balloon.stringLength);
        this.ctx.stroke();

        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        this.balloons.forEach((balloon, index) => {
            balloon.x += balloon.vx;
            balloon.y += balloon.vy;

            if (balloon.y < -80) {
                Object.assign(balloon, this.createBalloon(true));
            }

            this.drawBalloon(balloon, index);
        });

        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

window.BalloonsEffect = BalloonsEffect;
