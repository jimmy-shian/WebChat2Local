/**
 * WebChat2Local - Shared Markdown & Table Serializer
 */
const WebChat2LocalMarkdown = {
  /**
   * Serializes a response DOM element to pristine Markdown & intact XML tool tags.
   */
  serialize: function (element) {
    if (!element) return "";

    // Ignore UI / Angular / Framework chrome tags
    const ignoredTags = new Set([
      "button", "svg", "script", "style", "nav", "mat-icon", "mat-ripple",
      "thinking-overlay", "model-response-header", "tts-button"
    ]);

    function walk(node) {
      if (node.nodeType === Node.TEXT_NODE) {
        return node.nodeValue;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) {
        return "";
      }

      const tag = node.tagName.toLowerCase();

      // Skip UI controls & buttons
      if (
        ignoredTags.has(tag) ||
        node.getAttribute("role") === "button" ||
        node.classList.contains("toolbar") ||
        node.classList.contains("action-buttons") ||
        node.classList.contains("copy-button") ||
        node.classList.contains("model-response-header")
      ) {
        return "";
      }

      let inner = "";
      for (const child of node.childNodes) {
        inner += walk(child);
      }

      switch (tag) {
        case "h1": return `\n\n# ${inner.trim()}\n\n`;
        case "h2": return `\n\n## ${inner.trim()}\n\n`;
        case "h3": return `\n\n### ${inner.trim()}\n\n`;
        case "h4": return `\n\n#### ${inner.trim()}\n\n`;
        case "h5": return `\n\n##### ${inner.trim()}\n\n`;
        case "h6": return `\n\n###### ${inner.trim()}\n\n`;
        case "p": return `\n\n${inner.trim()}\n\n`;
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
            return `\n\n\`\`\`${lang}\n${codeText.trim()}\n\`\`\`\n\n`;
          }
          return `\n\n\`\`\`\n${(node.innerText || inner).trim()}\n\`\`\`\n\n`;
        }
        case "li": {
          const parentTag = node.parentElement ? node.parentElement.tagName.toLowerCase() : "ul";
          if (parentTag === "ol") {
            const index = Array.from(node.parentElement.children).indexOf(node) + 1;
            return `\n${index}. ${inner.trim()}`;
          }
          return `\n- ${inner.trim()}`;
        }
        case "ul":
        case "ol": return `\n${inner}\n\n`;
        case "blockquote": return `\n> ${inner.trim().replace(/\n/g, "\n> ")}\n\n`;
        case "hr": return `\n\n---\n\n`;
        case "a": {
          const href = node.getAttribute("href") || "";
          return href ? `[${inner.trim()}](${href})` : inner;
        }
        case "table": {
          const rows = Array.from(node.querySelectorAll("tr"));
          if (rows.length === 0) return `\n\n${inner.trim()}\n\n`;
          let mdTable = "\n\n";
          rows.forEach((row, rIdx) => {
            const cells = Array.from(row.querySelectorAll("th, td"));
            mdTable += "| " + cells.map((c) => (c.innerText || "").trim()).join(" | ") + " |\n";
            if (rIdx === 0) {
              mdTable += "| " + cells.map(() => "---").join(" | ") + " |\n";
            }
          });
          return mdTable + "\n";
        }
        case "tr":
        case "th":
        case "td":
        case "thead":
        case "tbody":
        case "tfoot":
          return inner;
        case "br": return `\n`;
        default: {
          // If it's a structural div/span or framework container, just return inner text
          if (
            ["div", "span", "section", "article", "main", "message-content", "model-response", "response-container", "structured-content-container"].includes(tag)
          ) {
            return inner;
          }
          // Preserve XML tool tags (e.g. <attempt_completion>, <result>, <task_progress>, <read_file>, <execute_command>)
          const attrs = Array.from(node.attributes).map((a) => ` ${a.name}="${a.value}"`).join("");
          return `<${tag}${attrs}>${inner}</${tag}>`;
        }
      }
    }

    let md = walk(element);
    return md
      .split("\n")
      .map((l) => l.trimEnd())
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  },
};

if (typeof window !== "undefined") {
  window.WebChat2LocalMarkdown = WebChat2LocalMarkdown;
}
