/**
 * 落叶纷飞特效
 * 用于秋季主题、季节变换等场合
 */

class LeavesEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.leaves = [];
        this.animationId = null;
        this.colors = [
            '#d2691e', '#cd853f', '#daa520', '#b8860b',
            '#ff8c00', '#ff7f50', '#dc143c', '#8b4513'
        ];
    }

    init() {
        this.createCanvas();
        this.generateLeaves();
        this.animate();
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'leaves-canvas';
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

    generateLeaves() {
        const count = 60;
        for (let i = 0; i < count; i++) {
            this.leaves.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height - this.canvas.height,
                vx: (Math.random() - 0.5) * 3,
                vy: Math.random() * 2 + 1.5,
                rotation: Math.random() * 360,
                rotationSpeed: (Math.random() - 0.5) * 6,
                color: this.colors[Math.floor(Math.random() * this.colors.length)],
                size: Math.random() * 12 + 8,
                opacity: Math.random() * 0.8 + 0.2,
                swing: Math.random() * 0.03 + 0.01,
                type: Math.floor(Math.random() * 3) // 不同的叶子形状
            });
        }
    }

    drawLeaf(leaf) {
        this.ctx.save();
        this.ctx.translate(leaf.x, leaf.y);
        this.ctx.rotate(leaf.rotation * Math.PI / 180);
        this.ctx.globalAlpha = leaf.opacity;
        this.ctx.fillStyle = leaf.color;
        
        // 根据类型绘制不同形状的叶子
        switch (leaf.type) {
            case 0: // 椭圆形叶子
                this.ctx.beginPath();
                this.ctx.ellipse(0, 0, leaf.size, leaf.size * 0.6, 0, 0, Math.PI * 2);
                this.ctx.fill();
                break;
                
            case 1: // 枫叶形状
                this.ctx.beginPath();
                this.ctx.moveTo(0, -leaf.size);
                this.ctx.lineTo(leaf.size * 0.3, -leaf.size * 0.3);
                this.ctx.lineTo(leaf.size * 0.8, -leaf.size * 0.5);
                this.ctx.lineTo(leaf.size * 0.5, 0);
                this.ctx.lineTo(leaf.size * 0.8, leaf.size * 0.5);
                this.ctx.lineTo(leaf.size * 0.3, leaf.size * 0.3);
                this.ctx.lineTo(0, leaf.size);
                this.ctx.lineTo(-leaf.size * 0.3, leaf.size * 0.3);
                this.ctx.lineTo(-leaf.size * 0.8, leaf.size * 0.5);
                this.ctx.lineTo(-leaf.size * 0.5, 0);
                this.ctx.lineTo(-leaf.size * 0.8, -leaf.size * 0.5);
                this.ctx.lineTo(-leaf.size * 0.3, -leaf.size * 0.3);
                this.ctx.closePath();
                this.ctx.fill();
                break;
                
            case 2: // 心形叶子
                this.ctx.beginPath();
                this.ctx.moveTo(0, leaf.size * 0.3);
                this.ctx.bezierCurveTo(-leaf.size * 0.5, -leaf.size * 0.3, -leaf.size, -leaf.size * 0.3, -leaf.size * 0.5, 0);
                this.ctx.bezierCurveTo(-leaf.size, leaf.size * 0.3, -leaf.size * 0.5, leaf.size * 0.6, 0, leaf.size);
                this.ctx.bezierCurveTo(leaf.size * 0.5, leaf.size * 0.6, leaf.size, leaf.size * 0.3, leaf.size * 0.5, 0);
                this.ctx.bezierCurveTo(leaf.size, -leaf.size * 0.3, leaf.size * 0.5, -leaf.size * 0.3, 0, leaf.size * 0.3);
                this.ctx.fill();
                break;
        }
        
        // 添加叶脉
        this.ctx.strokeStyle = 'rgba(0, 0, 0, 0.3)';
        this.ctx.lineWidth = 1;
        this.ctx.beginPath();
        this.ctx.moveTo(0, -leaf.size * 0.8);
        this.ctx.lineTo(0, leaf.size * 0.8);
        this.ctx.stroke();
        
        // 添加侧脉
        this.ctx.lineWidth = 0.5;
        for (let i = -2; i <= 2; i++) {
            if (i !== 0) {
                this.ctx.beginPath();
                this.ctx.moveTo(0, i * leaf.size * 0.2);
                this.ctx.lineTo(leaf.size * 0.3 * Math.sign(i), i * leaf.size * 0.2 + leaf.size * 0.1);
                this.ctx.stroke();
            }
        }
        
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        for (let i = this.leaves.length - 1; i >= 0; i--) {
            const leaf = this.leaves[i];
            
            // 更新位置
            leaf.x += leaf.vx + Math.sin(Date.now() * leaf.swing) * 1;
            leaf.y += leaf.vy;
            leaf.rotation += leaf.rotationSpeed;
            
            // 风的影响
            leaf.vx += (Math.random() - 0.5) * 0.2;
            leaf.vx *= 0.95; // 阻力
            
            // 重力影响
            leaf.vy += 0.05;
            
            // 绘制叶子
            this.drawLeaf(leaf);
            
            // 移除超出屏幕的叶子
            if (leaf.y > this.canvas.height + 50) {
                this.leaves.splice(i, 1);
            }
        }
        
        // 持续生成新的叶子
        if (this.leaves.length < 40) {
            for (let i = 0; i < 2; i++) {
                this.leaves.push({
                    x: Math.random() * this.canvas.width,
                    y: -50,
                    vx: (Math.random() - 0.5) * 3,
                    vy: Math.random() * 2 + 1.5,
                    rotation: Math.random() * 360,
                    rotationSpeed: (Math.random() - 0.5) * 6,
                    color: this.colors[Math.floor(Math.random() * this.colors.length)],
                    size: Math.random() * 12 + 8,
                    opacity: Math.random() * 0.8 + 0.2,
                    swing: Math.random() * 0.03 + 0.01,
                    type: Math.floor(Math.random() * 3)
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
        
        this.leaves = [];
    }
}

// 导出效果类
window.LeavesEffect = LeavesEffect;