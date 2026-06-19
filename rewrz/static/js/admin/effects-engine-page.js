function showEffectsPageNotification(message, type = 'info') {
    if (window.adminNotify && typeof window.adminNotify === 'function') {
        window.adminNotify(message, type);
        return;
    }
    alert(message);
}

function getEffectOptions() {
    return Array.isArray(window.__EFFECT_OPTIONS__) ? window.__EFFECT_OPTIONS__ : [];
}

function getScenePresets() {
    return window.__EFFECT_SCENE_PRESETS__ || {};
}

function getSceneOptions() {
    return Array.isArray(window.__EFFECT_SCENE_OPTIONS__) ? window.__EFFECT_SCENE_OPTIONS__ : [];
}

function getEffectOptionByValue(effectValue) {
    return getEffectOptions().find((option) => option.value === effectValue) || null;
}

function getSceneOptionsHtml(selectedScene = '') {
    return getSceneOptions().map((sceneOption) => {
        const selected = sceneOption.value === selectedScene ? 'selected' : '';
        return `<option value="${sceneOption.value}" ${selected}>${sceneOption.label}</option>`;
    }).join('');
}

function getSceneLabel(sceneValue = '') {
    const option = getSceneOptions().find((scene) => scene.value === sceneValue);
    return option ? option.label : sceneValue || '未设置';
}

function getEffectCheckboxesHtml(selectedEffects = []) {
    const selectedSet = new Set(Array.isArray(selectedEffects) ? selectedEffects : []);
    return getEffectOptions().map((option) => {
        const checked = selectedSet.has(option.value) ? 'checked' : '';
        return `
            <label class="flex items-center gap-2 text-sm">
                <input type="checkbox" class="custom-anniversary-effect h-4 w-4" value="${option.value}" ${checked}>
                <span>${option.icon}</span>
                <span>${option.label}</span>
            </label>
        `;
    }).join('');
}

function getPublicEffectCheckboxesHtml(selectedEffects = []) {
    const selectedSet = new Set(Array.isArray(selectedEffects) ? selectedEffects : []);
    return getEffectOptions().map((option) => {
        const checked = selectedSet.has(option.value) ? 'checked' : '';
        return `
            <label class="flex items-center gap-2 text-sm">
                <input type="checkbox" class="public-holiday-effect h-4 w-4" value="${option.value}" ${checked}>
                <span>${option.icon}</span>
                <span>${option.label}</span>
            </label>
        `;
    }).join('');
}

function slugifyEffectLabel(label = '') {
    return String(label || '')
        .toLowerCase()
        .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-')
        .replace(/^-+|-+$/g, '') || 'group';
}

function getEffectPreviewGroups() {
    return [
        {
            key: 'festive',
            title: '节庆烟火',
            description: '适合跨年、春节、国庆、站庆等热闹场景',
            effects: ['fireworks', 'countdown_banner', 'confetti', 'golden_dust', 'red_packets', 'ingots'],
        },
        {
            key: 'traditional',
            title: '中式节俗',
            description: '适合元宵、端午、中秋、七夕、小年等传统节日',
            effects: ['lanterns', 'firecrackers', 'embers', 'rice_grains', 'tangyuan', 'dragon_shape', 'dragon_boats', 'zongzi', 'star_bridge', 'feathers', 'osmanthus', 'dumplings', 'tree_lights'],
        },
        {
            key: 'memorial',
            title: '纪念追思',
            description: '适合清明、中元和庄重纪念类场景',
            effects: ['grayscale', 'candles', 'floating_lights', 'paper_charms', 'lotus_lights', 'willow_catkins'],
        },
        {
            key: 'romance',
            title: '浪漫花景',
            description: '适合情人节、妇女节、母亲节、教师节等柔和氛围',
            effects: ['hearts', 'petals', 'sakura', 'chalk_writing'],
        },
        {
            key: 'weather',
            title: '天气与季节',
            description: '适合冬季、秋季、春季和自然氛围场景',
            effects: ['moonlight', 'stars', 'snow', 'leaves', 'rain', 'thunder', 'clouds', 'sunshine', 'bubbles', 'balloons'],
        },
        {
            key: 'symbols',
            title: '节日符号',
            description: '适合劳动节、父亲节等具象符号场景',
            effects: ['gear_icons', 'tie_icons'],
        },
    ];
}

function buildEffectPreviewButtonHtml(option) {
    return `
        <button type="button" class="effect-preview-btn p-4 border border-gray-200 rounded-lg hover:border-blue-300 hover:bg-blue-50 transition-colors"
                data-effect="${option.value}">
            <div class="text-2xl mb-2">${option.icon}</div>
            <div class="font-medium">${option.label}</div>
            <div class="text-xs text-gray-500">${option.description}</div>
        </button>
    `;
}

function renderEffectPreviewGroups() {
    const container = document.getElementById('effect-preview-groups');
    if (!container) {
        return;
    }

    const optionsByValue = new Map(getEffectOptions().map((option) => [option.value, option]));
    const usedEffects = new Set();
    const sectionsHtml = [];

    getEffectPreviewGroups().forEach((group, index) => {
        const groupOptions = group.effects
            .map((effect) => optionsByValue.get(effect))
            .filter(Boolean);
        if (groupOptions.length === 0) {
            return;
        }
        groupOptions.forEach((option) => usedEffects.add(option.value));
        const groupId = `effect-preview-group-${slugifyEffectLabel(group.key)}`;
        const buttonsHtml = groupOptions.map(buildEffectPreviewButtonHtml).join('');
        sectionsHtml.push(`
            <section class="effect-preview-group rounded-2xl border border-gray-200 bg-gray-50/80 overflow-hidden">
                <button type="button"
                        class="effect-preview-group-toggle w-full flex items-center justify-between gap-4 px-5 py-4 text-left"
                        data-target-id="${groupId}"
                        aria-expanded="${index === 0 ? 'true' : 'false'}">
                    <span class="min-w-0">
                        <span class="block text-base font-semibold">${group.title}</span>
                        <span class="block text-sm text-gray-500 mt-1">${group.description}</span>
                    </span>
                    <span class="inline-flex items-center gap-3 shrink-0">
                        <span class="text-xs rounded-full border border-gray-200 bg-white px-2.5 py-1">${groupOptions.length} 个特效</span>
                        <i class="fas fa-chevron-down effect-preview-group-toggle-icon text-xs ${index === 0 ? 'rotate-180' : ''}"></i>
                    </span>
                </button>
                <div id="${groupId}" class="effect-preview-group-panel ${index === 0 ? '' : 'hidden'} px-5 pb-5">
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                        ${buttonsHtml}
                    </div>
                </div>
            </section>
        `);
    });

    const remainingOptions = getEffectOptions().filter((option) => !usedEffects.has(option.value));
    if (remainingOptions.length > 0) {
        const remainingId = 'effect-preview-group-extra';
        sectionsHtml.push(`
            <section class="effect-preview-group rounded-2xl border border-gray-200 bg-gray-50/80 overflow-hidden">
                <button type="button"
                        class="effect-preview-group-toggle w-full flex items-center justify-between gap-4 px-5 py-4 text-left"
                        data-target-id="${remainingId}"
                        aria-expanded="false">
                    <span class="min-w-0">
                        <span class="block text-base font-semibold">补充特效</span>
                        <span class="block text-sm text-gray-500 mt-1">未归入主题分组的附加能力，按需预览。</span>
                    </span>
                    <span class="inline-flex items-center gap-3 shrink-0">
                        <span class="text-xs rounded-full border border-gray-200 bg-white px-2.5 py-1">${remainingOptions.length} 个特效</span>
                        <i class="fas fa-chevron-down effect-preview-group-toggle-icon text-xs"></i>
                    </span>
                </button>
                <div id="${remainingId}" class="effect-preview-group-panel hidden px-5 pb-5">
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                        ${remainingOptions.map(buildEffectPreviewButtonHtml).join('')}
                    </div>
                </div>
            </section>
        `);
    }

    sectionsHtml.push(`
        <div class="flex justify-end">
            <button type="button" class="effect-preview-btn p-4 border border-gray-200 rounded-lg hover:border-red-300 hover:bg-red-50 transition-colors" data-effect="stop">
                <div class="text-2xl mb-2">⏹️</div>
                <div class="font-medium">停止特效</div>
                <div class="text-xs text-gray-500">清除所有</div>
            </button>
        </div>
    `);

    container.innerHTML = sectionsHtml.join('');
}

function bindEffectPreviewButtons() {
    document.querySelectorAll('.effect-preview-btn').forEach((button) => {
        button.addEventListener('click', function() {
            previewEffect(this.dataset.effect);
        });
    });

    document.querySelectorAll('.effect-preview-group-toggle').forEach((button) => {
        button.addEventListener('click', function() {
            const targetId = this.dataset.targetId;
            const panel = targetId ? document.getElementById(targetId) : null;
            const icon = this.querySelector('.effect-preview-group-toggle-icon');
            if (!panel) {
                return;
            }
            const shouldOpen = panel.classList.contains('hidden');
            panel.classList.toggle('hidden', !shouldOpen);
            this.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');
            if (icon) {
                icon.classList.toggle('rotate-180', shouldOpen);
            }
        });
    });
}

function previewEffect(effect, title = '') {
    if (effect === 'stop') {
        if (window.effectManager) {
            window.effectManager.stopAll();
        }
        showEffectsPageNotification('已停止所有特效', 'info');
        return;
    }

    if (!window.effectManager) {
        showEffectsPageNotification('特效系统未加载，请刷新页面重试', 'error');
        return;
    }

    window.effectManager.startEffect(effect);
    const effectMeta = getEffectOptionByValue(effect);
    const effectTitle = title || (effectMeta ? effectMeta.label : effect);
    showEffectsPageNotification(`正在预览：${effectTitle}`, 'success');
    setTimeout(() => {
        window.effectManager.stopEffect(effect);
    }, 5000);
}

function previewMultipleEffects(effects, title = '') {
    if (!window.effectManager) {
        showEffectsPageNotification('特效系统未加载，请刷新页面重试', 'error');
        return;
    }

    const uniqueEffects = [...new Set((effects || []).filter(Boolean))];
    if (uniqueEffects.length === 0) {
        showEffectsPageNotification('当前没有可预览的特效', 'warning');
        return;
    }

    window.effectManager.stopAll();
    uniqueEffects.forEach((effect, index) => {
        setTimeout(() => {
            window.effectManager.startEffect(effect);
        }, index * 160);
    });

    showEffectsPageNotification(`正在预览：${title || '多重特效'} (${uniqueEffects.length} 个特效)`, 'success');
    setTimeout(() => {
        uniqueEffects.forEach((effect) => {
            window.effectManager.stopEffect(effect);
        });
    }, 8000);
}

function updateEffectsByScene(container, scene, effectSelector) {
    const presets = getScenePresets();
    const effects = Array.isArray(presets[scene]) ? presets[scene] : [];
    container.querySelectorAll(effectSelector).forEach((checkbox) => {
        checkbox.checked = effects.includes(checkbox.value);
    });
}

function getEnabledStatusText(enabled) {
    return enabled ? '已启用' : '已停用';
}

function getSummaryEffectsCount(container, selector) {
    return container.querySelectorAll(`${selector}:checked`).length;
}

function updatePublicHolidaySummary(item) {
    if (!item) {
        return;
    }
    const name = item.querySelector('.public-holiday-name')?.value.trim() || '未命名公共节日';
    const scene = item.querySelector('.public-holiday-scene')?.value || '';
    const enabled = Boolean(item.querySelector('.public-holiday-enabled')?.checked);
    const startAt = item.dataset.startAt || '';
    const calendarTypeLabel = item.dataset.calendarTypeLabel || '';
    const title = item.querySelector('.public-holiday-title');
    const summary = item.querySelector('.public-holiday-summary');
    const status = item.querySelector('.public-holiday-status');
    const effectsCount = getSummaryEffectsCount(item, '.public-holiday-effect');

    if (title) {
        title.textContent = name;
    }
    if (summary) {
        summary.textContent = `日期：${startAt} · 类型：${calendarTypeLabel} · 场景：${getSceneLabel(scene)} · ${effectsCount} 个特效`;
    }
    if (status) {
        status.textContent = getEnabledStatusText(enabled);
        status.className = `public-holiday-status inline-flex items-center rounded-full border px-2.5 py-1 text-xs ${enabled ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-gray-200 bg-white text-gray-500'}`;
    }
}

function updateCustomAnniversarySummary(item) {
    if (!item) {
        return;
    }
    const name = item.querySelector('.custom-anniversary-name')?.value.trim() || '新的自定义纪念日';
    const scene = item.querySelector('.custom-anniversary-scene')?.value || '';
    const enabled = Boolean(item.querySelector('.custom-anniversary-enabled')?.checked);
    const dateType = item.querySelector('.custom-anniversary-date-type')?.value || 'solar_fixed';
    const month = item.querySelector('.custom-anniversary-month')?.value || '?';
    const day = item.querySelector('.custom-anniversary-day')?.value || '?';
    const title = item.querySelector('.custom-anniversary-title');
    const summary = item.querySelector('.custom-anniversary-summary');
    const meta = item.querySelector('.custom-anniversary-meta');
    const status = item.querySelector('.custom-anniversary-status');
    const effectsCount = getSummaryEffectsCount(item, '.custom-anniversary-effect');
    const dateTypeLabel = dateType === 'lunar_fixed' ? '农历固定' : '公历固定';

    if (title) {
        title.textContent = name;
    }
    if (summary) {
        summary.textContent = `日期：${month} 月 ${day} 日 · ${dateTypeLabel} · 场景：${getSceneLabel(scene)} · ${effectsCount} 个特效`;
    }
    if (meta) {
        meta.textContent = '自定义纪念日默认高于公共节日；如果同一天还有其他节日命中，系统会自动合并并去重特效。';
    }
    if (status) {
        status.textContent = getEnabledStatusText(enabled);
        status.className = `custom-anniversary-status inline-flex items-center rounded-full border px-2.5 py-1 text-xs ${enabled ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-gray-200 bg-white text-gray-500'}`;
    }
}

function toggleConfigPanel(item, explicitState = null) {
    const panel = item?.querySelector('.effect-config-panel');
    const button = item?.querySelector('.effect-config-toggle');
    const icon = button?.querySelector('.effect-config-toggle-icon');
    const label = button?.querySelector('.effect-config-toggle-label');
    if (!panel || !button) {
        return;
    }
    const shouldOpen = explicitState === null ? panel.classList.contains('hidden') : Boolean(explicitState);
    panel.classList.toggle('hidden', !shouldOpen);
    button.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');
    if (label) {
        label.textContent = shouldOpen ? '收起详情' : '展开详情';
    }
    if (icon) {
        icon.classList.toggle('rotate-180', shouldOpen);
    }
}

function buildCustomAnniversaryItemHtml(data = {}) {
    const id = data.id || `custom-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    const name = data.name || '';
    const dateType = data.date_type || data.calendar_type || 'solar_fixed';
    const month = (data.date_rule && data.date_rule.month) || data.month || '';
    const day = (data.date_rule && data.date_rule.day) || data.day || '';
    const scene = data.effect_scene || data.type || 'festive';
    const enabled = data.enabled === false ? '' : 'checked';
    const recurring = data.is_recurring === false ? '' : 'checked';
    const notes = data.notes || '';
    const effects = Array.isArray(data.effects) ? data.effects : [];
    const dateTypeLabel = dateType === 'lunar_fixed' ? '农历固定' : '公历固定';
    const statusClass = data.enabled === false
        ? 'border-gray-200 bg-white text-gray-500'
        : 'border-emerald-200 bg-emerald-50 text-emerald-700';
    const effectsCount = effects.length;

    return `
        <div class="anniversary-item theme-anniversary-item rounded-2xl border border-gray-200 p-5 bg-gray-50/80 custom-anniversary-item"
             data-id="${id}">
            <div class="flex flex-col gap-4">
                <div class="flex flex-wrap items-center justify-between gap-3">
                    <div class="min-w-0 flex-1">
                        <div class="flex flex-wrap items-center gap-2">
                            <h3 class="text-lg font-semibold custom-anniversary-title">${name || '新的自定义纪念日'}</h3>
                            <span class="inline-flex items-center rounded-full border border-red-100 px-2.5 py-1 text-xs bg-red-50 text-red-700">自定义纪念日</span>
                            <span class="custom-anniversary-status inline-flex items-center rounded-full border px-2.5 py-1 text-xs ${statusClass}">${data.enabled === false ? '已停用' : '已启用'}</span>
                        </div>
                        <div class="custom-anniversary-summary text-sm text-gray-500 mt-2">日期：${month || '?'} 月 ${day || '?'} 日 · ${dateTypeLabel} · 场景：${getSceneLabel(scene)} · ${effectsCount} 个特效</div>
                    </div>
                    <button type="button" class="effect-config-toggle inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm" data-target-id="custom-anniversary-${id}">
                        <span class="effect-config-toggle-label">展开详情</span>
                        <i class="fas fa-chevron-down effect-config-toggle-icon text-xs"></i>
                    </button>
                </div>

                <div id="custom-anniversary-${id}" class="effect-config-panel hidden rounded-2xl border border-gray-200 bg-white p-4">
                    <div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1.1fr)_minmax(300px,0.9fr)] gap-5">
                        <div class="space-y-4">
                            <div class="rounded-xl border border-red-100 bg-red-50/70 px-4 py-3 text-sm text-red-700 custom-anniversary-meta">
                                自定义纪念日默认高于公共节日；如果同一天还有其他节日命中，系统会自动合并并去重特效。
                            </div>

                            <div class="flex flex-wrap items-start justify-between gap-3">
                                <label class="flex-1 min-w-[220px]">
                                    <span class="text-xs text-gray-500 block mb-1">名称</span>
                                    <input type="text" class="custom-anniversary-name w-full px-3 py-2 border border-gray-300 rounded" value="${name}">
                                </label>
                                <label class="inline-flex items-center gap-2 text-sm pt-6">
                                    <input type="checkbox" class="custom-anniversary-enabled h-4 w-4" ${enabled}>
                                    启用这个纪念日
                                </label>
                            </div>

                            <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                                <label>
                                    <span class="text-xs text-gray-500 block mb-1">日期类型</span>
                                    <select class="custom-anniversary-date-type w-full px-3 py-2 border border-gray-300 rounded">
                                        <option value="solar_fixed" ${dateType === 'solar_fixed' ? 'selected' : ''}>公历固定</option>
                                        <option value="lunar_fixed" ${dateType === 'lunar_fixed' ? 'selected' : ''}>农历固定</option>
                                    </select>
                                </label>
                                <label>
                                    <span class="text-xs text-gray-500 block mb-1">月</span>
                                    <input type="number" class="custom-anniversary-month w-full px-3 py-2 border border-gray-300 rounded" min="1" max="12" value="${month}">
                                </label>
                                <label>
                                    <span class="text-xs text-gray-500 block mb-1">日</span>
                                    <input type="number" class="custom-anniversary-day w-full px-3 py-2 border border-gray-300 rounded" min="1" max="31" value="${day}">
                                </label>
                                <label class="flex items-end">
                                    <span class="inline-flex items-center gap-2 text-sm py-2">
                                        <input type="checkbox" class="custom-anniversary-recurring h-4 w-4" ${recurring}>
                                        每年循环
                                    </span>
                                </label>
                            </div>

                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <label>
                                    <span class="text-xs text-gray-500 block mb-1">场景</span>
                                    <select class="custom-anniversary-scene w-full px-3 py-2 border border-gray-300 rounded">
                                        ${getSceneOptionsHtml(scene)}
                                    </select>
                                </label>
                                <label>
                                    <span class="text-xs text-gray-500 block mb-1">备注</span>
                                    <input type="text" class="custom-anniversary-notes w-full px-3 py-2 border border-gray-300 rounded" value="${notes}">
                                </label>
                            </div>
                        </div>

                        <div class="space-y-4">
                            <div>
                                <div class="text-xs text-gray-500 block mb-2">特效组合</div>
                                <div class="rounded-xl border border-gray-200 bg-white p-3 grid grid-cols-2 gap-2">
                                    ${getEffectCheckboxesHtml(effects)}
                                </div>
                            </div>
                            <div class="flex flex-wrap gap-2">
                                <button type="button" class="preview-anniversary px-3 py-2 bg-blue-500 text-white rounded text-sm hover:bg-blue-600">
                                    <i class="fas fa-eye mr-1"></i>预览
                                </button>
                                <button type="button" class="remove-anniversary px-3 py-2 bg-red-500 text-white rounded text-sm hover:bg-red-600">
                                    <i class="fas fa-trash mr-1"></i>删除
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function attachCustomAnniversaryEvents(item) {
    item.querySelector('.effect-config-toggle')?.addEventListener('click', function() {
        toggleConfigPanel(item);
    });

    item.querySelector('.remove-anniversary')?.addEventListener('click', function() {
        item.remove();
        const container = document.getElementById('custom-anniversaries-container');
        if (container && container.children.length === 0) {
            container.innerHTML = `
                <div class="text-center py-8 text-gray-500">
                    <i class="fas fa-calendar-plus text-4xl mb-4"></i>
                    <p>还没有设置任何自定义纪念日</p>
                    <p class="text-sm">点击下方按钮添加第一条自定义纪念日规则</p>
                </div>
            `;
        }
    });

    item.querySelector('.custom-anniversary-scene')?.addEventListener('change', function() {
        updateEffectsByScene(item, this.value, '.custom-anniversary-effect');
        updateCustomAnniversarySummary(item);
    });

    item.querySelector('.custom-anniversary-name')?.addEventListener('input', function() {
        updateCustomAnniversarySummary(item);
    });

    item.querySelector('.custom-anniversary-date-type')?.addEventListener('change', function() {
        updateCustomAnniversarySummary(item);
    });

    item.querySelector('.custom-anniversary-month')?.addEventListener('input', function() {
        updateCustomAnniversarySummary(item);
    });

    item.querySelector('.custom-anniversary-day')?.addEventListener('input', function() {
        updateCustomAnniversarySummary(item);
    });

    item.querySelector('.custom-anniversary-enabled')?.addEventListener('change', function() {
        updateCustomAnniversarySummary(item);
    });

    item.querySelectorAll('.custom-anniversary-effect').forEach((checkbox) => {
        checkbox.addEventListener('change', function() {
            updateCustomAnniversarySummary(item);
        });
    });

    item.querySelector('.preview-anniversary')?.addEventListener('click', function() {
        const payload = collectCustomAnniversaryItem(item);
        if (!payload.name || !payload.date_rule.month || !payload.date_rule.day) {
            showEffectsPageNotification('请先完整填写纪念日名称与日期', 'warning');
            return;
        }
        previewMultipleEffects(payload.effects, `${payload.name} 预览`);
    });

    updateCustomAnniversarySummary(item);
}

function addCustomAnniversaryItem(data = {}) {
    const container = document.getElementById('custom-anniversaries-container');
    if (!container) {
        return;
    }
    const emptyState = container.querySelector('.text-center');
    if (emptyState) {
        emptyState.remove();
    }
    const wrapper = document.createElement('div');
    wrapper.innerHTML = buildCustomAnniversaryItemHtml(data);
    const item = wrapper.firstElementChild;
    container.appendChild(item);
    attachCustomAnniversaryEvents(item);
}

function collectCustomAnniversaryItem(item) {
    const month = parseInt(item.querySelector('.custom-anniversary-month')?.value || '', 10);
    const day = parseInt(item.querySelector('.custom-anniversary-day')?.value || '', 10);
    const effects = Array.from(item.querySelectorAll('.custom-anniversary-effect:checked')).map((checkbox) => checkbox.value);
    return {
        id: item.dataset.id || '',
        name: item.querySelector('.custom-anniversary-name')?.value.trim() || '',
        date_type: item.querySelector('.custom-anniversary-date-type')?.value || 'solar_fixed',
        date_rule: {
            month: Number.isFinite(month) ? month : null,
            day: Number.isFinite(day) ? day : null,
        },
        effect_scene: item.querySelector('.custom-anniversary-scene')?.value || 'festive',
        effects,
        enabled: Boolean(item.querySelector('.custom-anniversary-enabled')?.checked),
        is_recurring: Boolean(item.querySelector('.custom-anniversary-recurring')?.checked),
        notes: item.querySelector('.custom-anniversary-notes')?.value.trim() || '',
    };
}

function collectPublicHolidayItem(item) {
    const effects = Array.from(item.querySelectorAll('.public-holiday-effect:checked')).map((checkbox) => checkbox.value);
    return {
        code: item.dataset.code || '',
        name: item.querySelector('.public-holiday-name')?.value.trim() || '',
        effect_scene: item.querySelector('.public-holiday-scene')?.value || 'festive',
        effects,
        enabled: Boolean(item.querySelector('.public-holiday-enabled')?.checked),
    };
}

async function postJson(url, payload) {
    const csrfToken = document.querySelector('input[name="csrf_token"]')?.value || '';
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) {
        throw new Error(data.detail || data.message || `请求失败: ${response.status}`);
    }
    return data;
}

async function savePublicHolidays() {
    const items = Array.from(document.querySelectorAll('.public-holiday-item')).map(collectPublicHolidayItem);
    const year = parseInt(document.getElementById('public-holiday-year')?.value || '', 10) || window.__PUBLIC_HOLIDAY_CATALOG_YEAR__ || new Date().getFullYear();
    try {
        const result = await postJson(`${window.ADMIN_PATH}/api/v1/effects/public-holidays/save`, { year, holidays: items });
        showEffectsPageNotification(result.message || '公共节日配置已保存', 'success');
    } catch (error) {
        showEffectsPageNotification(`保存失败: ${error.message}`, 'error');
    }
}

async function rebuildPublicHolidays() {
    const year = parseInt(document.getElementById('public-holiday-year')?.value || '', 10) || window.__PUBLIC_HOLIDAY_CATALOG_YEAR__ || new Date().getFullYear();
    try {
        const result = await postJson(`${window.ADMIN_PATH}/api/v1/effects/public-holidays/rebuild`, { year });
        showEffectsPageNotification(result.message || '公共节日清单已重建', 'success');
        setTimeout(() => window.location.reload(), 500);
    } catch (error) {
        showEffectsPageNotification(`重建失败: ${error.message}`, 'error');
    }
}

async function saveCustomAnniversaries() {
    const anniversaries = Array.from(document.querySelectorAll('.custom-anniversary-item'))
        .map(collectCustomAnniversaryItem)
        .filter((item) => item.name && item.date_rule.month && item.date_rule.day);
    try {
        const result = await postJson(`${window.ADMIN_PATH}/api/v1/effects/custom-anniversaries/save`, { anniversaries });
        showEffectsPageNotification(result.message || '自定义纪念日已保存', 'success');
    } catch (error) {
        showEffectsPageNotification(`保存失败: ${error.message}`, 'error');
    }
}

document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('save-public-holidays')?.addEventListener('click', savePublicHolidays);
    document.getElementById('rebuild-public-holidays')?.addEventListener('click', rebuildPublicHolidays);
    document.getElementById('save-anniversaries')?.addEventListener('click', saveCustomAnniversaries);
    document.getElementById('add-anniversary')?.addEventListener('click', function() {
        addCustomAnniversaryItem();
    });

    document.getElementById('preview-all-anniversaries')?.addEventListener('click', function() {
        const effects = Array.from(document.querySelectorAll('.custom-anniversary-item .custom-anniversary-effect:checked')).map((checkbox) => checkbox.value);
        previewMultipleEffects(effects, '全部自定义纪念日特效');
    });

    document.querySelectorAll('.custom-anniversary-item').forEach(attachCustomAnniversaryEvents);
    renderEffectPreviewGroups();
    bindEffectPreviewButtons();

    document.querySelectorAll('.effect-config-toggle').forEach((button) => {
        button.addEventListener('click', function() {
            const item = this.closest('.public-holiday-item, .custom-anniversary-item');
            if (item) {
                toggleConfigPanel(item);
            }
        });
    });

    document.querySelectorAll('.public-holiday-scene').forEach((select) => {
        select.addEventListener('change', function() {
            const item = this.closest('.public-holiday-item');
            if (item) {
                updateEffectsByScene(item, this.value, '.public-holiday-effect');
                updatePublicHolidaySummary(item);
            }
        });
    });

    document.querySelectorAll('.public-holiday-item').forEach((item) => {
        item.querySelector('.public-holiday-name')?.addEventListener('input', function() {
            updatePublicHolidaySummary(item);
        });
        item.querySelector('.public-holiday-enabled')?.addEventListener('change', function() {
            updatePublicHolidaySummary(item);
        });
        item.querySelectorAll('.public-holiday-effect').forEach((checkbox) => {
            checkbox.addEventListener('change', function() {
                updatePublicHolidaySummary(item);
            });
        });
        updatePublicHolidaySummary(item);
    });
});
