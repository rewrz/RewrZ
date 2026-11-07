(() => {
    'use strict';

    const STYLE_ID = 'rewrz-editor-block-directives-style';
    // 指令名称与参数必须与 rewrz/core/content_utils.py 的 _render_directive_block 一致
    const DIRECTIVES = [
        {
            key: 'notice-info',
            label: '提示块',
            icon: 'fa-info-circle',
            hint: '补充说明、阅读提示',
            placeholder: '在这里填写提示内容',
            build: (content) => `:::notice info\n\n${content}\n\n:::\n`,
        },
        {
            key: 'notice-warn',
            label: '警示块',
            icon: 'fa-exclamation-triangle',
            hint: '风险提醒、重要注意',
            placeholder: '在这里填写警示内容',
            build: (content) => `:::notice warn\n\n${content}\n\n:::\n`,
        },
        {
            key: 'quote',
            label: '引用卡',
            icon: 'fa-quote-right',
            hint: '独立成块的引文',
            placeholder: '在这里填写引用内容',
            build: (content) => `:::quote\n\n${content}\n\n:::\n`,
        },
        {
            key: 'wide',
            label: '宽栏',
            icon: 'fa-expand',
            hint: '突破正文宽度的长图与宽表格',
            placeholder: '在这里填写宽栏内容',
            build: (content) => `:::wide\n\n${content}\n\n:::\n`,
        },
        {
            key: 'columns',
            label: '左右分栏',
            icon: 'fa-columns',
            hint: '两列并排，窄屏自动堆叠',
            placeholder: '在这里填写左栏内容',
            build: (content) => `:::columns\n\n:::left\n\n${content}\n\n:::\n\n:::right\n\n在这里填写右栏内容\n\n:::\n\n:::\n`,
        },
        {
            key: 'timeline',
            label: '时间线',
            icon: 'fa-list-ul',
            hint: '用无序列表按时间罗列事件',
            placeholder: '- 第一件事\n- 第二件事',
            build: (content) => `:::timeline\n\n${content}\n\n:::\n`,
        },
        {
            key: 'gallery',
            label: '图集',
            icon: 'fa-images',
            hint: '块内只展示图片，建议 2~4 张',
            placeholder: '![图片说明](图片地址)',
            build: (content) => `:::gallery\n\n${content}\n\n:::\n`,
        },
        {
            key: 'table',
            label: '表格容器',
            icon: 'fa-table',
            hint: '给宽表格加独立滚动容器',
            placeholder: '| 项目 | 说明 |\n| --- | --- |\n| 内容 | 在这里填写 |',
            build: (content) => `:::table\n\n${content}\n\n:::\n`,
        },
    ];

    const PREVIEW_LABELS = {
        notice: '提示/警示块',
        quote: '引用卡',
        wide: '宽栏',
        columns: '分栏',
        left: '左栏',
        right: '右栏',
        timeline: '时间线',
        gallery: '图集',
        table: '表格容器',
    };
    const DIRECTIVE_OPEN_LINE = /^:::(\w+)(?:\s+([\w-]+))?$/;

    function ensureStyle() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = `
.editor-block-menu-wrap { position: relative; }
.editor-block-menu {
    /* 固定定位，避免被编辑卡片的 overflow:hidden 裁掉 */
    position: fixed;
    z-index: 60;
    width: min(21rem, 88vw);
    max-height: 27rem;
    overflow-y: auto;
    padding: 0.35rem;
    border: 1px solid var(--ui-border);
    border-radius: 0.85rem;
    background: var(--color-card-bg);
    box-shadow: 0 16px 36px color-mix(in srgb, var(--color-text) 14%, transparent);
}
.editor-block-menu[hidden] { display: none; }
.editor-block-menu-item {
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    width: 100%;
    padding: 0.35rem 0.6rem;
    border: 0;
    border-radius: 0.55rem;
    background: transparent;
    color: var(--color-text);
    text-align: left;
    cursor: pointer;
}
.editor-block-menu-item:hover,
.editor-block-menu-item:focus-visible {
    background: color-mix(in srgb, var(--color-primary) 12%, transparent);
    outline: none;
}
.editor-block-menu-icon {
    flex: none;
    width: 1.4rem;
    color: var(--color-primary);
    text-align: center;
}
.editor-block-menu-text { display: flex; flex-direction: column; }
.editor-block-menu-text strong { font-size: 0.86rem; font-weight: 600; line-height: 1.25; }
.editor-block-menu-text small { font-size: 0.74rem; line-height: 1.3; color: var(--color-text-light); }
.editor-block-menu-tip {
    margin: 0.3rem 0.2rem 0.1rem;
    padding-top: 0.4rem;
    border-top: 1px solid var(--ui-border);
    font-size: 0.71rem;
    line-height: 1.5;
    color: var(--color-text-light);
}
.md-directive-tag {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    margin: 0.1rem 0;
    padding: 0.1rem 0.5rem;
    border: 1px solid color-mix(in srgb, var(--color-primary) 32%, transparent);
    border-radius: 999px;
    background: color-mix(in srgb, var(--color-primary) 10%, transparent);
    color: var(--color-primary);
    font-size: 0.76em;
    font-weight: 600;
}
.md-directive-tag::before { content: '\\25B8'; }
.md-directive-tag-end { opacity: 0.75; }
`;
        document.head.appendChild(style);
    }

    /** 正文里是否含有未闭合之外的区块指令，用于保存时强制回到 Markdown 模式。 */
    function hasDirective(content) {
        return String(content || '').split('\n').some((line) => DIRECTIVE_OPEN_LINE.test(line.trim()));
    }

    /**
     * 预览钩子：只把独占一行的 ::: 标记换成可读徽标，不改动预览结构与正文内容。
     * 匹配不到时原样返回，避免误伤代码示例或普通文本里的 :::。
     */
    function decoratePreviewHtml(html) {
        const source = String(html || '');
        if (!source.includes(':::')) return source;

        const open = source.replace(
            /(<p[^>]*>)\s*:::([a-z]+)(?:[ \t]+([\w-]+))?\s*(?=<br\b|<\/p>)/gi,
            (match, tag, name, arg) => {
                const label = PREVIEW_LABELS[name.toLowerCase()];
                if (!label) return match;
                const suffix = arg && /^(warn|warning)$/i.test(arg) ? '（警示）' : '';
                return `${tag}<span class="md-directive-tag">版式：${label}${suffix}</span>`;
            }
        );
        return open.replace(
            /(<p[^>]*>)\s*:::\s*(?=<br\b|<\/p>)/gi,
            (match, tag) => `${tag}<span class="md-directive-tag md-directive-tag-end">版式块结束</span>`
        );
    }

    function readSelection(editor) {
        try {
            if (typeof editor.getSelectedText !== 'function') return '';
            return String(editor.getSelectedText() || '').trim();
        } catch (error) {
            return '';
        }
    }

    function renderMenu(menu) {
        menu.innerHTML = '';
        DIRECTIVES.forEach((item) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'editor-block-menu-item';
            button.dataset.directive = item.key;
            button.innerHTML = `<span class="editor-block-menu-icon"><i class="fas ${item.icon}"></i></span>`
                + `<span class="editor-block-menu-text"><strong>${item.label}</strong><small>${item.hint}</small></span>`;
            menu.appendChild(button);
        });
        const tip = document.createElement('p');
        tip.className = 'editor-block-menu-tip';
        tip.textContent = '版式块仅 Markdown 模式生效，预览显示标记，发布后由前台主题呈现；选中文字后插入可直接入块。';
        menu.appendChild(tip);
    }

    /** 在文章/页面表单里挂载「插入版式」下拉，两个表单共用同一份指令定义。 */
    function init(options) {
        const { button, menu, editor, insertEditorText, getActiveEditorMode, setEditorMode, markDirty } = options;
        if (!button || !menu || !editor) return;
        ensureStyle();
        renderMenu(menu);

        const wrap = button.parentElement;
        // 下方空间不够时向上展开，并限制高度，避免菜单底部被视口或底部操作栏裁切
        const positionMenu = () => {
            const rect = button.getBoundingClientRect();
            const below = window.innerHeight - rect.bottom - 18;
            const above = rect.top - 18;
            const needed = menu.scrollHeight || 409;
            // 下方放不下全部条目且上方更宽裕时，改为向上展开
            const useAbove = below < needed && above > below;
            const available = Math.max(160, useAbove ? above : below);
            menu.style.maxHeight = `${Math.min(needed, available)}px`;

            const width = menu.offsetWidth;
            const height = menu.offsetHeight;
            const left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8));
            const top = useAbove
                ? Math.max(8, rect.top - 6 - height)
                : Math.min(rect.bottom + 6, window.innerHeight - height - 8);
            menu.style.left = `${left}px`;
            menu.style.top = `${Math.max(8, top)}px`;
        };
        const setOpen = (open) => {
            menu.hidden = !open;
            button.setAttribute('aria-expanded', String(open));
            if (open) positionMenu();
        };
        setOpen(false);
        const reposition = () => {
            if (!menu.hidden) positionMenu();
        };
        window.addEventListener('resize', reposition);
        window.addEventListener('scroll', reposition, true);

        // 阻止按钮抢走编辑器焦点，保留光标位置与选区，便于把选中文字包进版式块
        button.addEventListener('mousedown', (event) => event.preventDefault());
        button.addEventListener('click', () => setOpen(menu.hidden));
        document.addEventListener('click', (event) => {
            if (wrap && !wrap.contains(event.target)) setOpen(false);
        });
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') setOpen(false);
        });

        menu.addEventListener('click', (event) => {
            const itemButton = event.target.closest('[data-directive]');
            if (!itemButton) return;
            const item = DIRECTIVES.find((entry) => entry.key === itemButton.dataset.directive);
            if (!item) return;

            setOpen(false);
            const selected = readSelection(editor);
            if (getActiveEditorMode() !== 'markdown') {
                setEditorMode('markdown');
                if (window.adminNotify) {
                    window.adminNotify('版式块仅在 Markdown 模式生效，已自动切换。', 'info', { duration: 2200 });
                }
            }
            insertEditorText(`\n${item.build(selected || item.placeholder)}`);
            markDirty();
        });
    }

    window.RewrzEditorBlockDirectives = { DIRECTIVES, hasDirective, decoratePreviewHtml, init };
})();
