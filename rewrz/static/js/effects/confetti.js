/**
 * 彩带飞舞特效
 * 用于庆祝活动、生日等欢乐场合
 */

class ConfettiEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.confetti = [];
        this.animationId = null;
        this.colors = [
            '#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4', 
            '#feca57', '#ff9ff3', '#54a0ff', '#5f27cd'
        ];
    }

    init() {
        this.createCanvas();
        this.generateConfetti();
        this.animate();
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'confetti-canvas';
        this.canvas.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 9999;
        `;
        
        // 确保canvas存在再设置宽高
        if (this.canvas) {
            this.canvas.width = window.innerWidth;
            this.canvas.height = window.innerHeight;
            this.ctx = this.canvas.getContext('2d');
            
            document.body.appendChild(this.canvas);
            
            // 监听窗口大小变化
            window.addEventListener('resize', () => {
                if (this.canvas) {
                    this.canvas.width = window.innerWidth;
                    this.canvas.height = window.innerHeight;
                }
            });
        }
    }

    generateConfetti() {
        const count = 150;
        for (let i = 0; i < count; i++) {
            this.confetti.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height - this.canvas.height,
                vx: (Math.random() - 0.5) * 3,
                vy: Math.random() * 3 + 2,
                rotation: Math.random() * 360,
                rotationSpeed: (Math.random() - 0.5) * 10,
                color: this.colors[Math.floor(Math.random() * this.colors.length)],
                size: Math.random() * 8 + 4,
                shape: Math.random() > 0.5 ? 'rect' : 'circle'
            });
        }
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        for (let i = this.confetti.length - 1; i >= 0; i--) {
            const piece = this.confetti[i];
            
            // 更新位置
            piece.x += piece.vx;
            piece.y += piece.vy;
            piece.rotation += piece.rotationSpeed;
            
            // 重力效果
            piece.vy += 0.1;
            
            // 绘制彩带片
            this.ctx.save();
            this.ctx.translate(piece.x, piece.y);
            this.ctx.rotate(piece.rotation * Math.PI / 180);
            this.ctx.fillStyle = piece.color;
            
            if (piece.shape === 'rect') {
                this.ctx.fillRect(-piece.size/2, -piece.size/4, piece.size, piece.size/2);
            } else {
                this.ctx.beginPath();
                this.ctx.arc(0, 0, piece.size/2, 0, Math.PI * 2);
                this.ctx.fill();
            }
            
            this.ctx.restore();
            
            // 移除超出屏幕的彩带
            if (piece.y > this.canvas.height + 50) {
                this.confetti.splice(i, 1);
            }
        }
        
        // 持续生成新的彩带
        if (this.confetti.length < 50) {
            for (let i = 0; i < 5; i++) {
                this.confetti.push({
                    x: Math.random() * this.canvas.width,
                    y: -50,
                    vx: (Math.random() - 0.5) * 3,
                    vy: Math.random() * 3 + 2,
                    rotation: Math.random() * 360,
                    rotationSpeed: (Math.random() - 0.5) * 10,
                    color: this.colors[Math.floor(Math.random() * this.colors.length)],
                    size: Math.random() * 8 + 4,
                    shape: Math.random() > 0.5 ? 'rect' : 'circle'
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
        
        this.confetti = [];
    }
}

// 导出效果类
window.ConfettiEffect = ConfettiEffect;