/**
 * 红灯笼特效
 * 用于春节、传统节日等场合
 */

class LanternsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.lanterns = [];
        this.animationId = null;
    }

    init() {
        this.createCanvas();
        this.generateLanterns();
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
        
        this.lanterns = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'lanterns-canvas';
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
                    this.generateLanterns();
                }
            });
        }
    }

    generateLanterns() {
        this.lanterns = [];
        const count = Math.floor(this.canvas.width / 300) + 1;
        
        for (let i = 0; i < count; i++) {
            this.lanterns.push({
                x: (i + 0.5) * (this.canvas.width / count),
                y: 50 + Math.random() * 100,
                width: 60 + Math.random() * 20,
                height: 80 + Math.random() * 20,
                swingAngle: Math.random() * Math.PI * 2,
                swingSpeed: 0.02 + Math.random() * 0.02,
                swingAmplitude: 10 + Math.random() * 10
            });
        }
    }

    drawLantern(lantern) {
        this.ctx.save();
        
        // 计算摆动位置
        const swingX = Math.sin(lantern.swingAngle) * lantern.swingAmplitude;
        const currentX = lantern.x + swingX;
        
        // 绘制悬挂线
        this.ctx.strokeStyle = '#8B4513';
        this.ctx.lineWidth = 2;
        this.ctx.beginPath();
        this.ctx.moveTo(lantern.x, 0);
        this.ctx.lineTo(currentX, lantern.y);
        this.ctx.stroke();
        
        // 绘制灯笼主体
        const gradient = this.ctx.createLinearGradient(
            currentX - lantern.width/2, 
            lantern.y, 
            currentX + lantern.width/2, 
            lantern.y
        );
        gradient.addColorStop(0, '#FF4444');
        gradient.addColorStop(0.5, '#FF6666');
        gradient.addColorStop(1, '#CC2222');
        
        this.ctx.fillStyle = gradient;
        this.ctx.beginPath();
        this.ctx.ellipse(
            currentX, 
            lantern.y + lantern.height/2, 
            lantern.width/2, 
            lantern.height/2, 
            0, 0, Math.PI * 2
        );
        this.ctx.fill();
        
        // 绘制灯笼顶部
        this.ctx.fillStyle = '#8B4513';
        this.ctx.fillRect(
            currentX - lantern.width/2 * 0.8, 
            lantern.y - 10, 
            lantern.width * 0.8, 
            20
        );
        
        // 绘制灯笼底部
        this.ctx.fillStyle = '#8B4513';
        this.ctx.fillRect(
            currentX - lantern.width/2 * 0.6, 
            lantern.y + lantern.height - 5, 
            lantern.width * 0.6, 
            15
        );
        
        // 绘制装饰条纹
        this.ctx.strokeStyle = '#FFD700';
        this.ctx.lineWidth = 3;
        for (let i = 0; i < 3; i++) {
            const y = lantern.y + (i + 1) * lantern.height / 4;
            this.ctx.beginPath();
            this.ctx.moveTo(currentX - lantern.width/2 * 0.8, y);
            this.ctx.lineTo(currentX + lantern.width/2 * 0.8, y);
            this.ctx.stroke();
        }
        
        // 绘制中央文字区域
        this.ctx.fillStyle = '#FFD700';
        this.ctx.font = `${Math.floor(lantern.width/4)}px serif`;
        this.ctx.textAlign = 'center';
        this.ctx.fillText('福', currentX, lantern.y + lantern.height/2 + 5);
        
        // 绘制流苏
        this.ctx.strokeStyle = '#FFD700';
        this.ctx.lineWidth = 2;
        for (let i = 0; i < 5; i++) {
            const tassleX = currentX - lantern.width/4 + (i * lantern.width/8);
            this.ctx.beginPath();
            this.ctx.moveTo(tassleX, lantern.y + lantern.height + 10);
            this.ctx.lineTo(tassleX + Math.sin(lantern.swingAngle + i) * 3, lantern.y + lantern.height + 30);
            this.ctx.stroke();
        }
        
        // 绘制光晕效果
        const glowGradient = this.ctx.createRadialGradient(
            currentX, lantern.y + lantern.height/2, 0,
            currentX, lantern.y + lantern.height/2, lantern.width
        );
        glowGradient.addColorStop(0, 'rgba(255, 255, 0, 0.3)');
        glowGradient.addColorStop(1, 'rgba(255, 255, 0, 0)');
        
        this.ctx.fillStyle = glowGradient;
        this.ctx.beginPath();
        this.ctx.arc(currentX, lantern.y + lantern.height/2, lantern.width, 0, Math.PI * 2);
        this.ctx.fill();
        
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        // 更新和绘制灯笼
        this.lanterns.forEach(lantern => {
            lantern.swingAngle += lantern.swingSpeed;
            this.drawLantern(lantern);
        });
        
        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

// 导出效果类
window.LanternsEffect = LanternsEffect;