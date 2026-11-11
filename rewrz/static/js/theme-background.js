// 站点背景统一应用逻辑：前台与后台共用同一份类型、渐变与滤镜规则
(function () {
    'use strict';

    const GRADIENT_IMAGES = {
        gradient: 'linear-gradient(135deg, #6c7ef8 0%, #4b5fcf 100%)',
        gradient1: 'linear-gradient(135deg, #6c7ef8 0%, #4b5fcf 100%)',
        gradient2: 'linear-gradient(135deg, #ffb5c2 0%, #ffd8b8 100%)',
        gradient3: 'linear-gradient(135deg, #c0f4ed 0%, #d8e6ff 100%)',
        gradient4: 'linear-gradient(135deg, #ffe7c8 0%, #ffd1d1 100%)',
    };
    const BACKGROUND_CLASSES = [
        'bg-none', 'bg-gradient', 'bg-gradient-1', 'bg-gradient-2',
        'bg-gradient-3', 'bg-gradient-4', 'bg-custom', 'bg-page-cover',
    ];
    const EFFECT_KEYS = ['glow', 'blur', 'translucent', 'dim', 'particles', 'orbs'];

    function backgroundImageFor(type, customUrl) {
        if (type === 'custom') {
            const url = String(customUrl || '').trim();
            // 用 JSON 字符串字面量生成 CSS url()，避免引号与括号破坏样式声明
            return url ? `url(${JSON.stringify(url)})` : '';
        }
        return GRADIENT_IMAGES[type] || '';
    }

    function clearBackground(body) {
        if (!body) return;
        body.classList.remove(...BACKGROUND_CLASSES);
        const style = body.style;
        style.backgroundImage = '';
        style.backgroundSize = '';
        style.backgroundPosition = '';
        style.backgroundRepeat = '';
        style.backgroundAttachment = '';
        style.removeProperty('--page-bg-image');
    }

    function applyBackground(body, settings) {
        if (!body) return;
        const config = settings || {};
        const type = config.type || 'none';
        const image = backgroundImageFor(type, config.custom_url);
        const style = body.style;

        clearBackground(body);

        if (type === 'custom' && image) {
            body.classList.add('bg-custom');
            style.backgroundImage = image;
            style.backgroundSize = 'cover';
            style.backgroundPosition = 'center';
            style.backgroundRepeat = 'no-repeat';
            style.backgroundAttachment = 'fixed';
        } else if (GRADIENT_IMAGES[type]) {
            body.classList.add('bg-gradient', `bg-gradient-${type === 'gradient' ? '1' : type.slice(-1)}`);
            style.backgroundImage = image;
        } else {
            body.classList.add('bg-none');
        }

        body.dataset.backgroundType = type;
        body.dataset.backgroundUrl = type === 'custom' ? String(config.custom_url || '') : '';
    }

    function setStyleVars(node, vars) {
        Object.keys(vars).forEach((name) => node.style.setProperty(name, vars[name]));
    }

    function ensureFxContent(layer) {
        if (!layer || layer.children.length) return;
        const fragment = document.createDocumentFragment();
        const parts = {};
        ['glow', 'veil', 'particles', 'orbs'].forEach((name) => {
            parts[name] = document.createElement('div');
            parts[name].className = `site-bg-fx-${name}`;
            fragment.appendChild(parts[name]);
        });

        for (let i = 0; i < 36; i += 1) {
            const particle = document.createElement('span');
            setStyleVars(particle, {
                '--p-x': `${(2 + (i * 37) % 96).toFixed(1)}%`,
                '--p-size': `${(1.6 + (i % 5) * 0.7).toFixed(1)}px`,
                '--p-delay': `-${(i * 0.73).toFixed(2)}s`,
                '--p-duration': `${11 + (i % 7) * 2}s`,
                '--p-y': `${5 + (i * 29) % 78}%`,
                '--p-drift': i % 3 === 0 ? '1' : '-1',
                '--p-alpha': (0.45 + (i % 4) * 0.14).toFixed(2),
            });
            parts.particles.appendChild(particle);
        }
        for (let i = 0; i < 18; i += 1) {
            const orb = document.createElement('span');
            setStyleVars(orb, {
                '--orb-x': `${(3 + i * 5.3).toFixed(1)}%`,
                '--orb-size': `${10 + (i % 6) * 5}px`,
                '--orb-delay': `-${(i * 0.9).toFixed(1)}s`,
                '--orb-duration': `${9 + (i % 4) * 2}s`,
                '--orb-y': `${6 + (i * 23) % 72}%`,
                '--orb-drift': i % 2 === 0 ? '1' : '-1',
            });
            parts.orbs.appendChild(orb);
        }
        layer.appendChild(fragment);
    }

    function applyEffects(layer, effects) {
        if (!layer) return;
        ensureFxContent(layer);
        const selected = Array.isArray(effects) ? effects : [];
        EFFECT_KEYS.forEach((key) => {
            layer.classList.toggle(`fx-${key}`, selected.includes(key));
        });
    }

    window.themeBackground = {
        apply: applyBackground,
        clear: clearBackground,
        applyEffects: applyEffects,
        backgroundImageFor: backgroundImageFor,
    };
})();
