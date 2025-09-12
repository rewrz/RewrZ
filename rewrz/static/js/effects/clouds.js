/**
 * 云雾特效
 * 用于神秘、梦幻氛围等场合
 */

class CloudsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.clouds = [];
        this.animationId = null;
    }

    init() {
        this.createCanvas();
        this.generateClouds();
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
        
        this.clouds = [];
    }

    createCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'clouds-canvas';
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

    generateClouds() {
        const count = 8;
        for (let i = 0; i < count; i++) {
            this.clouds.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                vx: (Math.random() - 0.5) * 0.5,
                vy: (Math.random() - 0.5) * 0.3,
                size: Math.random() * 150 + 100,
                opacity: Math.random() * 0.3 + 0.1,
                particles: this.generateCloudParticles()
            });
        }
    }

    generateCloudParticles() {
        const particles = [];
        const count = 15 + Math.random() * 10;
        
        for (let i = 0; i < count; i++) {
            particles.push({
                x: (Math.random() - 0.5) * 200,
                y: (Math.random() - 0.5) * 100,
                size: Math.random() * 60 + 30,
                opacity: Math.random() * 0.8 + 0.2
            });
        }
        
        return particles;
    }

    drawCloud(cloud) {
        this.ctx.save();
        this.ctx.translate(cloud.x, cloud.y);
        this.ctx.globalAlpha = cloud.opacity;
        
        // 绘制云朵粒子
        cloud.particles.forEach(particle => {
            const gradient = this.ctx.createRadialGradient(
                particle.x, particle.y, 0,
                particle.x, particle.y, particle.size
            );
            gradient.addColorStop(0, `rgba(255, 255, 255, ${particle.opacity})`);
            gradient.addColorStop(0.5, `rgba(240, 240, 240, ${particle.opacity * 0.6})`);
            gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
            
            this.ctx.fillStyle = gradient;
            this.ctx.beginPath();
            this.ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
            this.ctx.fill();
        });
        
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        // 更新和绘制云朵
        this.clouds.forEach(cloud => {
            // 更新位置
            cloud.x += cloud.vx;
            cloud.y += cloud.vy;
            
            // 边界检查
            if (cloud.x < -cloud.size) {
                cloud.x = this.canvas.width + cloud.size;
            } else if (cloud.x > this.canvas.width + cloud.size) {
                cloud.x = -cloud.size;
            }
            
            if (cloud.y < -cloud.size) {
                cloud.y = this.canvas.height + cloud.size;
            } else if (cloud.y > this.canvas.height + cloud.size) {
                cloud.y = -cloud.size;
            }
            
            // 轻微的透明度变化
            cloud.opacity += (Math.random() - 0.5) * 0.01;
            cloud.opacity = Math.max(0.05, Math.min(0.4, cloud.opacity));
            
            this.drawCloud(cloud);
        });
        
        this.animationId = requestAnimationFrame(() => this.animate());
    }
}

// 导出效果类
window.CloudsEffect = CloudsEffect;