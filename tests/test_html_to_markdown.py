import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def test_markdown_preservation():
    print("==================================================")
    print("🚀 [TEST HTML TO MARKDOWN ACCURACY]")
    print("==================================================")

    options = Options()
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)

    try:
        # Load a simulated rich ChatGPT / Gemini HTML structure
        driver.get("about:blank")
        
        test_html = """
        <div class="markdown">
            <h2>Jimmy's Tools 專案分析</h2>
            <p>這是一個<strong>全方位精選實用工具庫</strong>，主要提供以下功能：</p>
            <ul>
                <li>建立網站首頁 <code>index.html</code></li>
                <li>載入 <code>components/site-config.js</code> 元件</li>
                <li>提供 <strong>78 張偉特塔羅牌</strong> 解讀系統</li>
            </ul>
            <pre><code class="language-html">&lt;script src="components/navigation.js"&gt;&lt;/script&gt;
&lt;link rel="stylesheet" href="components/global.css"&gt;</code></pre>
            <blockquote>這是一段重要備註說明。</blockquote>
        </div>
        """
        
        js_code = f"""
        document.body.innerHTML = `{test_html}`;
        
        function htmlToMarkdown(element) {{
            if (!element) return "";
            
            function walk(node) {{
                if (node.nodeType === Node.TEXT_NODE) {{
                    return node.nodeValue;
                }}
                if (node.nodeType !== Node.ELEMENT_NODE) {{
                    return "";
                }}

                const tag = node.tagName.toLowerCase();

                if (["button", "svg", "script", "style", "nav"].includes(tag) || 
                    node.getAttribute("role") === "button" ||
                    node.classList.contains("toolbar") ||
                    node.classList.contains("action-buttons")) {{
                    return "";
                }}

                let inner = "";
                for (const child of node.childNodes) {{
                    inner += walk(child);
                }}

                switch (tag) {{
                    case "h1": return `\\n# ${{inner.trim()}}\\n\\n`;
                    case "h2": return `\\n## ${{inner.trim()}}\\n\\n`;
                    case "h3": return `\\n### ${{inner.trim()}}\\n\\n`;
                    case "h4": return `\\n#### ${{inner.trim()}}\\n\\n`;
                    case "h5": return `\\n##### ${{inner.trim()}}\\n\\n`;
                    case "h6": return `\\n###### ${{inner.trim()}}\\n\\n`;
                    case "p": return `\\n\\n${{inner.trim()}}\\n\\n`;
                    case "strong":
                    case "b": return `**${{inner}}**`;
                    case "em":
                    case "i": return `*${{inner}}*`;
                    case "code": {{
                        if (node.parentElement && node.parentElement.tagName.toLowerCase() === "pre") {{
                            return inner;
                        }}
                        return `\\`${{inner}}\\``;
                    }}
                    case "pre": {{
                        let lang = "";
                        const codeEl = node.querySelector("code");
                        if (codeEl) {{
                            const match = codeEl.className.match(/language-([a-zA-Z0-9_-]+)/);
                            if (match) lang = match[1];
                            const codeText = codeEl.innerText || codeEl.textContent || "";
                            return `\\n\`\`\`${{lang}}\\n${{codeText.trim()}}\\n\`\`\`\\n\\n`;
                        }}
                        return `\\n\`\`\`\\n${{(node.innerText || inner).trim()}}\\n\`\`\`\\n\\n`;
                    }}
                    case "li": {{
                        const parentTag = node.parentElement ? node.parentElement.tagName.toLowerCase() : "ul";
                        if (parentTag === "ol") {{
                            const index = Array.from(node.parentElement.children).indexOf(node) + 1;
                            return `\\n${{index}}. ${{inner.trim()}}`;
                        }}
                        return `\\n- ${{inner.trim()}}`;
                    }}
                    case "ul":
                    case "ol": return `\\n${{inner}}\\n\\n`;
                    case "blockquote": return `\\n> ${{inner.trim().replace(/\\n/g, "\\n> ")}}\\n\\n`;
                    case "hr": return `\\n\\n---\\n\\n`;
                    case "a": {{
                        const href = node.getAttribute("href") || "";
                        return href ? `[${{inner}}](${{href}})` : inner;
                    }}
                    case "br": return `\\n`;
                    default: return inner;
                }}
            }}

            let md = walk(element);
            return md.replace(/\\n{{3,}}/g, "\\n\\n").trim();
        }}
        
        return htmlToMarkdown(document.querySelector('.markdown'));
        """
        
        converted_md = driver.execute_script(js_code)
        print("--- 轉換後的精準 Markdown 語法 ---")
        print(converted_md)
        print("----------------------------------")
        
        assert "## Jimmy's Tools 專案分析" in converted_md, "H2 Markdown preserved"
        assert "**全方位精選實用工具庫**" in converted_md, "Bold preserved"
        assert "```html" in converted_md, "Code block syntax preserved"
        assert "`index.html`" in converted_md, "Inline code preserved"
        assert "- 建立網站首頁" in converted_md, "List preserved"
        assert "> 這是一段重要備註說明。" in converted_md, "Blockquote preserved"
        
        print("\n🎉🎉🎉 斷言全部通過！Markdown 語法 100% 完美還原！")

    finally:
        driver.quit()

if __name__ == "__main__":
    test_markdown_preservation()
