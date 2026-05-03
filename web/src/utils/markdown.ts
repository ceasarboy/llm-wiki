import { marked } from 'marked'
import katex from 'katex'
import DOMPurify from 'dompurify'

marked.setOptions({
  breaks: true,
  gfm: true,
})

const BLOCK_MATH_REGEX = /\$\$([\s\S]+?)\$\$/g
const INLINE_MATH_REGEX = /(?<!\$)\$(?!\$)([^\$\n]+?)\$(?!\$)/g
const PLACEHOLDER_PREFIX = '\x00KATEX_'

const escapeHtml = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

export function renderMarkdown(text: string): string {
  let processedText = text
  const placeholders: Map<string, string> = new Map()
  let counter = 0

  processedText = processedText.replace(BLOCK_MATH_REGEX, (_, formula) => {
    const key = `${PLACEHOLDER_PREFIX}BLOCK_${counter++}\x00`
    try {
      const html = katex.renderToString(formula.trim(), { displayMode: true, throwOnError: false })
      placeholders.set(key, html)
    } catch {
      placeholders.set(key, `$$${formula}$$`)
    }
    return key
  })

  processedText = processedText.replace(INLINE_MATH_REGEX, (_, formula) => {
    const key = `${PLACEHOLDER_PREFIX}INLINE_${counter++}\x00`
    try {
      const html = katex.renderToString(formula.trim(), { displayMode: false, throwOnError: false })
      placeholders.set(key, html)
    } catch {
      placeholders.set(key, `$${formula}$`)
    }
    return key
  })

  processedText = processedText.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, path) => {
    if (path.startsWith('http://') || path.startsWith('https://')) {
      return `![${alt}](${path})`
    }
    const encodedPath = encodeURIComponent(path.replace(/\\/g, '/'))
    return `![${alt}](/api/assets?path=${encodedPath})`
  })

  processedText = processedText.replace(
    /\[Source: ([^\]]+)\]/g,
    (_, content) => `<span class="source-ref" style="color:var(--accent);cursor:pointer;font-size:0.8em;vertical-align:super;" title="来源 ${escapeHtml(content)}">[Source: ${escapeHtml(content)}]</span>`
  )

  processedText = processedText.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_, linkId, displayText) => {
    const cleanId = linkId.replace('.md', '').trim()
    const display = displayText || cleanId.split('/').pop() || cleanId
    return `<span class="wiki-link" data-link="${escapeHtml(cleanId)}" style="color:var(--accent);cursor:pointer;text-decoration:underline;">${escapeHtml(display)}</span>`
  })

  let html = marked.parse(processedText, { async: false }) as string

  html = html.replace(/<p>\s*<span class="wiki-link/g, '<span class="wiki-link')
  html = html.replace(/<\/span>\s*<\/p>/g, '</span>')

  for (const [key, value] of placeholders) {
    html = html.replace(key, value)
  }

  html = DOMPurify.sanitize(html, {
    ADD_TAGS: ['span'],
    ADD_ATTR: ['data-link', 'class', 'style'],
  })

  return html
}
