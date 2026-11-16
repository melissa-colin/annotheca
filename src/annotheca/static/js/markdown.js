/**
 * @fileoverview Renders journal text: Markdown, sanitized, where ```tikz code
 * blocks become diagrams compiled in the browser.
 */

import DOMPurify from '../vendor/dompurify/purify.es.mjs';
import {Marked} from '../vendor/marked/marked.esm.js';

import {t} from './i18n.js';
import {h} from './ui.js';

// TikZJax runs TeX in WebAssembly and replaces each <script type="text/tikz">
// with an SVG. It is GPL-licensed and large, so it is loaded from a CDN, and
// only once a diagram is shown.
const TIKZJAX_URL =
    'https://cdn.jsdelivr.net/npm/@drgrice1/tikzjax@1.0.0-beta24/dist/';
// Preamble lines that TikZJax needs as attributes rather than as code.
const TIKZ_PREAMBLE_RE =
    /^\s*\\(usetikzlibrary|usepackage)(?:\[([^\]]*)\])?\{([^}]*)\}\s*$/gm;
// TeX never answers when the code has an error, so a diagram still missing
// after this delay (which covers TikZJax's first download) is reported.
const TIKZ_TIMEOUT_MS = 90000;

const markdown = new Marked({gfm: true, breaks: true});
let tikzRequested = false;

/**
 * @param {string} source Markdown text, possibly written by an AI assistant
 *     or imported from someone else's project, hence sanitized.
 * @return {!DocumentFragment}
 */
export function renderMarkdown(source) {
  const template = document.createElement('template');
  template.innerHTML = DOMPurify.sanitize(markdown.parse(source));
  for (const link of template.content.querySelectorAll('a[href]')) {
    link.target = '_blank';
    link.rel = 'noopener';
  }
  for (const code of template.content.querySelectorAll('code.language-tikz')) {
    code.parentElement.replaceWith(tikzFigure(code.textContent));
  }
  return template.content;
}

/**
 * @param {string} source TikZ code: a tikzpicture, or its bare commands, with
 *     optional \usetikzlibrary and \usepackage lines.
 * @return {!HTMLElement} The diagram, with its source available below it.
 */
function tikzFigure(source) {
  const libraries = [];
  const packages = {};
  const body = source.replace(TIKZ_PREAMBLE_RE,
      (line, command, options, names) => {
        for (const name of names.split(',').map((n) => n.trim())) {
          if (command === 'usetikzlibrary') {
            libraries.push(name);
          } else {
            packages[name] = options ?? '';
          }
        }
        return '';
      }).trim();
  const details = h('details', {}, h('summary', {}, 'TikZ'),
      h('pre', {}, h('code', {}, source)));
  if (isMalformed(body)) {
    details.open = true;
    return h('figure.tikz', {},
        h('p.tikz-error', {}, t('journal.tikzError')), details);
  }
  const script = document.createElement('script');
  script.type = 'text/tikz';
  script.textContent = body.includes('\\begin{') ? body :
      `\\begin{tikzpicture}\n${body}\n\\end{tikzpicture}`;
  if (libraries.length) script.dataset.tikzLibraries = libraries.join(',');
  if (Object.keys(packages).length) {
    script.dataset.texPackages = JSON.stringify(packages);
  }
  loadTikzJax();
  const figure = h('figure.tikz', {}, script, details);
  const fail = () => {
    if (figure.querySelector('svg[role="img"]') || !figure.isConnected) return;
    figure.firstElementChild.replaceWith(
        h('p.tikz-error', {}, t('journal.tikzError')));
    details.open = true;
  };
  // On a failure TikZJax shows a broken image.
  figure.addEventListener('error', fail, true);
  setTimeout(fail, TIKZ_TIMEOUT_MS);
  return figure;
}

/**
 * Spots the TeX errors that make TikZJax hang, and with it every diagram
 * after it on the page: unbalanced braces or math, or a lone \begin or \end.
 * @param {string} code
 * @return {boolean}
 */
function isMalformed(code) {
  const text = code.replace(/(?<!\\)%.*$/gm, '').replace(/\\[{}$%]/g, '');
  let depth = 0;
  for (const char of text) {
    if (char === '{') depth++;
    if (char === '}' && --depth < 0) return true;
  }
  const count = (pattern) => (text.match(pattern) ?? []).length;
  return depth !== 0 || count(/\$/g) % 2 === 1 ||
      count(/\\begin\{/g) !== count(/\\end\{/g);
}

function loadTikzJax() {
  if (tikzRequested) return;
  tikzRequested = true;
  document.head.append(
      h('link', {rel: 'stylesheet', href: `${TIKZJAX_URL}fonts.css`}),
      h('script', {src: `${TIKZJAX_URL}tikzjax.js`}));
}
