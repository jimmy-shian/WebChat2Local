import json
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def test_xml_and_table_preservation():
    print("==================================================")
    print("🚀 [TEST PRESERVING XML TOOL TAGS & TABLES]")
    print("==================================================")

    options = Options()
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get("about:blank")
        
        test_html = """
        <div class="markdown">
            <attempt_completion>
                <result>
                    <p>index.html 是本專案的入口首頁：</p>
                    <table>
                        <thead>
                            <tr><th>分類</th><th>工具名稱</th><th>核心功能</th></tr>
                        </thead>
                        <tbody>
                            <tr><td>🔮 塔羅占卜</td><td>偉特塔羅</td><td>78張牌組解讀</td></tr>
                            <tr><td>⏱️ 時間工具</td><td>高精度計時器</td><td>番茄鐘與秒錶</td></tr>
                        </tbody>
                    </table>
                </result>
                <task_progress>
                    <ul>
                        <li>[x] 分析 index.html 檔案結構</li>
                        <li>[x] 彙整專案架構</li>
                    </ul>
                </task_progress>
            </attempt_completion>
        </div>
        """

        driver.execute_script(f"document.body.innerHTML = {json.dumps(test_html)};")

        js_code = """
        function robustHtmlToMarkdown(element) {
            if (!element) return "";

            const standardHtmlTags = new Set([
                "div", "span", "p", "article", "section", "main", "header", "footer",
                "h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "em", "i", "u",
                "ul", "ol", "li", "pre", "code", "blockquote", "hr", "br", "a",
                "table", "thead", "tbody", "tfoot", "tr", "th", "td",
                "button", "svg", "path", "g", "style", "script", "nav"
            ]);

            function walk(node) {
                if (node.nodeType === Node.TEXT_NODE) {
                    return node.nodeValue;
                }
                if (node.nodeType !== Node.ELEMENT_NODE) {
                    return "";
                }

                const tag = node.tagName.toLowerCase();

                if (["button", "svg", "script", "style", "nav"].includes(tag) || 
                    node.getAttribute("role") === "button" ||
                    node.classList.contains("toolbar") ||
                    node.classList.contains("action-buttons")) {
                    return "";
                }

                let inner = "";
                for (const child of node.childNodes) {
                    inner += walk(child);
                }

                switch (tag) {
                    case "h1": return `\\n\\n# ${inner.trim()}\\n\\n`;
                    case "h2": return `\\n\\n## ${inner.trim()}\\n\\n`;
                    case "h3": return `\\n\\n### ${inner.trim()}\\n\\n`;
                    case "h4": return `\\n\\n#### ${inner.trim()}\\n\\n`;
                    case "h5": return `\\n\\n##### ${inner.trim()}\\n\\n`;
                    case "h6": return `\\n\\n###### ${inner.trim()}\\n\\n`;
                    case "p": return `\\n\\n${inner.trim()}\\n\\n`;
                    case "strong":
                    case "b": return `**${inner.trim()}**`;
                    case "em":
                    case "i": return `*${inner.trim()}*`;
                    case "code": {
                        if (node.parentElement && node.parentElement.tagName.toLowerCase() === "pre") {
                            return inner;
                        }
                        return `\`${inner.trim()}\``;
                    }
                    case "pre": {
                        let lang = "";
                        const codeEl = node.querySelector("code");
                        if (codeEl) {
                            const match = codeEl.className.match(/language-([a-zA-Z0-9_-]+)/);
                            if (match) lang = match[1];
                            const codeText = codeEl.innerText || codeEl.textContent || "";
                            return `\\n\\n\`\`\`${lang}\\n${codeText.trim()}\\n\`\`\`\\n\\n`;
                        }
                        return `\\n\\n\`\`\`\\n${(node.innerText || inner).trim()}\\n\`\`\`\\n\\n`;
                    }
                    case "li": {
                        const parentTag = node.parentElement ? node.parentElement.tagName.toLowerCase() : "ul";
                        if (parentTag === "ol") {
                            const index = Array.from(node.parentElement.children).indexOf(node) + 1;
                            return `\\n${index}. ${inner.trim()}`;
                        }
                        return `\\n- ${inner.trim()}`;
                    }
                    case "ul":
                    case "ol": return `\\n${inner}\\n\\n`;
                    case "blockquote": return `\\n> ${inner.trim().replace(/\\n/g, "\\n> ")}\\n\\n`;
                    case "hr": return `\\n\\n---\\n\\n`;
                    case "a": {
                        const href = node.getAttribute("href") || "";
                        return href ? `[${inner.trim()}](${href})` : inner;
                    }
                    case "table": {
                        const rows = Array.from(node.querySelectorAll("tr"));
                        if (rows.length === 0) return `\\n\\n${inner.trim()}\\n\\n`;
                        let mdTable = "\\n\\n";
                        rows.forEach((row, rIdx) => {
                            const cells = Array.from(row.querySelectorAll("th, td"));
                            mdTable += "| " + cells.map(c => c.innerText.trim()).join(" | ") + " |\\n";
                            if (rIdx === 0) {
                                mdTable += "| " + cells.map(() => "---").join(" | ") + " |\\n";
                            }
                        });
                        return mdTable + "\\n";
                    }
                    case "tr":
                    case "th":
                    case "td":
                    case "thead":
                    case "tbody":
                    case "tfoot":
                        return inner;
                    case "br": return `\\n`;
                    default: {
                        if (!standardHtmlTags.has(tag)) {
                            const attrs = Array.from(node.attributes).map(a => ` ${a.name}="${a.value}"`).join("");
                            return `<${tag}${attrs}>${inner}</${tag}>`;
                        }
                        return inner;
                    }
                }
            }

            let md = walk(element);
            return md.split("\\n").map(l => l.trimEnd()).join("\\n").replace(/\\n{3,}/g, "\\n\\n").trim();
        }

        return robustHtmlToMarkdown(document.querySelector('.markdown'));
        """

        result_md = driver.execute_script(js_code)
        print("--- 產生的完整 XML 標籤與 Markdown 表格 ---")
        print(result_md)
        print("------------------------------------------")

        assert "<attempt_completion>" in result_md, "attempt_completion preserved"
        assert "<result>" in result_md, "result tag preserved"
        assert "</result>" in result_md, "closing result tag preserved"
        assert "<task_progress>" in result_md, "task_progress tag preserved"
        assert "| 分類 | 工具名稱 | 核心功能 |" in result_md, "Markdown table header preserved"
        assert "| --- | --- | --- |" in result_md, "Markdown table divider preserved"
        assert "| 🔮 塔羅占卜 | 偉特塔羅 | 78張牌組解讀 |" in result_md, "Markdown table row preserved"

        print("\n🎉🎉🎉 斷言全部通過！<attempt_completion><result> 標籤與 Markdown 表格 100% 完美保留！")

    finally:
        driver.quit()

if __name__ == "__main__":
    test_xml_and_table_preservation()
