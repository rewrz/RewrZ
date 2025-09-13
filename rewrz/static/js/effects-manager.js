/**
 * 特效管理器
 * 管理纪念日氛围特效，包括烟花、爆竹、樱花飘落、大红灯笼等
 */

class EffectsManager {
    constructor() {
        this.activeEffects = new Map();
        this.currentAnniversary = null;
        this.init();
    }

    async init() {
        await this.loadAnniversarySettings();
        this.setupEventListeners();
        this.startEffectMonitoring();
    }

    // 加载纪念日设置
    async loadAnniversarySettings() {
        try {
            const response = await fetch('/api/anniversary-mode/current');
            if (response.ok) {
                const data = await response.json();
                this.currentAnniversary = data;
                this.applyEffects(data);
            }
        } catch (error) {
            console.error('加载纪念日设置失败:', error);
        }
    }

    // 应用特效
    applyEffects(settings) {
        // 清除所有现有特效
        this.clearAllEffects();

        if (!settings || !settings.enabled) return;

        // 应用灰度效果（追悼模式）
        if (settings.grayscale) {
            this.applyGrayscaleEffect();
        }

        // 应用选中的特效
        if (settings.effects && settings.effects.length > 0) {
            settings.effects.forEach(effect => {
                switch (effect) {
                    case 'fireworks':
                        this.startFireworks();
                        break;
                    case 'firecrackers':
                        this.startFirecrackers();
                        break;
                    case 'sakura':
                        this.startSakuraFall();
                        break;
                    case 'lanterns':
                        this.startLanterns();
                        break;
                    case 'snow':
                        this.startSnowfall();
                        break;
                    case 'confetti':
                        this.startConfetti();
                        break;
                }
            });
        }
    }

    // 设置事件监听器
    setupEventListeners() {
        // 监听主题变化
        document.addEventListener('themeChanged', (event) => {
            this.onThemeChange(event.detail);
        });

        // 监听纪念日设置变化
        document.addEventListener('anniversarySettingsChanged', (event) => {
            this.applyEffects(event.detail);
        });
    }

    // 开始特效监控
    startEffectMonitoring() {
        // 每30秒检查一次纪念日设置更新
        setInterval(() => {
            this.loadAnniversarySettings();
        }, 30000);
    }

    // 清除所有特效
    clearAllEffects() {
        this.activeEffects.forEach((canvas, effectName) => {
            if (canvas && canvas.parentNode) {
                canvas.parentNode.removeChild(canvas);
            }
            this.activeEffects.delete(effectName);
        });

        // 移除灰度效果
        document.body.classList.remove('grayscale-effect');
    }

    // 应用灰度效果
    applyGrayscaleEffect() {
        document.body.classList.add('grayscale-effect');
    }

    // 获取激活的特效列表
    getActiveEffects() {
        return Array.from(this.activeEffects.keys());
    }

    // 停止特效
    stopEffect() {
        this.clearAllEffects();
    }

    // 启动特效
    startEffect(effects) {
        if (!Array.isArray(effects)) return;
        
        effects.forEach(effect => {
            switch (effect) {
                case 'fireworks':
                    this.startFireworks();
                    break;
                case 'firecrackers':
                    this.startFirecrackers();
                    break;
                case 'sakura':
                    this.startSakuraFall();
                    break;
                case 'lanterns':
                    this.startLanterns();
                    break;
                case 'snow':
                    this.startSnowfall();
                    break;
                case 'confetti':
                    this.startConfetti();
                    break;
            }
        });
    }

    // 移除滤镜
    removeFilters() {
        document.body.classList.remove('grayscale-effect');
    }

    // 应用滤镜
    applyFilter(filterType) {
        switch (filterType) {
            case 'grayscale':
                this.applyGrayscaleEffect();
                break;
            // 可以添加更多滤镜类型
        }
    }

    // 烟花特效
    startFireworks() {
        if (this.activeEffects.has('fireworks')) return;

        const canvas = this.createCanvas('fireworks');
        const ctx = canvas.getContext('2d');

        const fireworks = [];
        const particles = [];

        class Firework {
            constructor() {
                this.x = Math.random() * canvas.width;
                this.y = canvas.height;
                this.speed = Math.random() * 3 + 2;
                this.angle = Math.random() * Math.PI - Math.PI / 2 - Math.PI / 4;
                this.shrapnel = 30 + Math.random() * 50;
                this.hue = Math.random() * 360;
                this.brightness = 50 + Math.random() * 50;
            }

            update() {
                this.x += Math.cos(this.angle) * this.speed;
                this.y -= Math.sin(this.angle) * this.speed;
                this.speed *= 0.98;

                if (this.speed < 0.5) {
                    this.explode();
                    return false;
                }
                return true;
            }

            explode() {
                for (let i = 0; i < this.shrapnel; i++) {
                    particles.push(new Particle(this.x, this.y, this.hue));
                }
            }

            draw() {
                ctx.beginPath();
                ctx.arc(this.x, this.y, 2, 0, Math.PI * 2);
                ctx.fillStyle = `hsl(${this.hue}, 100%, ${this.brightness}%)`;
                ctx.fill();
            }
        }

        class Particle {
            constructor(x, y, hue) {
                this.x = x;
                this.y = y;
                this.speed = Math.random() * 5 + 2;
                this.angle = Math.random() * Math.PI * 2;
                this.friction = 0.95;
                this.gravity = 0.2;
                this.hue = hue;
                this.brightness = 50 + Math.random() * 50;
                this.alpha = 1;
                this.decay = Math.random() * 0.03 + 0.02;
            }

            update() {
                this.speed *= this.friction;
                this.x += Math.cos(this.angle) * this.speed;
                this.y += Math.sin(this.angle) * this.speed + this.gravity;
                this.alpha -= this.decay;
                return this.alpha > 0;
            }

            draw() {
                ctx.beginPath();
                ctx.arc(this.x, this.y, 1.5, 0, Math.PI * 2);
                ctx.fillStyle = `hsla(${this.hue}, 100%, ${this.brightness}%, ${this.alpha})`;
                ctx.fill();
            }
        }

        function animate() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // 随机生成新烟花
            if (Math.random() < 0.03) {
                fireworks.push(new Firework());
            }

            // 更新烟花
            for (let i = fireworks.length - 1; i >= 0; i--) {
                if (!fireworks[i].update()) {
                    fireworks.splice(i, 1);
                } else {
                    fireworks[i].draw();
                }
            }

            // 更新粒子
            for (let i = particles.length - 1; i >= 0; i--) {
                if (!particles[i].update()) {
                    particles.splice(i, 1);
                } else {
                    particles[i].draw();
                }
            }

            requestAnimationFrame(animate);
        }

        animate();
        this.activeEffects.set('fireworks', canvas);
    }

    // 爆竹特效
    startFirecrackers() {
        if (this.activeEffects.has('firecrackers')) return;

        const canvas = this.createCanvas('firecrackers');
        const ctx = canvas.getContext('2d');

        const firecrackers = [];
        const explosions = [];

        class Firecracker {
            constructor() {
                this.x = Math.random() * canvas.width;
                this.y = canvas.height;
                this.speed = Math.random() * 4 + 3;
                this.angle = Math.random() * Math.PI - Math.PI / 2 - Math.PI / 4;
                this.hue = 0; // 红色系
                this.timer = 60 + Math.random() * 60;
            }

            update() {
                this.x += Math.cos(this.angle) * this.speed;
                this.y -= Math.sin(this.angle) * this.speed;
                this.timer--;

                if (this.timer <= 0) {
                    this.explode();
                    return false;
                }
                return true;
            }

            explode() {
                explosions.push(new Explosion(this.x, this.y));
                // 播放爆炸音效
                this.playExplosionSound();
            }

            playExplosionSound() {
                const audio = new Audio('data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAAAAA');
                audio.volume = 0.3;
                audio.play().catch(() => {});
            }

            draw() {
                ctx.beginPath();
                ctx.arc(this.x, this.y, 3, 0, Math.PI * 2);
                ctx.fillStyle = `hsl(0, 100%, 50%)`;
                ctx.fill();
            }
        }

        class Explosion {
            constructor(x, y) {
                this.x = x;
                this.y = y;
                this.radius = 5;
                this.maxRadius = 30 + Math.random() * 20;
                this.growthRate = 2;
                this.alpha = 1;
            }

            update() {
                this.radius += this.growthRate;
                this.alpha -= 0.03;
                return this.alpha > 0 && this.radius < this.maxRadius;
            }

            draw() {
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
                ctx.fillStyle = `hsla(0, 100%, 60%, ${this.alpha})`;
                ctx.fill();

                // 爆炸光芒
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.radius * 1.5, 0, Math.PI * 2);
                ctx.strokeStyle = `hsla(60, 100%, 80%, ${this.alpha * 0.5})`;
                ctx.lineWidth = 2;
                ctx.stroke();
            }
        }

        function animate() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // 随机生成新爆竹
            if (Math.random() < 0.02) {
                firecrackers.push(new Firecracker());
            }

            // 更新爆竹
            for (let i = firecrackers.length - 1; i >= 0; i--) {
                if (!firecrackers[i].update()) {
                    firecrackers.splice(i, 1);
                } else {
                    firecrackers[i].draw();
                }
            }

            // 更新爆炸
            for (let i = explosions.length - 1; i >= 0; i--) {
                if (!explosions[i].update()) {
                    explosions.splice(i, 1);
                } else {
                    explosions[i].draw();
                }
            }

            requestAnimationFrame(animate);
        }

        animate();
        this.activeEffects.set('firecrackers', canvas);
    }

    // 樱花飘落特效
    startSakuraFall() {
        if (this.activeEffects.has('sakura')) return;

        const canvas = this.createCanvas('sakura');
        const ctx = canvas.getContext('2d');

        const petals = [];
        const petalCount = 50;

        class Petal {
            constructor() {
                this.reset();
            }

            reset() {
                this.x = Math.random() * canvas.width;
                this.y = Math.random() * -100;
                this.size = Math.random() * 5 + 2;
                this.speed = Math.random() * 2 + 1;
                this.angle = Math.random() * Math.PI * 2;
                this.spin = Math.random() * 0.1 - 0.05;
                this.hue = Math.random() * 20 + 330; // 粉色系
                this.alpha = Math.random() * 0.5 + 0.3;
            }

            update() {
                this.y += this.speed;
                this.x += Math.sin(this.angle) * 0.5;
                this.angle += this.spin;

                if (this.y > canvas.height) {
                    this.reset();
                }
            }

            draw() {
                ctx.save();
                ctx.translate(this.x, this.y);
                ctx.rotate(this.angle);

                ctx.beginPath();
                ctx.ellipse(0, 0, this.size, this.size * 0.6, 0, 0, Math.PI * 2);
                ctx.fillStyle = `hsla(${this.hue}, 70%, 70%, ${this.alpha})`;
                ctx.fill();

                // 花瓣纹理
                ctx.beginPath();
                ctx.ellipse(0, 0, this.size * 0.6, this.size * 0.3, 0, 0, Math.PI * 2);
                ctx.fillStyle = `hsla(${this.hue}, 70%, 85%, ${this.alpha * 0.8})`;
                ctx.fill();

                ctx.restore();
            }
        }

        // 初始化花瓣
        for (let i = 0; i < petalCount; i++) {
            petals.push(new Petal());
            petals[i].y = Math.random() * canvas.height;
        }

        function animate() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            petals.forEach(petal => {
                petal.update();
                petal.draw();
            });

            requestAnimationFrame(animate);
        }

        animate();
        this.activeEffects.set('sakura', canvas);
    }

    // 大红灯笼特效
    startLanterns() {
        if (this.activeEffects.has('lanterns')) return;

        const canvas = this.createCanvas('lanterns');
        const ctx = canvas.getContext('2d');

        const lanterns = [];
        const lanternCount = 8;

        class Lantern {
            constructor() {
                this.x = Math.random() * canvas.width;
                this.y = canvas.height + 50;
                this.speed = Math.random() * 0.8 + 0.5;
                this.swing = Math.random() * 0.02 - 0.01;
                this.angle = 0;
                this.size = Math.random() * 20 + 30;
                this.hue = Math.random() * 10; // 红色系
                this.brightness = 60 + Math.random() * 20;
            }

            update() {
                this.y -= this.speed;
                this.angle += this.swing;
                this.x += Math.sin(this.angle) * 0.5;

                if (this.y < -100) {
                    this.reset();
                }
            }

            reset() {
                this.x = Math.random() * canvas.width;
                this.y = canvas.height + 50;
                this.speed = Math.random() * 0.8 + 0.5;
            }

            draw() {
                ctx.save();
                ctx.translate(this.x, this.y);
                ctx.rotate(this.angle);

                // 灯笼主体
                ctx.beginPath();
                ctx.ellipse(0, 0, this.size, this.size * 1.2, 0, 0, Math.PI * 2);
                ctx.fillStyle = `hsl(${this.hue}, 100%, ${this.brightness}%)`;
                ctx.fill();

                // 灯笼边框
                ctx.strokeStyle = `hsl(${this.hue}, 100%, ${this.brightness - 20}%)`;
                ctx.lineWidth = 2;
                ctx.stroke();

                // 灯笼纹理
                ctx.beginPath();
                for (let i = -3; i <= 3; i++) {
                    ctx.moveTo(-this.size * 0.8, i * 5);
                    ctx.lineTo(this.size * 0.8, i * 5);
                }
                ctx.strokeStyle = `hsla(${this.hue}, 100%, ${this.brightness - 10}%, 0.6)`;
                ctx.lineWidth = 1;
                ctx.stroke();

                // 灯笼穗
                ctx.beginPath();
                ctx.moveTo(0, this.size * 1.2);
                ctx.lineTo(0, this.size * 1.8);
                ctx.strokeStyle = `hsl(${this.hue}, 100%, ${this.brightness - 10}%)`;
                ctx.lineWidth = 2;
                ctx.stroke();

                ctx.restore();
            }
        }

        // 初始化灯笼
        for (let i = 0; i < lanternCount; i++) {
            lanterns.push(new Lantern());
            lanterns[i].y = Math.random() * canvas.height;
        }

        function animate() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            lanterns.forEach(lantern => {
                lantern.update();
                lantern.draw();
            });

            requestAnimationFrame(animate);
        }

        animate();
        this.activeEffects.set('lanterns', canvas);
    }

    // 雪花特效
    startSnowfall() {
        if (this.activeEffects.has('snow')) return;

        const canvas = this.createCanvas('snow');
        const ctx = canvas.getContext('2d');

        const snowflakes = [];
        const flakeCount = 100;

        class Snowflake {
            constructor() {
                this.reset();
            }

            reset() {
                this.x = Math.random() * canvas.width;
                this.y = Math.random() * -100;
                this.size = Math.random() * 3 + 1;
                this.speed = Math.random() * 2 + 1;
                this.wind = Math.random() * 0.5 - 0.25;
                this.alpha = Math.random() * 0.8 + 0.2;
            }

            update() {
                this.y += this.speed;
                this.x += this.wind;

                if (this.y > canvas.height) {
                    this.reset();
                }
            }

            draw() {
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(255, 255, 255, ${this.alpha})`;
                ctx.fill();
            }
        }

        // 初始化雪花
        for (let i = 0; i < flakeCount; i++) {
            snowflakes.push(new Snowflake());
            snowflakes[i].y = Math.random() * canvas.height;
        }

        function animate() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            snowflakes.forEach(flake => {
                flake.update();
                flake.draw();
            });

            requestAnimationFrame(animate);
        }

        animate();
        this.activeEffects.set('snow', canvas);
    }

    // 彩花特效
    startConfetti() {
        if (this.activeEffects.has('confetti')) return;

        const canvas = this.createCanvas('confetti');
        const ctx = canvas.getContext('2d');

        const confettiPieces = [];
        const pieceCount = 200;

        class Confetti {
            constructor() {
                this.reset();
            }

            reset() {
                this.x = Math.random() * canvas.width;
                this.y = Math.random() * -100;
                this.size = Math.random() * 8 + 4;
                this.speed = Math.random() * 5 + 2;
                this.angle = Math.random() * Math.PI * 2;
                this.spin = Math.random() * 0.2 - 0.1;
                this.hue = Math.random() * 360;
                this.alpha = Math.random() * 0.8 + 0.2;
                this.shape = Math.random() > 0.5 ? 'circle' : 'rect';
            }

            update() {
                this.y += this.speed;
                this.x += Math.cos(this.angle) * 1;
                this.angle += this.spin;
                this.speed *= 0.99;

                if (this.y > canvas.height) {
                    this.reset();
                }
            }

            draw() {
                ctx.save();
                ctx.translate(this.x, this.y);
                ctx.rotate(this.angle);

                if (this.shape === 'circle') {
                    ctx.beginPath();
                    ctx.arc(0, 0, this.size / 2, 0, Math.PI * 2);
                    ctx.fillStyle = `hsla(${this.hue}, 100%, 60%, ${this.alpha})`;
                    ctx.fill();
                } else {
                    ctx.fillStyle = `hsla(${this.hue}, 100%, 60%, ${this.alpha})`;
                    ctx.fillRect(-this.size / 2, -this.size / 2, this.size, this.size);
                }

                ctx.restore();
            }
        }

        // 初始化彩花
        for (let i = 0; i < pieceCount; i++) {
            confettiPieces.push(new Confetti());
            confettiPieces[i].y = Math.random() * canvas.height;
        }

        function animate() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            confettiPieces.forEach(piece => {
                piece.update();
                piece.draw();
            });

            requestAnimationFrame(animate);
        }

        animate();
        this.activeEffects.set('confetti', canvas);
    }

    // 创建画布
    createCanvas(effectName) {
        // 移除现有的同名画布
        const existing = document.getElementById(`effect-${effectName}`);
        if (existing) {
            existing.remove();
        }

        const canvas = document.createElement('canvas');
        canvas.id = `effect-${effectName}`;
        canvas.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 9998;
        `;

        // 设置画布尺寸
        const resizeCanvas = () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        };

        resizeCanvas();
        window.addEventListener('resize', resizeCanvas);

        document.body.appendChild(canvas);
        return canvas;
    }

    // 主题变化处理
    onThemeChange(themeConfig) {
        // 主题变化时重新应用特效
        if (this.currentAnniversary) {
            this.applyEffects(this.currentAnniversary);
        }
    }
}

// 初始化特效管理器
document.addEventListener('DOMContentLoaded', () => {
    window.effectsManager = new EffectsManager();
});

// 导出供其他模块使用
export default EffectsManager;