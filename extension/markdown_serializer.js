/**
 * Gemini Web Markdown Serializer
 * Converts Google Gemini Web DOM nodes into clean Github-Flavored Markdown.
 */

const GeminiMarkdownSerializer = {
  serialize: function (rootElement) {
    if (!rootElement) return "";
    return this._traverse(rootElement).trim();
  },

  _traverse: function (node) {
    if (!node) return "";

    // 1. Text node
    if (node.nodeType === Node.TEXT_NODE) {
      return node.nodeValue;
    }

    // 2. Ignore hidden elements or specific action buttons
    if (node.nodeType === Node.ELEMENT_NODE) {
      const tag = node.tagName.toLowerCase();
      const className = node.className || "";

      // Ignore buttons, copy icons, citations footer, and thought blocks
      if (tag === "button" || tag === "svg" || tag === "mat-icon" || tag === "expandable-thought" || tag === "source-citation") return "";
      if (typeof className === "string" && (
        className.includes("response-action") ||
        className.includes("copy-button") ||
        className.includes("cdk-visually-hidden") ||
        className.includes("thought-container") ||
        className.includes("thinking-content") ||
        className.includes("thinking-process") ||
        className.includes("sources-list") ||
        className.includes("citation")
      )) {
        return "";
      }

      // Handle Code Blocks (<pre>, <code>)
      if (tag === "pre") {
        const codeEl = node.querySelector("code") || node;
        let lang = "";
        const codeClass = codeEl.className || "";
        const match = codeClass.match(/language-([a-zA-Z0-9_-]+)/);
        if (match) {
          lang = match[1];
        } else {
          lang = node.getAttribute("data-language") || "";
        }
        const rawCode = codeEl.innerText || node.innerText || "";
        return `\n\`\`\`${lang}\n${rawCode.trim()}\n\`\`\`\n\n`;
      }

      // Handle inline code
      if (tag === "code") {
        return `\`${node.innerText}\``;
      }

      // Headings
      if (/^h[1-6]$/.test(tag)) {
        const level = parseInt(tag[1], 10);
        const prefix = "#".repeat(level);
        return `\n\n${prefix} ${this._getChildrenText(node)}\n\n`;
      }

      // Paragraphs
      if (tag === "p") {
        return `\n\n${this._getChildrenText(node)}\n\n`;
      }

      // Line breaks
      if (tag === "br") {
        return "\n";
      }

      // Bold & Italic
      if (tag === "strong" || tag === "b") {
        return `**${this._getChildrenText(node)}**`;
      }
      if (tag === "em" || tag === "i") {
        return `*${this._getChildrenText(node)}*`;
      }
      if (tag === "del" || tag === "s") {
        return `~~${this._getChildrenText(node)}~~`;
      }

      // Blockquote
      if (tag === "blockquote") {
        const inner = this._getChildrenText(node).trim();
        const quoted = inner.split("\n").map(l => `> ${l}`).join("\n");
        return `\n\n${quoted}\n\n`;
      }

      // Lists (ul, ol)
      if (tag === "ul") {
        return `\n${this._serializeList(node, false)}\n`;
      }
      if (tag === "ol") {
        return `\n${this._serializeList(node, true)}\n`;
      }

      // Tables
      if (tag === "table") {
        return `\n\n${this._serializeTable(node)}\n\n`;
      }

      // Links
      if (tag === "a") {
        const href = node.getAttribute("href") || "#";
        const text = this._getChildrenText(node) || href;
        return `[${text}](${href})`;
      }

      // Default: traverse children
      return this._getChildrenText(node);
    }

    return "";
  },

  _getChildrenText: function (node) {
    let result = "";
    for (const child of node.childNodes) {
      result += this._traverse(child);
    }
    return result;
  },

  _serializeList: function (listNode, isOrdered) {
    let output = "";
    let index = 1;
    for (const child of listNode.childNodes) {
      if (child.nodeType === Node.ELEMENT_NODE && child.tagName.toLowerCase() === "li") {
        const prefix = isOrdered ? `${index++}. ` : "- ";
        const itemText = this._getChildrenText(child).trim();
        output += `${prefix}${itemText}\n`;
      }
    }
    return output;
  },

  _serializeTable: function (tableNode) {
    const rows = Array.from(tableNode.querySelectorAll("tr"));
    if (rows.length === 0) return "";

    let tableMd = "";
    let headerHandled = false;

    for (let r = 0; r < rows.length; r++) {
      const row = rows[r];
      const cells = Array.from(row.querySelectorAll("th, td"));
      const cellTexts = cells.map(c => this._getChildrenText(c).trim().replace(/\|/g, "\\|"));

      tableMd += `| ${cellTexts.join(" | ")} |\n`;

      if (!headerHandled && (row.querySelector("th") || r === 0)) {
        const separators = cells.map(() => "---");
        tableMd += `| ${separators.join(" | ")} |\n`;
        headerHandled = true;
      }
    }

    return tableMd;
  }
};

if (typeof window !== "undefined") {
  window.GeminiMarkdownSerializer = GeminiMarkdownSerializer;
}
