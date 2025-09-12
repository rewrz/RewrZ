/**
 * 蜡烛摇曳特效
 * 用于纪念日、哀悼等肃穆场合
 */

class CandlesEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.candles = [];
        this.animationId = null;
        this.flames = [];
    }

    init() {
        this.createCanvas();
        this.generateCandles();
        this.animate();
        this.addAmbientLight();
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'candles-canvas';
        this.canvas.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 9999;
            background: rgba(0, 0, 0, 0.1);
        `;
        
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        
        document.body.appendChild(this.canvas);
        
        // 监听窗口大小变化
        window.addEventListener('resize', () => {
            this.canvas.width = window.innerWidth;
            this.canvas.height = window.innerHeight;
            this.generateCandles();
        });
    }

    generateCandles() {
        this.candles = [];
        const count = Math.floor(this.canvas.width / 200) + 1;
        
        for (let i = 0; i < count; i++) {
            this.candles.push({
                x: (i + 0.5) * (this.canvas.width / count),
                y: this.canvas.height - 100,
                height: 60 + Math.random() * 40,
                width: 8 + Math.random() * 4,
                flameHeight: 15 + Math.random() * 10,
                flameOffset: 0,
                flickerSpeed: 0.02 + Math.random() * 0.03
            });
        }
    }

    addAmbientLight() {
        // 添加暖色调滤镜
        document.body.style.filter = 'sepia(0.3) brightness(0.8) contrast(1.1)';
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        // 绘制蜡烛和火焰
        this.candles.forEach(candle => {
            // 更新火焰摇曳
            candle.flameOffset = Math.sin(Date.now() * candle.flickerSpeed) * 3;
            
            // 绘制蜡烛主体
            this.ctx.fillStyle = '#f4f1de';
            this.ctx.fillRect(
                candle.x - candle.width/2, 
                candle.y - candle.height, 
                candle.width, 
                candle.height
            );
            
            // 绘制蜡烛顶部
            this.ctx.fillStyle = '#e9c46a';
            this.ctx.fillRect(
                candle.x - candle.width/2, 
                candle.y - candle.height, 
                candle.width, 
                5
            );
            
            // 绘制火焰
            const flameX = candle.x + candle.flameOffset;
            const flameY = candle.y - candle.height - candle.flameHeight;
            
            // 火焰外层（橙色）
            this.ctx.beginPath();
            this.ctx.ellipse(flameX, flameY, 6, candle.flameHeight, 0, 0, Math.PI * 2);
            this.ctx.fillStyle = '#ff6b35';
            this.ctx.fill();
            
            // 火焰内层（黄色）
            this.ctx.beginPath();
            this.ctx.ellipse(flameX, flameY + 3, 3, candle.flameHeight * 0.6, 0, 0, Math.PI * 2);
            this.ctx.fillStyle = '#f7931e';
            this.ctx.fill();
            
            // 火焰核心（白色）
            this.ctx.beginPath();
            this.ctx.ellipse(flameX, flameY + 5, 1, candle.flameHeight * 0.3, 0, 0, Math.PI * 2);
            this.ctx.fillStyle = '#fff3a0';
            this.ctx.fill();
            
            // 绘制光晕
            const gradient = this.ctx.createRadialGradient(
                flameX, flameY, 0, 
                flameX, flameY, 50
            );
            gradient.addColorStop(0, 'rgba(255, 107, 53, 0.3)');
            gradient.addColorStop(1, 'rgba(255, 107, 53, 0)');
            
            this.ctx.fillStyle = gradient;
            this.ctx.beginPath();
            this.ctx.arc(flameX, flameY, 50, 0, Math.PI * 2);
            this.ctx.fill();
        });
        
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
        
        // 移除环境光效果
        document.body.style.filter = '';
        
        this.candles = [];
    }
}

// 导出效果类
window.CandlesEffect = CandlesEffect;