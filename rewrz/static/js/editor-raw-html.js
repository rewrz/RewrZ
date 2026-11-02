(() => {
    'use strict';

    // Toast UI 的富文本模式只认识有限的内置节点，直接粘贴或导入的原始 HTML
    // （视频、音频、嵌入卡片等）在模式切换时会被整段丢弃。
    // 这里统一把“整块的原始 HTML”包进带标记的容器，让富文本按 HTML 块保留；
    // 取回正文或切回 Markdown 时再拆掉容器，避免逐标签打补丁。
    const WRAP_ATTR = 'data-rewrz-raw-html';
    const SOURCE_ATTR = 'data-rewrz-raw-html-source';
    const WRAP_OPEN = `<div ${WRAP_ATTR}="1"`;
    const FENCE_DETECT_PATTERN = /^\s*(`{3,}|~{3,})/;
    const INDENTED_CODE_PATTERN = /^(?: {4}|\t)/;
    const AUTOLINK_PATTERN = /^<(?:[^<>\s]+:[^<>\s]+|[^<>\s@]+@[^<>\s@]+)>$/;

    function isRawHtmlLine(line) {
        const trimmed = String(line || '').trimStart();
        if (!trimmed.startsWith('<')) return false;
        if (INDENTED_CODE_PATTERN.test(line)) return false;
        if (trimmed.startsWith(`<div ${WRAP_ATTR}`)) return false;
        if (AUTOLINK_PATTERN.test(trimmed)) return false;
        return /^<(?:[A-Za-z!/?])/.test(trimmed);
    }

    function updateFenceState(line, state) {
        const match = String(line || '').match(FENCE_DETECT_PATTERN);
        if (!match) return state;
        const marker = match[1];
        if (!state) return { char: marker[0], length: marker.length };
        if (marker[0] === state.char && marker.length >= state.length) return null;
        return state;
    }

    function encodeSource(raw) {
        try {
            const bytes = new TextEncoder().encode(raw);
            let binary = '';
            bytes.forEach((byte) => {
                binary += String.fromCharCode(byte);
            });
            return btoa(binary);
        } catch (error) {
            return '';
        }
    }

    function decodeSource(value) {
        try {
            const binary = atob(value);
            const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
            return new TextDecoder().decode(bytes);
        } catch (error) {
            return '';
        }
    }

    /**
     * 把 Markdown 中的整块原始 HTML 包成可被富文本保留的容器。
     * 只处理行首开始、且不在代码块内的 HTML，避免误伤代码示例与自动链接。
     */
    function protect(markdown) {
        const lines = String(markdown ?? '').split('\n');
        const output = [];
        let buffer = [];
        let fenceState = null;

        const flush = () => {
            if (!buffer.length) return;
            const raw = buffer.join('\n');
            const encoded = encodeSource(raw);
            const sourceAttr = encoded ? ` ${SOURCE_ATTR}="${encoded}"` : '';
            output.push(`${WRAP_OPEN}${sourceAttr}>${raw}</div>`);
            buffer = [];
        };

        lines.forEach((line) => {
            const nextFence = updateFenceState(line, fenceState);
            if (fenceState || nextFence?.char) {
                flush();
                output.push(line);
                fenceState = nextFence;
                return;
            }
            if (isRawHtmlLine(line)) {
                buffer.push(line);
                return;
            }
            flush();
            output.push(line);
        });
        flush();
        return output.join('\n');
    }

    /**
     * 拆掉保护容器，只保留内部原始 HTML。
     * 通过标记属性定位容器，并按 div 嵌套层级找闭合标签，容器被编辑过也能处理。
     */
    function unwrap(text) {
        const source = String(text ?? '');
        if (!source.includes(WRAP_ATTR)) return source;

        const openTagPattern = /<div\b[^>]*>/gi;
        const divTagPattern = /<\/?div\b[^>]*>/gi;
        let result = '';
        let lastIndex = 0;
        let openMatch;

        while ((openMatch = openTagPattern.exec(source))) {
            const openTag = openMatch[0];
            if (!openTag.includes(WRAP_ATTR)) continue;

            let depth = 1;
            let closeStart = -1;
            let closeEnd = -1;
            divTagPattern.lastIndex = openTagPattern.lastIndex;
            let tagMatch;
            while ((tagMatch = divTagPattern.exec(source))) {
                if (/^<\/div/i.test(tagMatch[0])) {
                    depth -= 1;
                    if (depth === 0) {
                        closeStart = tagMatch.index;
                        closeEnd = divTagPattern.lastIndex;
                        break;
                    }
                } else if (!/\/>\s*$/.test(tagMatch[0])) {
                    depth += 1;
                }
            }
            if (closeEnd < 0) break;

            // 优先使用容器上保存的原始源码，避免富文本解析改写了嵌套标签
            const sourceMatch = openTag.match(new RegExp(`${SOURCE_ATTR}="([^"]*)"`));
            const decoded = sourceMatch ? decodeSource(sourceMatch[1]) : '';
            const inner = source.slice(openTagPattern.lastIndex, closeStart);
            result += source.slice(lastIndex, openMatch.index) + (decoded || inner);
            lastIndex = closeEnd;
            openTagPattern.lastIndex = closeEnd;
        }

        return result + source.slice(lastIndex);
    }

    function hasWrapper(text) {
        return String(text ?? '').includes(WRAP_ATTR);
    }

    /**
     * Toast UI 自定义 HTML 块渲染器：只注册 div 一个节点，
     * 让保护容器（以及正文里原有的 div 原始 HTML）在富文本中原样保留。
     */
    function createDivHtmlBlockRenderer() {
        return function (node) {
            const tagName = (node && node.type) || 'div';
            return [
                { type: 'openTag', tagName, outerNewLine: true, attributes: (node && node.attrs) || {} },
                { type: 'html', content: (node && node.childrenHTML) || '' },
                { type: 'closeTag', tagName, outerNewLine: true },
            ];
        };
    }

    window.RewrzEditorRawHtml = { protect, unwrap, hasWrapper, createDivHtmlBlockRenderer };
})();
