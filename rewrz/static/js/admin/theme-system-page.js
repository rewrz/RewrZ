function showThemePageNotification(message, type = 'info') {
    if (window.adminNotify && typeof window.adminNotify === 'function') {
        window.adminNotify(message, type);
        return;
    }
    alert(message);
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

        showThemePageNotification('背景图片设置已保存并应用', 'success');
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
            saveBackgroundImage();
        });
    });

    const selectedBackgroundType = document.querySelector('input[name="background_type"]:checked')?.value;
    if (selectedBackgroundType === 'custom') {
        document.getElementById('custom-background-input')?.classList.remove('hidden');
    }

    document.querySelector('input[name="custom_background_url"]')?.addEventListener('blur', saveBackgroundImage);

    document.getElementById('custom-theme-form')?.addEventListener('submit', createCustomTheme);
    document.querySelectorAll('.delete-custom-theme').forEach((button) => {
        button.addEventListener('click', function() {
            deleteCustomTheme(this.dataset.themeName || '');
        });
    });
});
