/**
 * 特效管理器
 * 统一管理所有视觉特效的启动、停止和切换
 */

class EffectManager {
    constructor() {
        this.activeEffects = new Map();
        this.effectClasses = {
            'fireworks': 'FireworksEffect',
            'sakura': 'SakuraEffect', 
            'snow': 'SnowEffect',
            'lanterns': 'LanternsEffect',
            'firecrackers': 'FirecrackersEffect',
            'confetti': 'ConfettiEffect',
            'candles': 'CandlesEffect',
            'petals': 'PetalsEffect',
            'leaves': 'LeavesEffect',
            'rain': 'RainEffect',
            'thunder': 'ThunderEffect',
            'clouds': 'CloudsEffect',
            'sunshine': 'SunshineEffect'
        };
        this.loadedScripts = new Set();
    }

    async loadEffect(effectName) {
        if (this.loadedScripts.has(effectName)) {
            return true;
        }

        try {
            const script = document.createElement('script');
            script.src = `/static/js/effects/${effectName}.js?v=${Date.now()}`;
            
            document.head.appendChild(script);
            
            // 等待脚本加载
            return new Promise((resolve) => {
                script.onload = () => {
                    this.loadedScripts.add(effectName);
                    console.log(`特效 ${effectName} 加载成功`);
                    resolve(true);
                };
                script.onerror = () => {
                    console.error(`特效 ${effectName} 加载失败`);
                    resolve(false);
                };
            });
        } catch (error) {
            console.error(`加载特效 ${effectName} 时出错:`, error);
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

        // 加载特效脚本
        const loaded = await this.loadEffect(effectName);
        if (!loaded) {
            console.error(`无法加载特效: ${effectName}`);
            return false;
        }

        // 获取特效类
        const effectClassName = this.effectClasses[effectName];
        if (!effectClassName || !window[effectClassName]) {
            console.error(`特效类不存在: ${effectClassName}`);
            return false;
        }

        try {
            // 创建并启动特效实例
            const effectInstance = new window[effectClassName]();
            effectInstance.init();
            
            // 保存到活动特效列表
            this.activeEffects.set(effectName, effectInstance);
            
            console.log(`特效 ${effectName} 已启动`);
            return true;
        } catch (error) {
            console.error(`启动特效 ${effectName} 时出错:`, error);
            return false;
        }
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
                console.log(`特效 ${effectName} 已停止`);
                return true;
            } catch (error) {
                console.error(`停止特效 ${effectName} 时出错:`, error);
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
        console.log('所有特效已停止');
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
        console.log('灰度滤镜已启用');
    }

    disableGrayscale() {
        document.documentElement.style.filter = '';
        console.log('灰度滤镜已禁用');
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
            'festive': ['fireworks', 'confetti', 'lanterns'], // 喜庆节日
            'mourn': ['grayscale', 'candles'], // 纪念悼念
            'spring_festival': ['lanterns', 'firecrackers'], // 春节
            'new_year': ['fireworks', 'confetti'], // 新年
            'cherry_blossom': ['sakura', 'petals'], // 樱花节
            'winter': ['snow', 'clouds'], // 冬季
            'autumn': ['leaves'], // 秋季
            'celebration': ['fireworks', 'confetti'], // 庆祝
            'memorial': ['grayscale', 'candles'], // 追悼
            'valentine': ['sakura', 'petals'], // 情人节
            'christmas': ['snow', 'fireworks'], // 圣诞节
            'national_day': ['fireworks', 'lanterns'], // 国庆节
            'rainy_day': ['rain', 'clouds'], // 雨天
            'stormy': ['rain', 'thunder', 'clouds'], // 暴风雨
            'sunny': ['sunshine'], // 晴天
            'cloudy': ['clouds'], // 多云
            'spring': ['sakura', 'petals', 'sunshine'], // 春天
            'summer': ['sunshine'], // 夏天
            'thunderstorm': ['thunder', 'rain'] // 雷雨
        };

        // 使用传入的特效列表，如果没有则使用预定义组合
        const effectsToStart = effects.length > 0 ? effects : (effectCombinations[anniversaryType] || []);
        
        // 启动特效
        for (const effectName of effectsToStart) {
            await this.startEffect(effectName);
            // 添加小延迟避免同时启动太多特效
            await new Promise(resolve => setTimeout(resolve, 100));
        }

        console.log(`纪念日氛围 ${anniversaryType} 特效已启动:`, effectsToStart);
    }

    /**
     * 获取所有可用的特效名称
     * @returns {Array}
     */
    getAvailableEffects() {
        return Object.keys(this.effectClasses).concat(['grayscale']);
    }

    /**
     * 预加载所有特效脚本
     */
    async preloadAllEffects() {
        const effectNames = Object.keys(this.effectClasses);
        const loadPromises = effectNames.map(name => this.loadEffect(name));
        
        try {
            await Promise.all(loadPromises);
            console.log('所有特效脚本预加载完成');
            return true;
        } catch (error) {
            console.error('特效脚本预加载失败:', error);
            return false;
        }
    }
}

// 创建全局实例
window.effectManager = new EffectManager();

// 导出管理器类
window.EffectManager = EffectManager;

// 页面加载完成后预加载特效
document.addEventListener('DOMContentLoaded', () => {
    if (window.effectManager) {
        window.effectManager.preloadAllEffects();
    }
});