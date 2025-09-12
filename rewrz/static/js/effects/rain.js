/**
 * 下雨特效
 * 用于雨季、忧郁氛围等场合
 */

class RainEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.raindrops = [];
        this.animationId = null;
    }

    init() {
        this.createCanvas();
        this.generateRaindrops();
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
        
        this.raindrops = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'rain-canvas';
        this.canvas.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 9999;
        `;
        
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        
        document.body.appendChild(this.canvas);
        
        // 监听窗口大小变化
        window.addEventListener('resize', () => {
            this.canvas.width = window.innerWidth;
            this.canvas.height = window.innerHeight;
        });
    }

    generateRaindrops() {
        const count = 200;
        for (let i = 0; i < count; i++) {
            this.raindrops.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height - this.canvas.height,
                length: Math.random() * 20 + 10,
                speed: Math.random() * 8 + 5,
                opacity: Math.random() * 0.6 + 0.4
            });
        }
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        for (let i = this.raindrops.length - 1; i >= 0; i--) {
            const drop = this.raindrops[i];
            
            // 绘制雨滴
            this.ctx.save();
            this.ctx.globalAlpha = drop.opacity;
            this.ctx.strokeStyle = '#87CEEB';
            this.ctx.lineWidth = 1;
            this.ctx.beginPath();
            this.ctx.moveTo(drop.x, drop.y);
            this.ctx.lineTo(drop.x - 2, drop.y + drop.length);
            this.ctx.stroke();
            this.ctx.restore();
            
            // 更新位置
            drop.y += drop.speed;
            drop.x -= 1; // 斜向下落
            
            // 移除超出屏幕的雨滴
            if (drop.y > this.canvas.height + 50) {
                this.raindrops.splice(i, 1);
            }
        }
        
        // 持续生成新的雨滴
        if (this.raindrops.length < 150) {
            for (let i = 0; i < 5; i++) {
                this.raindrops.push({
                    x: Math.random() * (this.canvas.width + 100),
                    y: -50,
                    length: Math.random() * 20 + 10,
                    speed: Math.random() * 8 + 5,
                    opacity: Math.random() * 0.6 + 0.4
                });
            }
        }
        
        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

// 导出效果类
window.RainEffect = RainEffect;