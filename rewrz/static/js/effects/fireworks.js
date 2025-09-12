/**
 * 烟花特效
 * 用于节日庆典、新年等喜庆场合
 */

class FireworksEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.fireworks = [];
        this.particles = [];
        this.animationId = null;
        this.intervalId = null;
        this.colors = [
            '#ff1744', '#ff9800', '#ffeb3b', '#4caf50', 
            '#2196f3', '#9c27b0', '#e91e63', '#00bcd4'
        ];
    }

    init() {
        this.createCanvas();
        this.animate();
        
        // 每2-4秒发射一次烟花
        this.intervalId = setInterval(() => {
            this.createFirework();
        }, Math.random() * 2000 + 2000);
        
        // 立即发射第一个烟花
        this.createFirework();
    }

    stop() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
            this.animationId = null;
        }
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
        if (this.canvas) {
            document.body.removeChild(this.canvas);
            this.canvas = null;
        }
        this.fireworks = [];
        this.particles = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'fireworks-canvas';
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

    createFirework() {
        const firework = {
            x: Math.random() * this.canvas.width,
            y: this.canvas.height,
            targetY: Math.random() * this.canvas.height * 0.5 + 50,
            vx: (Math.random() - 0.5) * 4,
            vy: -Math.random() * 8 - 8,
            color: this.colors[Math.floor(Math.random() * this.colors.length)],
            exploded: false,
            trail: []
        };
        
        this.fireworks.push(firework);
    }

    createExplosion(x, y, color) {
        const particleCount = 30 + Math.random() * 20;
        
        for (let i = 0; i < particleCount; i++) {
            const angle = (Math.PI * 2 * i) / particleCount;
            const velocity = Math.random() * 6 + 2;
            
            this.particles.push({
                x: x,
                y: y,
                vx: Math.cos(angle) * velocity,
                vy: Math.sin(angle) * velocity,
                color: color,
                alpha: 1,
                decay: Math.random() * 0.02 + 0.01,
                size: Math.random() * 3 + 1
            });
        }
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        // 更新烟花
        for (let i = this.fireworks.length - 1; i >= 0; i--) {
            const firework = this.fireworks[i];
            
            // 添加轨迹
            firework.trail.push({ x: firework.x, y: firework.y });
            if (firework.trail.length > 10) {
                firework.trail.shift();
            }
            
            // 绘制轨迹
            this.ctx.strokeStyle = firework.color;
            this.ctx.lineWidth = 2;
            this.ctx.beginPath();
            for (let j = 0; j < firework.trail.length; j++) {
                const point = firework.trail[j];
                if (j === 0) {
                    this.ctx.moveTo(point.x, point.y);
                } else {
                    this.ctx.lineTo(point.x, point.y);
                }
            }
            this.ctx.stroke();
            
            // 更新位置
            firework.x += firework.vx;
            firework.y += firework.vy;
            firework.vy += 0.2; // 重力
            
            // 检查是否到达目标高度或开始下降
            if (firework.y <= firework.targetY || firework.vy >= 0) {
                this.createExplosion(firework.x, firework.y, firework.color);
                this.fireworks.splice(i, 1);
            }
        }

        // 更新粒子
        for (let i = this.particles.length - 1; i >= 0; i--) {
            const particle = this.particles[i];
            
            particle.x += particle.vx;
            particle.y += particle.vy;
            particle.vy += 0.1; // 重力
            particle.alpha -= particle.decay;
            
            // 绘制粒子
            this.ctx.save();
            this.ctx.globalAlpha = particle.alpha;
            this.ctx.fillStyle = particle.color;
            this.ctx.beginPath();
            this.ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
            this.ctx.fill();
            this.ctx.restore();
            
            // 移除消失的粒子
            if (particle.alpha <= 0) {
                this.particles.splice(i, 1);
            }
        }

        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

// 导出效果类
window.FireworksEffect = FireworksEffect;