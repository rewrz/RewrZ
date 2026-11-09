function showThemePageNotification(message, type = 'info') {
    if (window.adminNotify && typeof window.adminNotify === 'function') {
        window.adminNotify(message, type);
        return;
    }
    alert(message);
}

function currentBackgroundImage() {
    const selected = document.querySelector('input[name="background_type"]:checked');
    const type = selected?.value || 'none';
    if (type === 'custom') {
        const url = document.querySelector('input[name="custom_background_url"]')?.value?.trim() || '';
        return url ? `url('${url.replace(/'/g, '%27')}')` : '';
    }
    if (type === 'none') return '';
    const swatch = selected?.closest('label')?.querySelector('.theme-swatch-option');
    return swatch ? (swatch.style.backgroundImage || swatch.style.background || '') : '';
}

function updateBackgroundPreview() {
    const preview = document.getElementById('background-fx-preview');
    if (!preview) return;
    const backgroundImage = currentBackgroundImage();
    preview.style.backgroundImage = backgroundImage;
    // 后台整页背景与预览使用同一张画面，刷新页面后也能同步显示
    document.body.style.backgroundImage = backgroundImage;
    const layer = preview.querySelector('.site-bg-fx');
    if (!layer) return;
    const activeClasses = [];
    document.querySelectorAll('input[name="background_effects"]').forEach((checkbox) => {
        layer.classList.toggle(`fx-${checkbox.value}`, checkbox.checked);
        if (checkbox.checked) activeClasses.push(`fx-${checkbox.value}`);
    });
    const pageLayer = document.getElementById('theme-admin-bg-fx');
    if (!pageLayer) return;
    if (!pageLayer.children.length) pageLayer.innerHTML = layer.innerHTML;
    pageLayer.className = `site-bg-fx theme-admin-bg-fx${activeClasses.length ? ' ' + activeClasses.join(' ') : ''}`;
}

async function saveBackgroundImage() {
    const selectedValue = document.querySelector('input[name="background_type"]:checked')?.value || 'none';
    const customUrl = document.querySelector('input[name="custom_background_url"]')?.value || '';

    try {
        const formData = new FormData();
        formData.append('background_type', selectedValue);
        if (selectedValue === 'custom' && customUrl) {
            formData.append('custom_background_url', customUrl);
        }
        document.querySelectorAll('input[name="background_effects"]:checked').forEach((checkbox) => {
            formData.append('background_effects', checkbox.value);
        });
        formData.append('csrf_token', document.querySelector('input[name="csrf_token"]').value);

        const response = await fetch(`${window.ADMIN_PATH}/api/v1/admin/themes/background`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        if (!result.success) {
            throw new Error(result.message || '保存失败');
        }

        const bodyStyle = document.body.style;
        switch (selectedValue) {
            case 'gradient1':
                bodyStyle.backgroundImage = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
                break;
            case 'gradient2':
                bodyStyle.backgroundImage = 'linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%)';
                break;
            case 'gradient3':
                bodyStyle.backgroundImage = 'linear-gradient(135deg, #a8edea 0%, #fed6e3 100%)';
                break;
            case 'gradient4':
                bodyStyle.backgroundImage = 'linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%)';
                break;
            case 'custom':
                bodyStyle.backgroundImage = customUrl ? `url('${customUrl}')` : 'none';
                break;
            default:
                bodyStyle.backgroundImage = 'none';
                break;
        }

        showThemePageNotification('背景设置已保存并应用', 'success');
    } catch (error) {
        console.error('保存背景图片设置错误:', error);
        showThemePageNotification(`保存背景图片设置失败: ${error.message}`, 'error');
    }
}

async function createCustomTheme(event) {
    event.preventDefault();

    const form = event.currentTarget;
    const themeName = form.querySelector('input[name="theme_name"]')?.value?.trim() || '';
    const themeData = form.querySelector('textarea[name="theme_data"]')?.value || '';
    const csrfToken = form.querySelector('input[name="csrf_token"]')?.value || '';

    if (!themeName) {
        showThemePageNotification('请先填写主题标识', 'warning');
        return;
    }

    try {
        JSON.parse(themeData);
    } catch (_) {
        showThemePageNotification('主题配置 JSON 格式错误', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('theme_name', themeName);
    formData.append('theme_data', themeData);
    formData.append('csrf_token', csrfToken);

    try {
        const response = await fetch(`${window.ADMIN_PATH}/themes/custom`, {
            method: 'POST',
            body: formData,
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || result.detail || '创建失败');
        }

        window.adminSetFlash?.('自定义主题已创建', 'success');
        window.location.reload();
    } catch (error) {
        console.error('创建自定义主题失败:', error);
        showThemePageNotification(`创建自定义主题失败: ${error.message}`, 'error');
    }
}

async function deleteCustomTheme(themeName) {
    const confirmed = await window.adminConfirm?.(`确认删除自定义主题“${themeName}”吗？`, {
        title: '删除自定义主题',
        confirmText: '删除',
        tone: 'danger',
    });
    if (!confirmed) {
        return;
    }

    try {
        const response = await fetch(`${window.ADMIN_PATH}/themes/custom/${encodeURIComponent(themeName)}`, {
            method: 'DELETE',
            headers: {
                'X-CSRF-Token': document.querySelector('input[name="csrf_token"]')?.value || '',
            },
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || result.detail || '删除失败');
        }

        window.adminSetFlash?.('自定义主题已删除', 'success');
        window.location.reload();
    } catch (error) {
        console.error('删除自定义主题失败:', error);
        showThemePageNotification(`删除自定义主题失败: ${error.message}`, 'error');
    }
}

document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('input[name="current_theme"]').forEach((radio) => {
        radio.addEventListener('change', function() {
            document.querySelectorAll('.theme-option .theme-option-label').forEach((label) => {
                label.classList.remove('is-active');
            });

            if (this.checked) {
                const label = this.nextElementSibling;
                label?.classList.add('is-active');
                const themeName = label?.querySelector('.font-semibold')?.textContent || this.value;
                showThemePageNotification(`已切换到 ${themeName} 主题`, 'success');
                window.dispatchEvent(new Event('adminThemeRefreshRequested'));
                if (window.adminThemeSync && typeof window.adminThemeSync.syncNow === 'function') {
                    setTimeout(() => window.adminThemeSync.syncNow(), 120);
                }
            }
        });
    });

    const themeForm = document.getElementById('theme-form');
    if (themeForm) {
        themeForm.addEventListener('htmx:afterRequest', function() {
            window.dispatchEvent(new Event('adminThemeRefreshRequested'));
            if (window.adminThemeSync && typeof window.adminThemeSync.syncNow === 'function') {
                setTimeout(() => window.adminThemeSync.syncNow(), 80);
            }
        });
    }

    document.querySelectorAll('input[name="background_type"]').forEach((radio) => {
        radio.addEventListener('change', function() {
            if (this.value === 'custom') {
                document.getElementById('custom-background-input')?.classList.remove('hidden');
            } else {
                document.getElementById('custom-background-input')?.classList.add('hidden');
            }
            updateBackgroundPreview();
            saveBackgroundImage();
        });
    });

    const selectedBackgroundType = document.querySelector('input[name="background_type"]:checked')?.value;
    if (selectedBackgroundType === 'custom') {
        document.getElementById('custom-background-input')?.classList.remove('hidden');
    }

    document.querySelectorAll('input[name="background_effects"]').forEach((checkbox) => {
        checkbox.addEventListener('change', function() {
            updateBackgroundPreview();
            saveBackgroundImage();
        });
    });

    const customBackgroundInput = document.querySelector('input[name="custom_background_url"]');
    customBackgroundInput?.addEventListener('input', updateBackgroundPreview);
    customBackgroundInput?.addEventListener('blur', saveBackgroundImage);

    updateBackgroundPreview();

    document.getElementById('custom-theme-form')?.addEventListener('submit', createCustomTheme);
    document.querySelectorAll('.delete-custom-theme').forEach((button) => {
        button.addEventListener('click', function() {
            deleteCustomTheme(this.dataset.themeName || '');
        });
    });
});
