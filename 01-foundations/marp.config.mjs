// Marp engine with Mermaid support.
// Usage:
//   npx marp --config ./01-foundations/marp.config.mjs 01-foundations/workshop.md -o workshop.html
//
// Requires: npm i -D @marp-team/marp-cli markdown-it-mermaid-plugin

import { Marp } from '@marp-team/marp-core'
import markdownItMermaid from 'markdown-it-mermaid-plugin'

export default {
  // Inject mermaid.js into the HTML so diagrams render in the browser.
  html: true,
  engine: (opts) =>
    new Marp(opts).use(markdownItMermaid, {
      // Mermaid init options
      theme: 'dark',
      themeVariables: {
        darkMode: true,
        background: '#0f1115',
        primaryColor: '#151821',
        primaryTextColor: '#e7e9ee',
        primaryBorderColor: '#ffb454',
        lineColor: '#7cd1ff',
        secondaryColor: '#2a2f3a',
        tertiaryColor: '#0b0d12',
      },
    }),
}
