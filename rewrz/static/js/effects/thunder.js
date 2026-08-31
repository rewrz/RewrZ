/**
 * 打雷特效
 * 用于暴雨、戏剧性氛围等场合
 */

class ThunderEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.lightnings = [];
        this.animationId = null;
        this.intervalId = null;
        this.flashOverlay = null;
    }

    init() {
        this.createCanvas();
        this.createFlashOverlay();
        this.animate();
        
        // 每3-8秒打一次雷
        this.intervalId = setInterval(() => {
            this.createLightning();
        }, Math.random() * 5000 + 3000);
        
        // 立即打第一个雷
        setTimeout(() => this.createLightning(), 1000);
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
        if (this.flashOverlay) {
            document.body.removeChild(this.flashOverlay);
            this.flashOverlay = null;
        }
        this.lightnings = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'thunder-canvas';
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

    createFlashOverlay() {
        this.flashOverlay = document.createElement('div');
        this.flashOverlay.id = 'thunder-flash';
        this.flashOverlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: white;
            opacity: 0;
            pointer-events: none;
            z-index: 9998;
        `;
        document.body.appendChild(this.flashOverlay);
    }

    createLightning() {
        const startX = Math.random() * this.canvas.width;
        const startY = 0;
        const endX = startX + (Math.random() - 0.5) * 200;
        const endY = this.canvas.height * (0.3 + Math.random() * 0.4);
        
        const lightning = {
            points: this.generateLightningPath(startX, startY, endX, endY),
            life: 1,
            decay: 0.05,
            branches: []
        };
        
        // 生成分支
        const branchCount = Math.floor(Math.random() * 3) + 1;
        for (let i = 0; i < branchCount; i++) {
            const branchPoint = Math.floor(lightning.points.length * (0.3 + Math.random() * 0.4));
            const point = lightning.points[branchPoint];
            if (point) {
                const branchEndX = point.x + (Math.random() - 0.5) * 150;
                const branchEndY = point.y + Math.random() * 100 + 50;
                lightning.branches.push(
                    this.generateLightningPath(point.x, point.y, branchEndX, branchEndY)
                );
            }
        }
        
        this.lightnings.push(lightning);
        
        // 闪光效果
        this.flash();
    }

    generateLightningPath(startX, startY, endX, endY) {
        const points = [];
        const segments = 20;
        
        for (let i = 0; i <= segments; i++) {
            const t = i / segments;
            const x = startX + (endX - startX) * t + (Math.random() - 0.5) * 30;
            const y = startY + (endY - startY) * t + (Math.random() - 0.5) * 20;
            points.push({ x, y });
        }
        
        return points;
    }

    flash() {
        // 闪光动画
        this.flashOverlay.style.opacity = '0.8';
        setTimeout(() => {
            this.flashOverlay.style.opacity = '0';
        }, 100);
        
        setTimeout(() => {
            this.flashOverlay.style.opacity = '0.6';
            setTimeout(() => {
                this.flashOverlay.style.opacity = '0';
            }, 50);
        }, 200);
    }

    drawLightning(lightning) {
        this.ctx.save();
        this.ctx.globalAlpha = lightning.life;
        this.ctx.strokeStyle = '#ffffff';
        this.ctx.lineWidth = 3;
        this.ctx.shadowBlur = 10;
        this.ctx.shadowColor = '#87CEEB';
        
        // 绘制主闪电
        this.ctx.beginPath();
        for (let i = 0; i < lightning.points.length; i++) {
            const point = lightning.points[i];
            if (i === 0) {
                this.ctx.moveTo(point.x, point.y);
            } else {
                this.ctx.lineTo(point.x, point.y);
            }
        }
        this.ctx.stroke();
        
        // 绘制分支
        lightning.branches.forEach(branch => {
            this.ctx.beginPath();
            for (let i = 0; i < branch.length; i++) {
                const point = branch[i];
                if (i === 0) {
                    this.ctx.moveTo(point.x, point.y);
                } else {
                    this.ctx.lineTo(point.x, point.y);
                }
            }
            this.ctx.stroke();
        });
        
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        // 更新和绘制闪电
        for (let i = this.lightnings.length - 1; i >= 0; i--) {
            const lightning = this.lightnings[i];
            
            this.drawLightning(lightning);
            
            lightning.life -= lightning.decay;
            
            if (lightning.life <= 0) {
                this.lightnings.splice(i, 1);
            }
        }
        
        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

// 导出效果类
window.ThunderEffect = ThunderEffect;