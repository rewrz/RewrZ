/**
 * 特效管理器
 * 统一管理所有视觉特效的启动、停止和切换
 */

class EffectManager {
    constructor() {
        this.activeEffects = new Map();
        this.loadingEffects = new Map();
        // 用户偏好减少动态效果时，跳过画布类特效（灰度滤镜除外，它是内容呈现而非动画）
        this.prefersReducedMotion = window.matchMedia
            && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        this.resizeHandler = () => this.handleWindowResize();
        this.effectClasses = {
            'fireworks': 'FireworksEffect',
            'sakura': 'SakuraEffect',
            'snow': 'SnowEffect',
            'lanterns': 'LanternsEffect',
            'firecrackers': 'FirecrackersEffect',
            'confetti': 'ConfettiEffect',
            'golden_dust': 'GoldenDustEffect',
            'floating_lights': 'FloatingLightsEffect',
            'hearts': 'HeartsEffect',
            'balloons': 'BalloonsEffect',
            'bubbles': 'BubblesEffect',
            'moonlight': 'MoonlightEffect',
            'stars': 'StarsEffect',
            'embers': 'EmbersEffect',
            'rice_grains': 'RiceGrainsEffect',
            'countdown_banner': 'CountdownBannerEffect',
            'red_packets': 'RedPacketsEffect',
            'ingots': 'IngotsEffect',
            'tangyuan': 'TangyuanEffect',
            'dragon_shape': 'DragonShapeEffect',
            'willow_catkins': 'WillowCatkinsEffect',
            'gear_icons': 'GearIconsEffect',
            'tie_icons': 'TieIconsEffect',
            'dragon_boats': 'DragonBoatsEffect',
            'zongzi': 'ZongziEffect',
            'star_bridge': 'StarBridgeEffect',
            'feathers': 'FeathersEffect',
            'paper_charms': 'PaperCharmsEffect',
            'lotus_lights': 'LotusLightsEffect',
            'chalk_writing': 'ChalkWritingEffect',
            'osmanthus': 'OsmanthusEffect',
            'dumplings': 'DumplingsEffect',
            'tree_lights': 'TreeLightsEffect',
            'candles': 'CandlesEffect',
            'petals': 'PetalsEffect',
            'leaves': 'LeavesEffect',
            'rain': 'RainEffect',
            'thunder': 'ThunderEffect',
            'clouds': 'CloudsEffect',
            'sunshine': 'SunshineEffect'
        };
        this.effectScriptFiles = {
            'golden_dust': 'golden-dust.js',
            'floating_lights': 'floating-lights.js',
            'rice_grains': 'rice-grains.js',
            'countdown_banner': 'countdown-banner.js',
            'red_packets': 'red-packets.js',
            'dragon_shape': 'dragon-shape.js',
            'willow_catkins': 'willow-catkins.js',
            'gear_icons': 'gear-icons.js',
            'tie_icons': 'tie-icons.js',
            'dragon_boats': 'dragon-boats.js',
            'star_bridge': 'star-bridge.js',
            'paper_charms': 'paper-charms.js',
            'lotus_lights': 'lotus-lights.js',
            'chalk_writing': 'chalk-writing.js',
            'tree_lights': 'tree-lights.js',
        };
        this.loadedScripts = new Set();
    }

    async loadEffect(effectName) {
        if (this.loadedScripts.has(effectName)) {
            return true;
        }
        if (this.loadingEffects.has(effectName)) {
            return this.loadingEffects.get(effectName);
        }

        // 检查是否已经存在相同的脚本标签
        const scriptFileName = this.effectScriptFiles[effectName] || `${effectName}.js`;
        const existingScript = document.querySelector(`script[src*="${scriptFileName}"]`);
        if (existingScript) {
            this.loadedScripts.add(effectName);
            return true;
        }

        try {
            const script = document.createElement('script');
            script.src = `/static/js/effects/${scriptFileName}`;
            script.setAttribute('data-effect', effectName);
            const loader = new Promise((resolve) => {
                script.onload = () => {
                    this.loadedScripts.add(effectName);
                    this.loadingEffects.delete(effectName);
                    resolve(true);
                };
                script.onerror = () => {
                    this.loadingEffects.delete(effectName);
                    resolve(false);
                };
            });
            this.loadingEffects.set(effectName, loader);
            document.head.appendChild(script);
            return loader;
        } catch (error) {
            return false;
        }
    }

    async startEffect(effectName) {
        // 如果特效已经在运行，先停止它
        if (this.activeEffects.has(effectName)) {
            this.stopEffect(effectName);
        }

        // 特殊处理灰度效果
        if (effectName === 'grayscale') {
            this.enableGrayscale();
            return true;
        }

        if (this.prefersReducedMotion) {
            return false;
        }

        // 加载特效脚本
        const loaded = await this.loadEffect(effectName);
        if (!loaded) {
            return false;
        }

        // 获取特效类，添加等待机制
        const effectClassName = this.effectClasses[effectName];
        if (!effectClassName) {
            return false;
        }

        // 等待类加载完成，最多等待3秒
        let attempts = 0;
        while (!window[effectClassName] && attempts < 30) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }

        if (!window[effectClassName]) {
            return false;
        }

        try {
            // 创建并启动特效实例
            const effectInstance = new window[effectClassName]();
            effectInstance.init();

            // 保存到活动特效列表
            this.activeEffects.set(effectName, effectInstance);
            this.syncResizeListener();

            return true;
        } catch (error) {
            return false;
        }
    }

    /**
     * 统一管理窗口 resize 监听：
     * 有画布特效时注册，全部停止后移除，避免监听器随特效重启而累积
     */
    syncResizeListener() {
        if (this.activeEffects.size > 0) {
            window.addEventListener('resize', this.resizeHandler);
        } else {
            window.removeEventListener('resize', this.resizeHandler);
        }
    }

    handleWindowResize() {
        this.activeEffects.forEach((effect) => {
            const hasOwnHandler = typeof effect.handleWindowResize === 'function';
            // 特效自带处理器时由其自行调整画布，避免重复设置导致画布被清空两次
            if (!hasOwnHandler && effect.canvas) {
                effect.canvas.width = window.innerWidth;
                effect.canvas.height = window.innerHeight;
            }
            if (hasOwnHandler) {
                try {
                    effect.handleWindowResize();
                } catch (_) {
                    // 单个特效的 resize 失败不影响其他特效
                }
            }
        });
    }

    stopEffect(effectName) {
        // 特殊处理灰度效果
        if (effectName === 'grayscale') {
            this.disableGrayscale();
            return true;
        }

        const effect = this.activeEffects.get(effectName);
        if (effect) {
            try {
                effect.stop();
                this.activeEffects.delete(effectName);
                this.syncResizeListener();
                return true;
            } catch (error) {
                return false;
            }
        }
        return false;
    }

    stopAll() {
        // 停止灰度效果
        this.disableGrayscale();
        
        // 停止所有其他特效
        const effectNames = Array.from(this.activeEffects.keys());
        effectNames.forEach(name => this.stopEffect(name));
    }

    isActive(effectName) {
        if (effectName === 'grayscale') {
            return document.documentElement.style.filter.includes('grayscale');
        }
        return this.activeEffects.has(effectName);
    }

    getActiveEffects() {
        const effects = Array.from(this.activeEffects.keys());
        if (document.documentElement.style.filter.includes('grayscale')) {
            effects.push('grayscale');
        }
        return effects;
    }

    // 特殊效果：灰度滤镜（用于纪念日）
    enableGrayscale() {
        document.documentElement.style.filter = 'grayscale(100%)';
        if (document.body) {
            document.body.classList.add('grayscale-effect');
        }
    }

    disableGrayscale() {
        document.documentElement.style.filter = '';
        if (document.body) {
            document.body.classList.remove('grayscale-effect');
        }
    }

    /**
     * 根据纪念日类型启动对应的特效组合
     * @param {string} anniversaryType - 纪念日类型
     * @param {Array} effects - 特效列表
     */
    async startAnniversaryEffects(anniversaryType, effects = []) {
        // 先停止所有现有特效
        this.stopAll();

        // 预定义的特效组合
        const effectCombinations = {
            'festive': ['fireworks', 'confetti', 'lanterns', 'golden_dust', 'stars'], // 喜庆节日
            'mourn': ['grayscale', 'candles', 'floating_lights', 'paper_charms'], // 纪念悼念
            'spring_festival': ['lanterns', 'firecrackers', 'golden_dust', 'embers', 'red_packets'], // 春节
            'new_year': ['fireworks', 'confetti', 'golden_dust', 'stars', 'countdown_banner'], // 新年
            'cherry_blossom': ['sakura', 'petals'], // 樱花节
            'winter': ['snow', 'clouds', 'moonlight'], // 冬季
            'autumn': ['leaves'], // 秋季
            'celebration': ['fireworks', 'confetti', 'golden_dust', 'balloons'], // 庆祝
            'memorial': ['grayscale', 'candles', 'floating_lights'], // 追悼
            'valentine': ['hearts', 'petals', 'sakura', 'stars', 'feathers'], // 情人节
            'christmas': ['snow', 'fireworks', 'floating_lights', 'stars', 'tree_lights'], // 圣诞节
            'national_day': ['fireworks', 'lanterns', 'golden_dust', 'stars'], // 国庆节
            'rainy_day': ['rain', 'clouds'], // 雨天
            'stormy': ['rain', 'thunder', 'clouds'], // 暴风雨
            'sunny': ['sunshine'], // 晴天
            'cloudy': ['clouds'], // 多云
            'spring': ['sakura', 'petals', 'sunshine'], // 春天
            'summer': ['sunshine', 'bubbles', 'balloons'], // 夏天
            'thunderstorm': ['thunder', 'rain'] // 雷雨
        };

        // 使用传入的特效列表，如果没有则使用预定义组合
        const effectsToStart = [...new Set(effects.length > 0 ? effects : (effectCombinations[anniversaryType] || []))];

        const prioritizedEffects = effectsToStart.sort((left, right) => {
            if (left === 'grayscale') {
                return -1;
            }
            if (right === 'grayscale') {
                return 1;
            }
            return 0;
        });

        // 启动特效
        for (const effectName of prioritizedEffects) {
            await this.startEffect(effectName);
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    }

    /**
     * 获取所有可用的特效名称
     * @returns {Array}
     */
    getAvailableEffects() {
        return Object.keys(this.effectClasses).concat(['grayscale']);
    }

}

// 创建全局实例
window.effectManager = new EffectManager();

// 导出管理器类
window.EffectManager = EffectManager;
