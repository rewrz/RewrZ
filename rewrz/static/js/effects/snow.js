/**
 * 雪花飘落特效
 * 用于冬季、圣诞节等场合
 */

class SnowEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.snowflakes = [];
        this.animationId = null;
    }

    init() {
        this.createCanvas();
        this.generateSnowflakes();
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
        
        this.snowflakes = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'snow-canvas';
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
        this.handleWindowResize = () => {
            this.canvas.width = window.innerWidth;
            this.canvas.height = window.innerHeight;
        };
    }

    generateSnowflakes() {
        const count = 100;
        for (let i = 0; i < count; i++) {
            this.snowflakes.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height - this.canvas.height,
                vx: (Math.random() - 0.5) * 2,
                vy: Math.random() * 2 + 1,
                size: Math.random() * 4 + 2,
                opacity: Math.random() * 0.8 + 0.2,
                swing: Math.random() * 0.02 + 0.01
            });
        }
    }

    drawSnowflake(snowflake) {
        this.ctx.save();
        this.ctx.globalAlpha = snowflake.opacity;
        this.ctx.fillStyle = '#ffffff';
        
        // 绘制雪花
        this.ctx.beginPath();
        this.ctx.arc(snowflake.x, snowflake.y, snowflake.size, 0, Math.PI * 2);
        this.ctx.fill();
        
        // 添加雪花的十字形状
        this.ctx.strokeStyle = '#ffffff';
        this.ctx.lineWidth = 1;
        this.ctx.beginPath();
        this.ctx.moveTo(snowflake.x - snowflake.size, snowflake.y);
        this.ctx.lineTo(snowflake.x + snowflake.size, snowflake.y);
        this.ctx.moveTo(snowflake.x, snowflake.y - snowflake.size);
        this.ctx.lineTo(snowflake.x, snowflake.y + snowflake.size);
        this.ctx.stroke();
        
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        for (let i = this.snowflakes.length - 1; i >= 0; i--) {
            const snowflake = this.snowflakes[i];
            
            // 更新位置
            snowflake.x += snowflake.vx + Math.sin(Date.now() * snowflake.swing) * 0.5;
            snowflake.y += snowflake.vy;
            
            // 轻微的左右摆动
            snowflake.vx += (Math.random() - 0.5) * 0.1;
            snowflake.vx *= 0.98; // 阻力
            
            // 绘制雪花
            this.drawSnowflake(snowflake);
            
            // 移除超出屏幕的雪花
            if (snowflake.y > this.canvas.height + 50) {
                this.snowflakes.splice(i, 1);
            }
        }
        
        // 持续生成新的雪花
        if (this.snowflakes.length < 80) {
            for (let i = 0; i < 3; i++) {
                this.snowflakes.push({
                    x: Math.random() * this.canvas.width,
                    y: -50,
                    vx: (Math.random() - 0.5) * 2,
                    vy: Math.random() * 2 + 1,
                    size: Math.random() * 4 + 2,
                    opacity: Math.random() * 0.8 + 0.2,
                    swing: Math.random() * 0.02 + 0.01
                });
            }
        }
        
        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

// 导出效果类
window.SnowEffect = SnowEffect;