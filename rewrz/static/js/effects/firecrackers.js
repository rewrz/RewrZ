/**
 * 爆竹特效
 * 用于新年、庆祝等场合
 */

class FirecrackersEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.crackers = [];
        this.sparks = [];
        this.animationId = null;
        this.intervalId = null;
        this.colors = ['#ff4444', '#ff8800', '#ffff00', '#ffffff'];
    }

    init() {
        this.createCanvas();
        this.animate();
        
        // 每1-3秒放一次爆竹
        this.intervalId = setInterval(() => {
            this.createFirecracker();
        }, Math.random() * 2000 + 1000);
        
        // 立即放第一个爆竹
        this.createFirecracker();
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
        this.crackers = [];
        this.sparks = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'firecrackers-canvas';
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

    createFirecracker() {
        const x = Math.random() * this.canvas.width;
        const y = this.canvas.height - 50;
        
        // 创建爆竹串
        for (let i = 0; i < 5 + Math.random() * 10; i++) {
            setTimeout(() => {
                this.explode(x + (Math.random() - 0.5) * 100, y - Math.random() * 200);
            }, i * (50 + Math.random() * 100));
        }
    }

    explode(x, y) {
        // 创建爆炸火花
        const sparkCount = 15 + Math.random() * 15;
        
        for (let i = 0; i < sparkCount; i++) {
            const angle = (Math.PI * 2 * i) / sparkCount + (Math.random() - 0.5) * 0.5;
            const velocity = Math.random() * 8 + 4;
            
            this.sparks.push({
                x: x,
                y: y,
                vx: Math.cos(angle) * velocity,
                vy: Math.sin(angle) * velocity,
                color: this.colors[Math.floor(Math.random() * this.colors.length)],
                life: 1,
                decay: Math.random() * 0.02 + 0.01,
                size: Math.random() * 3 + 1,
                trail: []
            });
        }
        
        // 创建爆炸闪光
        this.crackers.push({
            x: x,
            y: y,
            size: 20 + Math.random() * 30,
            life: 1,
            decay: 0.1,
            color: '#ffffff'
        });
    }

    animate() {
        // 清除画布，保持透明背景
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        // 更新和绘制爆竹闪光
        for (let i = this.crackers.length - 1; i >= 0; i--) {
            const cracker = this.crackers[i];
            
            // 绘制闪光
            this.ctx.save();
            this.ctx.globalAlpha = cracker.life;
            this.ctx.fillStyle = cracker.color;
            this.ctx.shadowBlur = 20;
            this.ctx.shadowColor = cracker.color;
            this.ctx.beginPath();
            this.ctx.arc(cracker.x, cracker.y, cracker.size, 0, Math.PI * 2);
            this.ctx.fill();
            this.ctx.restore();
            
            cracker.life -= cracker.decay;
            cracker.size *= 0.95;
            
            if (cracker.life <= 0) {
                this.crackers.splice(i, 1);
            }
        }

        // 更新和绘制火花
        for (let i = this.sparks.length - 1; i >= 0; i--) {
            const spark = this.sparks[i];
            
            // 添加轨迹点
            spark.trail.push({ x: spark.x, y: spark.y, life: spark.life });
            if (spark.trail.length > 8) {
                spark.trail.shift();
            }
            
            // 绘制轨迹
            for (let j = 0; j < spark.trail.length; j++) {
                const point = spark.trail[j];
                this.ctx.save();
                this.ctx.globalAlpha = point.life * (j / spark.trail.length);
                this.ctx.fillStyle = spark.color;
                this.ctx.beginPath();
                this.ctx.arc(point.x, point.y, spark.size * (j / spark.trail.length), 0, Math.PI * 2);
                this.ctx.fill();
                this.ctx.restore();
            }
            
            // 绘制火花
            this.ctx.save();
            this.ctx.globalAlpha = spark.life;
            this.ctx.fillStyle = spark.color;
            this.ctx.shadowBlur = 10;
            this.ctx.shadowColor = spark.color;
            this.ctx.beginPath();
            this.ctx.arc(spark.x, spark.y, spark.size, 0, Math.PI * 2);
            this.ctx.fill();
            this.ctx.restore();
            
            // 更新位置
            spark.x += spark.vx;
            spark.y += spark.vy;
            spark.vy += 0.2; // 重力
            spark.vx *= 0.98; // 阻力
            spark.life -= spark.decay;
            
            if (spark.life <= 0) {
                this.sparks.splice(i, 1);
            }
        }

        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

// 导出效果类
window.FirecrackersEffect = FirecrackersEffect;