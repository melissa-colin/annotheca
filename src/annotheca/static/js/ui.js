/**
 * @fileoverview Small DOM helpers: element builder, icons, toasts, dialogs.
 */

import {api} from './api.js';
import {hasMessage, t} from './i18n.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const TOAST_DURATION_MS = 4500;
const NOTES_SAVE_DELAY_MS = 600;

/** Stroke paths of the 24×24 icons. */
const ICONS = {
  arrowLeft: 'M19 12H5M11 6l-6 6 6 6',
  book: 'M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5zM5 19.5' +
      'A1.5 1.5 0 0 0 6.5 21H19M9 7h6',
  download: 'M12 4v11M7 10l5 5 5-5M5 20h14',
  file: 'M6 3h8l4 4v14H6zM14 3v4h4',
  folderPlus: 'M3 6h6l2 2h10v11H3zM12 11v6M9 14h6',
  highlighter: 'M14 5l5 5-7 7H7v-5zM7 17l-3 3h5',
  minus: 'M5 12h14',
  note: 'M5 4h14v10l-5 6H5zM14 20v-6h5',
  pencil: 'M4 20h4L19 9l-4-4L4 16zM13 7l4 4',
  plus: 'M12 5v14M5 12h14',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 1 0 0-14M20 20l-4-4',
  share: 'M12 15V4M8 8l4-4 4 4M5 13v7h14v-7',
  trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  upload: 'M12 16V5M7 10l5-5 5 5M5 20h14',
  x: 'M6 6l12 12M18 6L6 18',
};

/**
 * Creates an element.
 * @param {string} tag Tag name followed by classes, e.g. 'button.chip.small'.
 * @param {!Object=} props Properties to set. Keys starting with 'on' add
 *     listeners; 'dataset' and 'style' take objects, style keys may be custom
 *     properties such as '--color'.
 * @param {...*} children Nodes or strings; nullish and false are skipped and
 *     arrays are flattened.
 * @return {!HTMLElement}
 */
export function h(tag, props = {}, ...children) {
  const [name, ...classes] = tag.split('.');
  const el = document.createElement(name);
  el.classList.add(...classes);
  for (const [key, value] of Object.entries(props)) {
    if (key.startsWith('on')) {
      el.addEventListener(key.slice(2), value);
    } else if (key === 'dataset') {
      Object.assign(el.dataset, value);
    } else if (key === 'style') {
      for (const [property, v] of Object.entries(value)) {
        el.style.setProperty(property, v);
      }
    } else if (key in el) {
      el[key] = value;
    } else {
      el.setAttribute(key, value);
    }
  }
  el.append(...children.flat().filter((c) => c != null && c !== false));
  return el;
}

/**
 * @param {string} name A key of ICONS.
 * @return {!SVGElement}
 */
export function icon(name) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.classList.add('icon');
  const path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('d', ICONS[name]);
  svg.append(path);
  return svg;
}

/**
 * Creates a textarea for the general notes of a placement, saved as the user
 * pauses typing and when it loses focus.
 * @param {!Object} placement Its `notes` field is kept up to date.
 * @param {string=} className Extra classes, e.g. '.compact'.
 * @return {!HTMLTextAreaElement}
 */
export function notesEditor(placement, className = '') {
  let timer;
  const save = () => {
    clearTimeout(timer);
    if (textarea.value === placement.notes) return;
    placement.notes = textarea.value;
    api.setNotes(placement.id, placement.notes).catch(report);
  };
  const textarea = h(`textarea.notes${className}`, {
    value: placement.notes,
    placeholder: t('notes.placeholder'),
    oninput: () => {
      clearTimeout(timer);
      timer = setTimeout(save, NOTES_SAVE_DELAY_MS);
    },
    onblur: save,
  });
  return textarea;
}

/**
 * Shows a transient message.
 * @param {string} message
 * @param {string=} kind 'info' or 'error'.
 */
export function toast(message, kind = 'info') {
  const el = h(`div.toast.${kind}`, {role: 'status'}, message);
  document.getElementById('toasts').append(el);
  setTimeout(() => el.remove(), TOAST_DURATION_MS);
}

/**
 * Shows an error raised by the API in the user's language.
 * @param {!Error} error
 */
export function report(error) {
  const key = `error.${error.message}`;
  toast(t(hasMessage(key) ? key : 'error.generic'), 'error');
  console.error(error);
}

/**
 * Asks for a confirmation, or for a name when `value` is given.
 * @param {{title: string, message: (string|undefined),
 *     value: (string|undefined), action: string, danger: (boolean|undefined)}}
 *     options
 * @return {!Promise<(string|boolean|null)>} The entered name, true for a
 *     confirmation, or null when cancelled.
 */
export function ask({title, message, value, action, danger = false}) {
  const dialog = document.getElementById('dialog');
  const input = value === undefined ? null : h('input.input', {
    value, maxLength: 80, required: true, placeholder: t('name'),
  });
  dialog.replaceChildren(h('form', {method: 'dialog'},
      h('h2', {}, title),
      message && h('p', {}, message),
      input,
      h('div.dialog-actions', {},
          h('button.button.ghost', {value: 'cancel', formNoValidate: true},
              t('cancel')),
          h(`button.button.${danger ? 'danger' : 'primary'}`, {value: 'ok'},
              action))));
  dialog.returnValue = '';
  dialog.showModal();
  input?.select();
  return new Promise((resolve) => {
    dialog.addEventListener('close', () => {
      if (dialog.returnValue !== 'ok') {
        resolve(null);
      } else {
        resolve(input ? input.value.trim() : true);
      }
    }, {once: true});
  });
}
