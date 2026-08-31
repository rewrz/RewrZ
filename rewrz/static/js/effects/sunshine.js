/**
 * 阳光特效
 * 用于温暖、希望、积极氛围等场合
 */

class SunshineEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.rays = [];
        this.particles = [];
        this.animationId = null;
    }

    init() {
        this.createCanvas();
        this.generateRays();
        this.generateParticles();
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
        
        this.rays = [];
        this.particles = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'sunshine-canvas';
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
            this.generateRays();
        };
    }

    generateRays() {
        this.rays = [];
        const rayCount = 12;
        const centerX = this.canvas.width * 0.8;
        const centerY = this.canvas.height * 0.2;
        
        for (let i = 0; i < rayCount; i++) {
            const angle = (i / rayCount) * Math.PI * 2;
            this.rays.push({
                centerX: centerX,
                centerY: centerY,
                angle: angle,
                length: Math.random() * 200 + 300,
                width: Math.random() * 30 + 20,
                opacity: Math.random() * 0.3 + 0.1,
                speed: Math.random() * 0.01 + 0.005
            });
        }
    }

    generateParticles() {
        const count = 50;
        for (let i = 0; i < count; i++) {
            this.particles.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                vx: (Math.random() - 0.5) * 1,
                vy: (Math.random() - 0.5) * 1,
                size: Math.random() * 3 + 1,
                opacity: Math.random() * 0.6 + 0.2,
                color: `hsl(${45 + Math.random() * 30}, 100%, ${70 + Math.random() * 20}%)`
            });
        }
    }

    drawRays() {
        this.rays.forEach(ray => {
            this.ctx.save();
            this.ctx.translate(ray.centerX, ray.centerY);
            this.ctx.rotate(ray.angle);
            
            // 创建阳光射线渐变
            const gradient = this.ctx.createLinearGradient(0, 0, ray.length, 0);
            gradient.addColorStop(0, `rgba(255, 255, 0, ${ray.opacity})`);
            gradient.addColorStop(0.3, `rgba(255, 215, 0, ${ray.opacity * 0.8})`);
            gradient.addColorStop(0.7, `rgba(255, 165, 0, ${ray.opacity * 0.4})`);
            gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
            
            this.ctx.fillStyle = gradient;
            this.ctx.beginPath();
            this.ctx.moveTo(0, -ray.width / 2);
            this.ctx.lineTo(ray.length, -ray.width / 4);
            this.ctx.lineTo(ray.length, ray.width / 4);
            this.ctx.lineTo(0, ray.width / 2);
            this.ctx.closePath();
            this.ctx.fill();
            
            this.ctx.restore();
            
            // 旋转射线
            ray.angle += ray.speed;
        });
    }

    drawSun() {
        const centerX = this.canvas.width * 0.8;
        const centerY = this.canvas.height * 0.2;
        const radius = 40;
        
        // 太阳光晕
        const glowGradient = this.ctx.createRadialGradient(
            centerX, centerY, 0,
            centerX, centerY, radius * 3
        );
        glowGradient.addColorStop(0, 'rgba(255, 255, 0, 0.3)');
        glowGradient.addColorStop(0.5, 'rgba(255, 215, 0, 0.2)');
        glowGradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
        
        this.ctx.fillStyle = glowGradient;
        this.ctx.beginPath();
        this.ctx.arc(centerX, centerY, radius * 3, 0, Math.PI * 2);
        this.ctx.fill();
        
        // 太阳主体
        const sunGradient = this.ctx.createRadialGradient(
            centerX, centerY, 0,
            centerX, centerY, radius
        );
        sunGradient.addColorStop(0, '#FFFF99');
        sunGradient.addColorStop(0.7, '#FFD700');
        sunGradient.addColorStop(1, '#FFA500');
        
        this.ctx.fillStyle = sunGradient;
        this.ctx.beginPath();
        this.ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        this.ctx.fill();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        // 绘制阳光射线
        this.drawRays();
        
        // 绘制太阳
        this.drawSun();
        
        // 更新和绘制光粒子
        this.particles.forEach(particle => {
            // 更新位置
            particle.x += particle.vx;
            particle.y += particle.vy;
            
            // 边界检查
            if (particle.x < 0 || particle.x > this.canvas.width) {
                particle.vx *= -1;
            }
            if (particle.y < 0 || particle.y > this.canvas.height) {
                particle.vy *= -1;
            }
            
            // 绘制光粒子
            this.ctx.save();
            this.ctx.globalAlpha = particle.opacity;
            this.ctx.fillStyle = particle.color;
            this.ctx.shadowBlur = 10;
            this.ctx.shadowColor = particle.color;
            this.ctx.beginPath();
            this.ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
            this.ctx.fill();
            this.ctx.restore();
        });
        
        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

// 导出效果类
window.SunshineEffect = SunshineEffect;