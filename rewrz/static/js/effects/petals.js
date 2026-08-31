/**
 * 花瓣飘落特效
 * 用于纪念、追思等温馨场合
 */

class PetalsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.petals = [];
        this.animationId = null;
        this.colors = [
            '#ffb3ba', '#ffdfba', '#ffffba', '#baffc9', 
            '#bae1ff', '#e6ccff', '#ffc9de', '#c9ffba'
        ];
    }

    init() {
        this.createCanvas();
        this.generatePetals();
        this.animate();
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'petals-canvas';
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

    generatePetals() {
        const count = 80;
        for (let i = 0; i < count; i++) {
            this.petals.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height - this.canvas.height,
                vx: (Math.random() - 0.5) * 2,
                vy: Math.random() * 2 + 1,
                rotation: Math.random() * 360,
                rotationSpeed: (Math.random() - 0.5) * 4,
                color: this.colors[Math.floor(Math.random() * this.colors.length)],
                size: Math.random() * 8 + 6,
                opacity: Math.random() * 0.8 + 0.2,
                swing: Math.random() * 0.02 + 0.01
            });
        }
    }

    drawPetal(petal) {
        this.ctx.save();
        this.ctx.translate(petal.x, petal.y);
        this.ctx.rotate(petal.rotation * Math.PI / 180);
        this.ctx.globalAlpha = petal.opacity;
        
        // 绘制花瓣形状
        this.ctx.fillStyle = petal.color;
        this.ctx.beginPath();
        
        // 花瓣的椭圆形状
        this.ctx.ellipse(0, 0, petal.size, petal.size * 0.6, 0, 0, Math.PI * 2);
        this.ctx.fill();
        
        // 添加花瓣纹理
        this.ctx.strokeStyle = 'rgba(0, 0, 0, 0.1)';
        this.ctx.lineWidth = 0.5;
        this.ctx.beginPath();
        this.ctx.moveTo(-petal.size * 0.8, 0);
        this.ctx.lineTo(petal.size * 0.8, 0);
        this.ctx.stroke();
        
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        for (let i = this.petals.length - 1; i >= 0; i--) {
            const petal = this.petals[i];
            
            // 更新位置
            petal.x += petal.vx + Math.sin(Date.now() * petal.swing) * 0.5;
            petal.y += petal.vy;
            petal.rotation += petal.rotationSpeed;
            
            // 轻微的左右摆动
            petal.vx += (Math.random() - 0.5) * 0.1;
            petal.vx *= 0.98; // 阻力
            
            // 绘制花瓣
            this.drawPetal(petal);
            
            // 移除超出屏幕的花瓣
            if (petal.y > this.canvas.height + 50) {
                this.petals.splice(i, 1);
            }
        }
        
        // 持续生成新的花瓣
        if (this.petals.length < 60) {
            for (let i = 0; i < 3; i++) {
                this.petals.push({
                    x: Math.random() * this.canvas.width,
                    y: -50,
                    vx: (Math.random() - 0.5) * 2,
                    vy: Math.random() * 2 + 1,
                    rotation: Math.random() * 360,
                    rotationSpeed: (Math.random() - 0.5) * 4,
                    color: this.colors[Math.floor(Math.random() * this.colors.length)],
                    size: Math.random() * 8 + 6,
                    opacity: Math.random() * 0.8 + 0.2,
                    swing: Math.random() * 0.02 + 0.01
                });
            }
        }
        
        this.animationId = requestAnimationFrame(() => this.animate());
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
        
        this.petals = [];
    }
}

// 导出效果类
window.PetalsEffect = PetalsEffect;