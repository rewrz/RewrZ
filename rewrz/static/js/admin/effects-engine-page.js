function showEffectsPageNotification(message, type = 'info') {
    if (window.adminNotify && typeof window.adminNotify === 'function') {
        window.adminNotify(message, type);
        return;
    }
    alert(message);
}

function previewEffect(effect, title = '') {
    if (effect === 'stop') {
        if (window.effectManager) {
            window.effectManager.stopAll();
        }
        showEffectsPageNotification('已停止所有特效', 'info');
        return;
    }

    if (window.effectManager) {
        window.effectManager.startEffect(effect);
        showEffectsPageNotification(`正在预览：${title || effect}`, 'success');
        setTimeout(() => {
            window.effectManager.stopEffect(effect);
        }, 5000);
    } else {
        showEffectsPageNotification('特效系统未加载，请刷新页面重试', 'error');
    }
}

function previewMultipleEffects(effects, title = '') {
    if (!window.effectManager) {
        showEffectsPageNotification('特效系统未加载，请刷新页面重试', 'error');
        return;
    }

    window.effectManager.stopAll();
    effects.forEach((effect, index) => {
        setTimeout(() => {
            window.effectManager.startEffect(effect);
        }, index * 200);
    });

    showEffectsPageNotification(`正在预览：${title || '多重特效'} (${effects.length} 个特效)`, 'success');
    setTimeout(() => {
        effects.forEach((effect) => {
            window.effectManager.stopEffect(effect);
        });
    }, 8000);
}

function buildAnniversaryOptionsHtml() {
    return `
        <div class="text-xs font-medium text-gray-600 border-b pb-1">🎉 喜庆特效</div>
        <label class="flex items-center text-sm"><input type="checkbox" value="fireworks" class="effect-checkbox mr-2">🎆 烟花绽放</label>
        <label class="flex items-center text-sm"><input type="checkbox" value="lanterns" class="effect-checkbox mr-2">🏮 红灯笼</label>
        <label class="flex items-center text-sm"><input type="checkbox" value="firecrackers" class="effect-checkbox mr-2">🧨 爆竹声声</label>
        <label class="flex items-center text-sm"><input type="checkbox" value="confetti" class="effect-checkbox mr-2">🎊 彩带飞舞</label>
        <div class="text-xs font-medium text-gray-600 border-b pb-1 pt-2">🕯️ 纪念特效</div>
        <label class="flex items-center text-sm"><input type="checkbox" value="grayscale" class="effect-checkbox mr-2">⚫ 全站灰白</label>
        <label class="flex items-center text-sm"><input type="checkbox" value="candles" class="effect-checkbox mr-2">🕯️ 蜡烛摇曳</label>
        <label class="flex items-center text-sm"><input type="checkbox" value="petals" class="effect-checkbox mr-2">🌸 花瓣飘落</label>
        <div class="text-xs font-medium text-gray-600 border-b pb-1 pt-2">🌨️ 季节特效</div>
        <label class="flex items-center text-sm"><input type="checkbox" value="snow" class="effect-checkbox mr-2">❄️ 雪花飘飘</label>
        <label class="flex items-center text-sm"><input type="checkbox" value="sakura" class="effect-checkbox mr-2">🌸 樱花飞舞</label>
        <label class="flex items-center text-sm"><input type="checkbox" value="leaves" class="effect-checkbox mr-2">🍂 落叶纷飞</label>
        <div class="text-xs font-medium text-gray-600 border-b pb-1 pt-2">🌦️ 天气特效</div>
        <label class="flex items-center text-sm"><input type="checkbox" value="rain" class="effect-checkbox mr-2">🌧️ 下雨天</label>
        <label class="flex items-center text-sm"><input type="checkbox" value="thunder" class="effect-checkbox mr-2">⚡ 雷电交加</label>
        <label class="flex items-center text-sm"><input type="checkbox" value="clouds" class="effect-checkbox mr-2">☁️ 云雾缭绕</label>
        <label class="flex items-center text-sm"><input type="checkbox" value="sunshine" class="effect-checkbox mr-2">☀️ 阳光明媚</label>
    `;
}

function addAnniversaryItem() {
    const container = document.getElementById('anniversaries-container');
    const emptyState = container.querySelector('.text-center');
    if (emptyState) {
        emptyState.remove();
    }

    const newItem = document.createElement('div');
    newItem.className = 'anniversary-item theme-anniversary-item bg-gray-50 rounded-lg p-4 border border-gray-200';
    newItem.innerHTML = `
        <div class="grid grid-cols-1 md:grid-cols-5 gap-4 items-center">
            <div class="flex space-x-2">
                <input type="number" class="w-16 px-2 py-2 border border-gray-300 rounded text-center" placeholder="月" min="1" max="12">
                <span class="py-2 text-gray-500">月</span>
                <input type="number" class="w-16 px-2 py-2 border border-gray-300 rounded text-center" placeholder="日" min="1" max="31">
                <span class="py-2 text-gray-500">日</span>
            </div>
            <div>
                <input type="text" class="w-full px-3 py-2 border border-gray-300 rounded" placeholder="节日名称（如：国庆节）">
            </div>
            <div>
                <select class="w-full px-3 py-2 border border-gray-300 rounded anniversary-type-select">
                    <option value="festive">🎉 喜庆节日</option>
                    <option value="mourn">🕯️ 纪念悼念</option>
                    <option value="spring_festival">🏮 春节</option>
                    <option value="new_year">🎆 新年</option>
                    <option value="cherry_blossom">🌸 樱花节</option>
                    <option value="winter">❄️ 冬季</option>
                    <option value="autumn">🍂 秋季</option>
                    <option value="celebration">🎊 庆祝</option>
                    <option value="memorial">🕊️ 追悼</option>
                    <option value="valentine">💖 情人节</option>
                    <option value="christmas">🎄 圣诞节</option>
                    <option value="national_day">🇨🇳 国庆节</option>
                    <option value="rainy_day">🌧️ 雨天</option>
                    <option value="stormy">⛈️ 暴风雨</option>
                    <option value="sunny">☀️ 晴天</option>
                    <option value="cloudy">☁️ 多云</option>
                    <option value="spring">🌱 春天</option>
                    <option value="summer">😎 夏天</option>
                    <option value="thunderstorm">⚡ 雷雨</option>
                </select>
            </div>
            <div>
                <label class="text-xs text-gray-500 block mb-1">特效选择（可多选）</label>
                <div class="max-h-32 overflow-y-auto border border-gray-300 rounded bg-white">
                    <div class="p-2 space-y-1">
                        ${buildAnniversaryOptionsHtml()}
                    </div>
                </div>
            </div>
            <div class="flex flex-wrap gap-2">
                <button type="button" class="preview-anniversary px-3 py-2 bg-blue-500 text-white rounded text-sm hover:bg-blue-600">
                    <i class="fas fa-eye"></i> 预览
                </button>
                <button type="button" class="remove-anniversary px-3 py-2 bg-red-500 text-white rounded text-sm hover:bg-red-600">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `;
    container.appendChild(newItem);
    attachAnniversaryEvents(newItem);
}

function attachAnniversaryEvents(item) {
    item.querySelector('.remove-anniversary')?.addEventListener('click', function() {
        item.remove();
        const container = document.getElementById('anniversaries-container');
        if (container.children.length === 0) {
            container.innerHTML = `
                <div class="text-center py-8 text-gray-500">
                    <i class="fas fa-calendar-plus text-4xl mb-4"></i>
                    <p>还没有设置任何纪念日特效规则</p>
                    <p class="text-sm">点击下方按钮添加第一条纪念日规则</p>
                </div>
            `;
        }
    });

    item.querySelector('.preview-anniversary')?.addEventListener('click', function() {
        const inputs = item.querySelectorAll('input[type="number"], input[type="text"], select');
        const checkboxes = item.querySelectorAll('.effect-checkbox:checked');
        const month = inputs[0].value;
        const day = inputs[1].value;
        const name = inputs[2].value;
        const effects = Array.from(checkboxes).map((checkbox) => checkbox.value);

        if (month && day && name && effects.length > 0) {
            previewMultipleEffects(effects, `${name}（${month}月${day}日）`);
        } else {
            showEffectsPageNotification('请先完整填写纪念日信息并选择至少一个特效', 'warning');
        }
    });
}

async function saveAnniversaries() {
    const anniversaries = [];
    document.querySelectorAll('.anniversary-item').forEach((item) => {
        const inputs = item.querySelectorAll('input[type="number"], input[type="text"], select');
        const checkboxes = item.querySelectorAll('.effect-checkbox:checked');

        if (inputs.length >= 4) {
            const month = parseInt(inputs[0].value, 10);
            const day = parseInt(inputs[1].value, 10);
            const name = inputs[2].value.trim();
            const type = inputs[3].value;
            const effects = Array.from(checkboxes).map((checkbox) => checkbox.value);

            if (month && day && name && type) {
                anniversaries.push({ month, day, name, type, effects });
            }
        }
    });

    try {
        const response = await fetch(`${window.ADMIN_PATH}/api/v1/anniversary-mode/save`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': document.querySelector('input[name="csrf_token"]').value,
            },
            body: JSON.stringify({ anniversaries }),
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        if (!result.success) {
            throw new Error(result.message || '保存失败');
        }

        showEffectsPageNotification(`已保存 ${anniversaries.length} 条纪念日特效规则`, 'success');
    } catch (error) {
        console.error('保存纪念日特效规则错误:', error);
        showEffectsPageNotification(`保存失败: ${error.message}`, 'error');
    }
}

function addScheduleItem() {
    const container = document.getElementById('schedule-container');
    const emptyState = container.querySelector('.text-center');
    if (emptyState) {
        emptyState.remove();
    }

    const sourceSelect = document.querySelector('#schedule-container .schedule-item select');
    const scheduleOptionsHtml = sourceSelect
        ? sourceSelect.innerHTML
        : ['<option value="">无特效</option>', '<option value="festive">festive</option>', '<option value="memorial">memorial</option>', '<option value="celebration">celebration</option>'].join('');

    const newItem = document.createElement('div');
    newItem.className = 'schedule-item theme-schedule-item bg-gray-50 rounded-lg p-4 border border-gray-200';
    newItem.innerHTML = `
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 items-center">
            <div class="space-y-2">
                <label class="text-xs text-gray-500">开始时间</label>
                <input type="date" class="w-full px-3 py-2 border border-gray-300 rounded text-sm">
            </div>
            <div class="space-y-2">
                <label class="text-xs text-gray-500">结束时间</label>
                <input type="date" class="w-full px-3 py-2 border border-gray-300 rounded text-sm">
            </div>
            <div class="space-y-2">
                <label class="text-xs text-gray-500">特效场景</label>
                <select class="w-full px-3 py-2 border border-gray-300 rounded text-sm">
                    ${scheduleOptionsHtml}
                </select>
            </div>
            <div class="flex flex-wrap gap-2">
                <button type="button" class="preview-schedule px-3 py-2 bg-blue-500 text-white rounded text-sm hover:bg-blue-600">
                    <i class="fas fa-eye"></i>
                </button>
                <button type="button" class="remove-schedule px-3 py-2 bg-red-500 text-white rounded text-sm hover:bg-red-600">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `;
    container.appendChild(newItem);
    attachScheduleEvents(newItem);
}

function attachScheduleEvents(item) {
    item.querySelector('.remove-schedule')?.addEventListener('click', function() {
        item.remove();
        const container = document.getElementById('schedule-container');
        if (container.children.length === 0) {
            container.innerHTML = `
                <div class="text-center py-8 text-gray-500">
                    <i class="fas fa-calendar-alt text-4xl mb-4"></i>
                    <p>还没有设置任何节日特效调度</p>
                    <p class="text-sm">点击下方按钮添加第一条调度规则</p>
                </div>
            `;
        }
    });

    item.querySelector('.preview-schedule')?.addEventListener('click', function() {
        const inputs = item.querySelectorAll('input[type="date"], select');
        const startDate = inputs[0].value;
        const endDate = inputs[1].value;
        const scene = inputs[2].value;

        if (startDate && endDate && scene) {
            showEffectsPageNotification(`预览调度：${startDate} 至 ${endDate} - ${scene}`, 'info');
        } else {
            showEffectsPageNotification('请先完整填写调度信息', 'warning');
        }
    });
}

async function saveSchedule() {
    const schedules = [];
    document.querySelectorAll('.schedule-item').forEach((item) => {
        const inputs = item.querySelectorAll('input[type="date"], select');
        if (inputs.length >= 3) {
            const startDate = inputs[0].value;
            const endDate = inputs[1].value;
            const scene = inputs[2].value;
            if (startDate && endDate && scene) {
                schedules.push({
                    start_date: startDate,
                    end_date: endDate,
                    atmosphere: scene,
                });
            }
        }
    });

    try {
        const response = await fetch(`${window.ADMIN_PATH}/api/v1/theme-schedule/save`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': document.querySelector('input[name="csrf_token"]').value,
            },
            body: JSON.stringify({ schedules }),
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        if (!result.success) {
            throw new Error(result.message || '保存失败');
        }

        showEffectsPageNotification(`已保存 ${schedules.length} 条节日特效调度规则`, 'success');
    } catch (error) {
        console.error('保存节日特效调度设置错误:', error);
        showEffectsPageNotification(`保存失败: ${error.message}`, 'error');
    }
}

document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('add-anniversary')?.addEventListener('click', addAnniversaryItem);
    document.getElementById('save-anniversaries')?.addEventListener('click', saveAnniversaries);
    document.getElementById('preview-all-anniversaries')?.addEventListener('click', function() {
        const effects = Array.from(document.querySelectorAll('.anniversary-item .effect-checkbox:checked')).map((checkbox) => checkbox.value);
        const uniqueEffects = [...new Set(effects)];
        if (uniqueEffects.length === 0) {
            showEffectsPageNotification('当前没有选中的特效可预览', 'warning');
            return;
        }
        previewMultipleEffects(uniqueEffects, '全部纪念日特效');
    });

    document.getElementById('add-schedule')?.addEventListener('click', addScheduleItem);
    document.getElementById('save-schedule')?.addEventListener('click', saveSchedule);

    document.querySelectorAll('.effect-preview-btn').forEach((button) => {
        button.addEventListener('click', function() {
            previewEffect(this.dataset.effect);
        });
    });

    document.querySelectorAll('.anniversary-item').forEach(attachAnniversaryEvents);
    document.querySelectorAll('.schedule-item').forEach(attachScheduleEvents);

    const effectCombinations = {
        festive: ['fireworks', 'confetti', 'lanterns'],
        mourn: ['grayscale', 'candles'],
        spring_festival: ['lanterns', 'firecrackers'],
        new_year: ['fireworks', 'confetti'],
        cherry_blossom: ['sakura', 'petals'],
        winter: ['snow', 'clouds'],
        autumn: ['leaves'],
        celebration: ['fireworks', 'confetti'],
        memorial: ['grayscale', 'candles'],
        valentine: ['sakura', 'petals'],
        christmas: ['snow', 'fireworks'],
        national_day: ['fireworks', 'lanterns'],
        rainy_day: ['rain', 'clouds'],
        stormy: ['rain', 'thunder', 'clouds'],
        sunny: ['sunshine'],
        cloudy: ['clouds'],
        spring: ['sakura', 'petals', 'sunshine'],
        summer: ['sunshine'],
        thunderstorm: ['thunder', 'rain'],
    };

    function updateEffectCheckboxes(anniversaryItem, selectedType) {
        const effects = effectCombinations[selectedType] || [];
        anniversaryItem.querySelectorAll('.effect-checkbox').forEach((checkbox) => {
            checkbox.checked = effects.includes(checkbox.value);
        });
    }

    document.getElementById('anniversaries-container')?.addEventListener('change', function(event) {
        if (event.target.classList.contains('anniversary-type-select')) {
            const anniversaryItem = event.target.closest('.anniversary-item');
            if (anniversaryItem) {
                updateEffectCheckboxes(anniversaryItem, event.target.value);
            }
        }
    });
});
