/**
 * 精美蜡烛摇曳特效
 * 用于纪念日、哀悼等肃穆场合
 */

class CandlesEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.candles = [];
        this.animationId = null;
        this.waxDrops = [];
        this.particles = [];
        this.time = 0;
    }

    init() {
        this.createCanvas();
        this.generateCandles();
        this.animate();
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
            background: transparent;
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
        this.waxDrops = [];
        
        // 只在左右两侧放置蜡烛，每侧2-3根
        const leftCandles = 2;
        const rightCandles = 2;
        
        // 左侧蜡烛
        for (let i = 0; i < leftCandles; i++) {
            this.candles.push({
                x: 30 + i * 40 + Math.random() * 20,
                y: this.canvas.height - 60 - Math.random() * 40,
                height: 60 + Math.random() * 40,
                width: 10 + Math.random() * 6,
                flameHeight: 15 + Math.random() * 10,
                flameWidth: 6 + Math.random() * 3,
                flameOffset: 0,
                flickerSpeed: 0.015 + Math.random() * 0.02,
                flickerIntensity: 0.8 + Math.random() * 0.4,
                baseFlameHeight: 15 + Math.random() * 10,
                waxColor: this.getRandomWaxColor(),
                lastWaxDrop: 0
            });
        }
        
        // 右侧蜡烛
        for (let i = 0; i < rightCandles; i++) {
            this.candles.push({
                x: this.canvas.width - 30 - i * 40 - Math.random() * 20,
                y: this.canvas.height - 60 - Math.random() * 40,
                height: 60 + Math.random() * 40,
                width: 10 + Math.random() * 6,
                flameHeight: 15 + Math.random() * 10,
                flameWidth: 6 + Math.random() * 3,
                flameOffset: 0,
                flickerSpeed: 0.015 + Math.random() * 0.02,
                flickerIntensity: 0.8 + Math.random() * 0.4,
                baseFlameHeight: 15 + Math.random() * 10,
                waxColor: this.getRandomWaxColor(),
                lastWaxDrop: 0
            });
        }
    }

    getRandomWaxColor() {
        const colors = [
            { r: 255, g: 248, b: 220 }, // 象牙白
            { r: 245, g: 222, b: 179 }, // 小麦色
            { r: 255, g: 239, b: 213 }, // 杏仁白
            { r: 250, g: 235, b: 215 }, // 古董白
            { r: 255, g: 228, b: 196 }  // 俾斯麦棕
        ];
        return colors[Math.floor(Math.random() * colors.length)];
    }

    createWaxDrop(candle) {
        if (Math.random() < 0.002 && Date.now() - candle.lastWaxDrop > 3000) {
            this.waxDrops.push({
                x: candle.x + (Math.random() - 0.5) * candle.width,
                y: candle.y - candle.height + 5,
                speed: 0.5 + Math.random() * 0.5,
                size: 2 + Math.random() * 3,
                color: candle.waxColor,
                life: 1.0
            });
            candle.lastWaxDrop = Date.now();
        }
    }

    createFlameParticles(candle) {
        if (Math.random() < 0.3) {
            const flameX = candle.x + candle.flameOffset;
            const flameY = candle.y - candle.height - candle.flameHeight;
            
            this.particles.push({
                x: flameX + (Math.random() - 0.5) * 6,
                y: flameY + Math.random() * 10,
                vx: (Math.random() - 0.5) * 0.5,
                vy: -0.5 - Math.random() * 1.5,
                size: 1 + Math.random() * 2,
                life: 1.0,
                decay: 0.02 + Math.random() * 0.03,
                color: Math.random() > 0.7 ? '#fff3a0' : '#ff6b35'
            });
        }
    }

    animate() {
        this.time += 0.016;
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        // 更新和绘制蜡烛
        this.candles.forEach(candle => {
            // 复杂的火焰摇曳动画
            const flicker1 = Math.sin(this.time * candle.flickerSpeed * 60) * candle.flickerIntensity;
            const flicker2 = Math.sin(this.time * candle.flickerSpeed * 80 + 1.5) * candle.flickerIntensity * 0.7;
            const flicker3 = Math.sin(this.time * candle.flickerSpeed * 100 + 3) * candle.flickerIntensity * 0.5;
            
            candle.flameOffset = (flicker1 + flicker2 + flicker3) * 2;
            candle.flameHeight = candle.baseFlameHeight + (flicker1 + flicker2) * 3;
            
            // 绘制蜡烛主体（带渐变）
            const candleGradient = this.ctx.createLinearGradient(
                candle.x - candle.width/2, candle.y - candle.height,
                candle.x + candle.width/2, candle.y - candle.height
            );
            candleGradient.addColorStop(0, `rgba(${candle.waxColor.r - 20}, ${candle.waxColor.g - 20}, ${candle.waxColor.b - 20}, 1)`);
            candleGradient.addColorStop(0.5, `rgba(${candle.waxColor.r}, ${candle.waxColor.g}, ${candle.waxColor.b}, 1)`);
            candleGradient.addColorStop(1, `rgba(${candle.waxColor.r - 15}, ${candle.waxColor.g - 15}, ${candle.waxColor.b - 15}, 1)`);
            
            this.ctx.fillStyle = candleGradient;
            this.ctx.fillRect(
                candle.x - candle.width/2, 
                candle.y - candle.height, 
                candle.width, 
                candle.height
            );
            
            // 绘制蜡烛顶部（稍暗）
            this.ctx.fillStyle = `rgba(${candle.waxColor.r - 30}, ${candle.waxColor.g - 30}, ${candle.waxColor.b - 30}, 1)`;
            this.ctx.fillRect(
                candle.x - candle.width/2, 
                candle.y - candle.height, 
                candle.width, 
                6
            );
            
            // 绘制烛芯
            this.ctx.fillStyle = '#2c1810';
            this.ctx.fillRect(
                candle.x - 0.5, 
                candle.y - candle.height - 3, 
                1, 
                8
            );
            
            // 绘制复杂的火焰
            const flameX = candle.x + candle.flameOffset;
            const flameY = candle.y - candle.height - candle.flameHeight;
            
            this.ctx.save();
            this.ctx.translate(flameX, flameY);
            
            // 火焰外层（深橙色）
            this.ctx.beginPath();
            this.ctx.ellipse(0, 0, candle.flameWidth, candle.flameHeight, 0, 0, Math.PI * 2);
            const outerGradient = this.ctx.createRadialGradient(0, 0, 0, 0, 0, candle.flameHeight);
            outerGradient.addColorStop(0, '#ff8c42');
            outerGradient.addColorStop(0.7, '#ff6b35');
            outerGradient.addColorStop(1, '#d63031');
            this.ctx.fillStyle = outerGradient;
            this.ctx.fill();
            
            // 火焰中层（橙黄色）
            this.ctx.beginPath();
            this.ctx.ellipse(0, 2, candle.flameWidth * 0.7, candle.flameHeight * 0.8, 0, 0, Math.PI * 2);
            const middleGradient = this.ctx.createRadialGradient(0, 2, 0, 0, 2, candle.flameHeight * 0.8);
            middleGradient.addColorStop(0, '#ffd93d');
            middleGradient.addColorStop(0.6, '#ff8c42');
            middleGradient.addColorStop(1, 'rgba(255, 107, 53, 0.8)');
            this.ctx.fillStyle = middleGradient;
            this.ctx.fill();
            
            // 火焰核心（亮黄色）
            this.ctx.beginPath();
            this.ctx.ellipse(0, 4, candle.flameWidth * 0.4, candle.flameHeight * 0.6, 0, 0, Math.PI * 2);
            const coreGradient = this.ctx.createRadialGradient(0, 4, 0, 0, 4, candle.flameHeight * 0.6);
            coreGradient.addColorStop(0, '#fff3a0');
            coreGradient.addColorStop(0.5, '#ffd93d');
            coreGradient.addColorStop(1, 'rgba(255, 217, 61, 0.6)');
            this.ctx.fillStyle = coreGradient;
            this.ctx.fill();
            
            this.ctx.restore();
            
            // 绘制大范围光晕
            const glowGradient = this.ctx.createRadialGradient(
                flameX, flameY, 0, 
                flameX, flameY, 120
            );
            glowGradient.addColorStop(0, 'rgba(255, 140, 66, 0.15)');
            glowGradient.addColorStop(0.3, 'rgba(255, 107, 53, 0.08)');
            glowGradient.addColorStop(1, 'rgba(255, 107, 53, 0)');
            
            this.ctx.fillStyle = glowGradient;
            this.ctx.beginPath();
            this.ctx.arc(flameX, flameY, 120, 0, Math.PI * 2);
            this.ctx.fill();
            
            // 创建蜡滴和火焰粒子
            this.createWaxDrop(candle);
            this.createFlameParticles(candle);
        });
        
        // 更新和绘制蜡滴
        this.waxDrops = this.waxDrops.filter(drop => {
            drop.y += drop.speed;
            drop.life -= 0.005;
            
            if (drop.life > 0 && drop.y < this.canvas.height) {
                this.ctx.fillStyle = `rgba(${drop.color.r}, ${drop.color.g}, ${drop.color.b}, ${drop.life})`;
                this.ctx.beginPath();
                this.ctx.arc(drop.x, drop.y, drop.size, 0, Math.PI * 2);
                this.ctx.fill();
                return true;
            }
            return false;
        });
        
        // 更新和绘制火焰粒子
        this.particles = this.particles.filter(particle => {
            particle.x += particle.vx;
            particle.y += particle.vy;
            particle.life -= particle.decay;
            particle.vy -= 0.01; // 重力效果
            
            if (particle.life > 0) {
                this.ctx.fillStyle = particle.color.replace('1)', `${particle.life})`);
                this.ctx.beginPath();
                this.ctx.arc(particle.x, particle.y, particle.size * particle.life, 0, Math.PI * 2);
                this.ctx.fill();
                return true;
            }
            return false;
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
        this.waxDrops = [];
        this.particles = [];
    }
}

// 导出效果类
window.CandlesEffect = CandlesEffect;