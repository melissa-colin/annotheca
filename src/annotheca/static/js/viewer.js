/**
 * @fileoverview PDF reader with highlights and sticky notes. Annotations
 * belong to a placement, i.e. to a paper as filed in one folder.
 *
 * Annotation geometry is stored as fractions of the page size, so it does not
 * depend on the zoom level: a highlight is a list of [x, y, width, height]
 * rectangles and a note is the [x, y] position of its top-left corner.
 */

import * as pdfjs from '../vendor/pdfjs/pdf.min.mjs';

import {api} from './api.js';
import {t} from './i18n.js';
import {h, icon, report} from './ui.js';

pdfjs.GlobalWorkerOptions.workerSrc =
    new URL('../vendor/pdfjs/pdf.worker.min.mjs', import.meta.url).href;

const COLORS = ['#ffd54f', '#a5d6a7', '#90caf9', '#f48fb1', '#ce93d8'];
const ZOOM_FACTOR = 1.2;
const MIN_SCALE = 0.5;
const MAX_SCALE = 3;
/** The initial zoom fits the page width, up to this scale. */
const MAX_FIT_SCALE = 1.5;
const SAVE_DELAY_MS = 600;
/** Notes are kept this far from the right and bottom edges of the page. */
const NOTE_MARGIN = 0.1;
/** Revealed annotations are shown this far below the top of the reader. */
const REVEAL_OFFSET_PX = 120;

/**
 * Merges the selection rectangles that sit on the same line.
 * @param {!Array<!Array<number>>} rects [x, y, width, height] rectangles.
 * @return {!Array<!Array<number>>}
 */
function mergeRects(rects) {
  const sorted = [...rects].sort((a, b) => a[1] - b[1] || a[0] - b[0]);
  const merged = [];
  for (const [x, y, width, height] of sorted) {
    const last = merged.at(-1);
    const sameLine = last && Math.abs(last[1] - y) < last[3] / 2;
    if (sameLine && x <= last[0] + last[2] + 0.01) {
      const right = Math.max(last[0] + last[2], x + width);
      const bottom = Math.max(last[1] + last[3], y + height);
      last[0] = Math.min(last[0], x);
      last[1] = Math.min(last[1], y);
      last[2] = right - last[0];
      last[3] = bottom - last[1];
    } else {
      merged.push([x, y, width, height]);
    }
  }
  return merged.map((rect) => rect.map((v) => Math.round(v * 1e4) / 1e4));
}

/**
 * @param {number} fraction
 * @return {string} The fraction as a CSS percentage.
 */
function percent(fraction) {
  return `${fraction * 100}%`;
}

/**
 * @param {number} value
 * @param {number} max
 * @return {number} The value clamped to [0, max].
 */
function clamp(value, max) {
  return Math.min(Math.max(value, 0), max);
}

/**
 * @param {!Object} annotation
 * @return {number} Vertical position of the annotation on its page.
 */
function annotationTop(annotation) {
  return annotation.kind === 'note' ?
      annotation.geometry[1] : annotation.geometry[0][1];
}

/** Full-screen reader for one placement. */
export class PaperViewer {
  /**
   * @param {!HTMLElement} root Element the reader fills.
   * @param {{placement: !Object, subtitle: string, onClose: function()}}
   *     options The placement to read, a subtitle shown under its title, and
   *     a callback run once the reader is closed.
   */
  constructor(root, {placement, subtitle, onClose}) {
    this.root = root;
    this.placement = placement;
    this.subtitle = subtitle;
    this.onClose = onClose;
    this.tool = 'highlight';
    this.color = COLORS[0];
    this.scale = 1;
    /** @type {?Object} pdf.js loading task, which owns the document. */
    this.loadingTask = null;
    /** @type {!Array<!Object>} pdf.js pages. */
    this.pdfPages = [];
    /** @type {!Array<!Object>} Page elements and their layers. */
    this.pages = [];
    /** @type {!Array<!Object>} */
    this.annotations = [];
    /**
     * Note edits waiting to be saved, by annotation id.
     * @type {!Map<number, {changes: !Object, save: function(), timer: number}>}
     */
    this.pendingSaves = new Map();
    this.popover = null;
    this.onKeyDown = (event) => this.handleKey(event);
    this.observer = null;
  }

  /** Shows the reader and loads the PDF and the annotations. */
  async open() {
    this.buildChrome();
    this.root.hidden = false;
    document.addEventListener('keydown', this.onKeyDown);
    this.loadingTask =
        pdfjs.getDocument({url: api.pdfUrl(this.placement.paper_id)});
    const [pdf, annotations] = await Promise.all([
      this.loadingTask.promise,
      api.listAnnotations(this.placement.id),
    ]);
    this.annotations = annotations;
    this.pdfPages = await Promise.all(Array.from(
        {length: pdf.numPages}, (_, i) => pdf.getPage(i + 1)));
    const pageWidth = this.pdfPages[0].getViewport({scale: 1}).width;
    const fit = (this.pagesEl.clientWidth - 64) / pageWidth;
    this.scale = Math.min(Math.max(fit, MIN_SCALE), MAX_FIT_SCALE);
    this.layoutPages();
  }

  /** Saves pending edits, hides the reader and releases the PDF. */
  close() {
    this.pendingSaves.forEach(({save}) => save());
    document.removeEventListener('keydown', this.onKeyDown);
    this.observer?.disconnect();
    this.loadingTask?.destroy();
    this.root.hidden = true;
    this.root.replaceChildren();
    this.onClose();
  }

  buildChrome() {
    this.pagesEl = h('div.viewer-pages', {
      // While selecting, the end-of-content block keeps the selection from
      // jumping to the end of the page when the pointer leaves the text.
      onpointerdown: (event) =>
        event.target.closest('.textLayer')?.classList.add('selecting'),
      onmouseup: () => this.highlightSelection(),
      onclick: (event) => this.handlePageClick(event),
    });
    this.listEl = h('div.annotation-list');
    this.zoomLabel = h('span.zoom-label');
    this.toolButtons = ['highlight', 'note'].map((tool) => h('button.tool', {
      dataset: {tool},
      onclick: () => this.setTool(tool),
    }, icon(tool === 'note' ? 'note' : 'highlighter'),
    h('span', {}, t(`viewer.${tool}`))));
    this.swatches = COLORS.map((color) => h('button.swatch', {
      style: {'--swatch': color},
      dataset: {color},
      ariaLabel: color,
      onclick: () => {
        this.color = color;
        this.syncToolbar();
      },
    }));
    const zoomButton = (direction) => h('button.icon-button', {
      title: t(direction > 0 ? 'viewer.zoomIn' : 'viewer.zoomOut'),
      onclick: () => this.zoom(direction),
    }, icon(direction > 0 ? 'plus' : 'minus'));

    this.root.replaceChildren(
        h('header.viewer-bar', {},
            h('button.button.ghost', {onclick: () => this.close()},
                icon('arrowLeft'), t('viewer.back')),
            h('div.viewer-title', {},
                h('strong', {}, this.placement.title),
                h('span', {}, this.subtitle)),
            h('div.tools', {}, this.toolButtons),
            h('div.swatches', {}, this.swatches),
            h('div.zoom', {}, zoomButton(-1), this.zoomLabel, zoomButton(1))),
        h('div.viewer-body', {},
            this.pagesEl,
            h('aside.viewer-side', {},
                h('h2', {}, t('viewer.annotations')), this.listEl)));
    this.syncToolbar();
  }

  syncToolbar() {
    for (const button of this.toolButtons) {
      button.classList.toggle('active', button.dataset.tool === this.tool);
    }
    for (const swatch of this.swatches) {
      swatch.classList.toggle('active', swatch.dataset.color === this.color);
    }
    this.pagesEl.classList.toggle('note-mode', this.tool === 'note');
    this.zoomLabel.textContent = `${Math.round(this.scale * 100)}%`;
  }

  /** @param {string} tool 'highlight' or 'note'. */
  setTool(tool) {
    this.tool = tool;
    this.syncToolbar();
  }

  /** @param {number} direction 1 to zoom in, -1 to zoom out. */
  zoom(direction) {
    const scale = this.scale * ZOOM_FACTOR ** direction;
    if (scale < MIN_SCALE || scale > MAX_SCALE) return;
    const position = this.pagesEl.scrollTop / this.pagesEl.scrollHeight;
    this.scale = scale;
    this.layoutPages();
    this.pagesEl.scrollTop = position * this.pagesEl.scrollHeight;
  }

  /** Creates the page placeholders; pages render when scrolled into view. */
  layoutPages() {
    this.observer?.disconnect();
    this.observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        this.observer.unobserve(entry.target);
        this.renderPage(this.pages[entry.target.dataset.page - 1]);
      }
    }, {root: this.pagesEl, rootMargin: '800px 0px'});

    this.pages = this.pdfPages.map((pdfPage, index) => {
      const viewport = pdfPage.getViewport({scale: this.scale});
      const highlightLayer = h('div.highlight-layer');
      const noteLayer = h('div.note-layer');
      const el = h('div.page', {
        dataset: {page: index + 1},
        style: {
          'width': `${viewport.width}px`,
          'height': `${viewport.height}px`,
          '--total-scale-factor': this.scale,
        },
      }, highlightLayer, noteLayer);
      this.observer.observe(el);
      return {number: index + 1, pdfPage, viewport, el, highlightLayer,
        noteLayer};
    });
    this.pagesEl.replaceChildren(...this.pages.map((page) => page.el));
    this.syncToolbar();
    this.drawAnnotations();
  }

  /**
   * Draws a page and its selectable text layer.
   * @param {!Object} page
   */
  async renderPage({pdfPage, viewport, el, noteLayer}) {
    const ratio = window.devicePixelRatio || 1;
    const canvas = h('canvas', {
      width: Math.floor(viewport.width * ratio),
      height: Math.floor(viewport.height * ratio),
    });
    const textLayer = h('div.textLayer');
    el.prepend(canvas);
    noteLayer.before(textLayer);
    try {
      await pdfPage.render({
        canvasContext: canvas.getContext('2d'),
        viewport,
        transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0],
      }).promise;
      await new pdfjs.TextLayer({
        textContentSource: pdfPage.streamTextContent(),
        container: textLayer,
        viewport,
      }).render();
      textLayer.append(h('div.endOfContent'));
    } catch (error) {
      // Zooming discards the pages being drawn; anything else is unexpected.
      if (error.name !== 'RenderingCancelledException') report(error);
    }
  }

  /**
   * @param {number} x Client x coordinate.
   * @param {number} y Client y coordinate.
   * @return {?{page: !Object, x: number, y: number}} The page under the
   *     point and the point's position on it, as fractions.
   */
  locate(x, y) {
    for (const page of this.pages) {
      const box = page.el.getBoundingClientRect();
      if (x >= box.left && x <= box.right && y >= box.top && y <= box.bottom) {
        return {
          page,
          x: (x - box.left) / box.width,
          y: (y - box.top) / box.height,
        };
      }
    }
    return null;
  }

  /** Turns the current text selection into one highlight per page. */
  highlightSelection() {
    for (const layer of this.pagesEl.querySelectorAll('.selecting')) {
      layer.classList.remove('selecting');
    }
    const selection = document.getSelection();
    if (this.tool !== 'highlight' || selection.isCollapsed ||
        !this.pagesEl.contains(selection.anchorNode)) {
      return;
    }
    const quote = selection.toString().replace(/\s+/g, ' ').trim();
    const rectsByPage = new Map();
    for (const rect of selection.getRangeAt(0).getClientRects()) {
      const hit = this.locate(
          rect.left + rect.width / 2, rect.top + rect.height / 2);
      if (!hit || rect.width < 1) continue;
      const box = hit.page.el.getBoundingClientRect();
      // Whole-page rectangles come from elements fully inside the range.
      if (rect.height > box.height / 10) continue;
      const rects = rectsByPage.get(hit.page) ?? [];
      rects.push([(rect.left - box.left) / box.width,
        (rect.top - box.top) / box.height,
        rect.width / box.width, rect.height / box.height]);
      rectsByPage.set(hit.page, rects);
    }
    selection.removeAllRanges();
    for (const [page, rects] of rectsByPage) {
      this.create({
        kind: 'highlight', page: page.number, color: this.color,
        geometry: mergeRects(rects), quote,
      });
    }
  }

  /**
   * Adds a note in note mode; otherwise opens the menu of a clicked
   * highlight.
   * @param {!MouseEvent} event
   */
  handlePageClick(event) {
    this.hidePopover();
    if (event.target.closest('.postit')) return;
    const hit = this.locate(event.clientX, event.clientY);
    if (!hit) return;
    if (this.tool === 'note') {
      this.create({
        kind: 'note', page: hit.page.number, color: this.color,
        geometry: [
          clamp(hit.x, 1 - NOTE_MARGIN), clamp(hit.y, 1 - NOTE_MARGIN)],
      });
      return;
    }
    const highlight = this.annotations.find((a) =>
      a.kind === 'highlight' && a.page === hit.page.number &&
      a.geometry.some(([x, y, width, height]) => hit.x >= x &&
          hit.x <= x + width && hit.y >= y && hit.y <= y + height));
    if (highlight && document.getSelection().isCollapsed) {
      this.showPopover(highlight, event.clientX, event.clientY);
    }
  }

  /** @param {!KeyboardEvent} event */
  handleKey(event) {
    if (event.key !== 'Escape') return;
    if (this.popover) {
      this.hidePopover();
    } else if (event.target.matches('textarea')) {
      event.target.blur();
    } else {
      this.close();
    }
  }

  /**
   * Shows a menu to recolor or delete a highlight.
   * @param {!Object} highlight
   * @param {number} x
   * @param {number} y
   */
  showPopover(highlight, x, y) {
    this.popover = h('div.popover', {style: {left: `${x}px`, top: `${y}px`}},
        COLORS.map((color) => h(`button.swatch${
          color === highlight.color ? '.active' : ''}`, {
          style: {'--swatch': color},
          ariaLabel: color,
          onclick: () => this.update(highlight, {color}),
        })),
        h('button.icon-button.danger', {
          title: t('delete'), onclick: () => this.remove(highlight),
        }, icon('trash')));
    this.root.append(this.popover);
  }

  hidePopover() {
    this.popover?.remove();
    this.popover = null;
  }

  /** Redraws every annotation on the pages and in the side list. */
  drawAnnotations() {
    for (const page of this.pages) {
      page.highlightLayer.replaceChildren();
      page.noteLayer.replaceChildren();
    }
    for (const annotation of this.annotations) {
      const page = this.pages[annotation.page - 1];
      if (!page) continue;
      if (annotation.kind === 'note') {
        page.noteLayer.append(this.noteElement(annotation));
      } else {
        page.highlightLayer.append(...annotation.geometry.map(
            ([x, y, width, height]) => h('div.highlight', {style: {
              'left': percent(x), 'top': percent(y),
              'width': percent(width), 'height': percent(height),
              '--color': annotation.color,
            }})));
      }
    }
    this.renderList();
  }

  /**
   * @param {!Object} note
   * @return {!HTMLElement} A draggable, editable sticky note.
   */
  noteElement(note) {
    const textarea = h('textarea', {
      value: note.body,
      placeholder: t('viewer.notePlaceholder'),
      oninput: () => {
        note.body = textarea.value;
        this.saveLater(note, {body: note.body});
      },
    });
    const el = h('div.postit', {
      dataset: {id: note.id},
      style: {
        'left': percent(note.geometry[0]),
        'top': percent(note.geometry[1]),
        '--color': note.color,
      },
    },
    h('div.postit-bar', {onpointerdown: (event) => this.drag(event, note, el)},
        h('span', {}, t('viewer.page', {n: note.page})),
        h('button.postit-delete', {
          title: t('delete'), onclick: () => this.remove(note),
        }, icon('x'))),
    textarea);
    return el;
  }

  /**
   * Moves a note with the pointer and saves its new position.
   * @param {!PointerEvent} event
   * @param {!Object} note
   * @param {!HTMLElement} el
   */
  drag(event, note, el) {
    if (event.target.closest('button')) return;
    event.preventDefault();
    const box = el.parentElement.getBoundingClientRect();
    const [startX, startY] = note.geometry;
    const move = (moveEvent) => {
      note.geometry = [
        clamp(startX + (moveEvent.clientX - event.clientX) / box.width,
            1 - NOTE_MARGIN),
        clamp(startY + (moveEvent.clientY - event.clientY) / box.height,
            1 - NOTE_MARGIN),
      ];
      el.style.left = percent(note.geometry[0]);
      el.style.top = percent(note.geometry[1]);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', () => {
      window.removeEventListener('pointermove', move);
      this.saveLater(note, {geometry: note.geometry});
    }, {once: true});
  }

  renderList() {
    const sorted = [...this.annotations].sort((a, b) =>
      a.page - b.page || annotationTop(a) - annotationTop(b));
    this.listEl.replaceChildren(...sorted.map((annotation) =>
      h('button.annotation-item', {
        style: {'--color': annotation.color},
        onclick: () => this.reveal(annotation),
      },
      h('span.annotation-meta', {},
          icon(annotation.kind === 'note' ? 'note' : 'highlighter'),
          t('viewer.page', {n: annotation.page})),
      h('span.annotation-text', {},
          (annotation.kind === 'note' ? annotation.body : annotation.quote) ||
          '…'))));
    if (!sorted.length) {
      this.listEl.append(h('p.muted', {}, t('viewer.empty')));
    }
  }

  /** @param {!Object} annotation Scrolls the annotation into view. */
  reveal(annotation) {
    const page = this.pages[annotation.page - 1];
    const top = annotationTop(annotation) * page.el.offsetHeight;
    this.pagesEl.scrollTo({
      top: page.el.offsetTop + top - REVEAL_OFFSET_PX,
      behavior: 'smooth',
    });
    if (annotation.kind === 'note') this.focusNote(annotation);
  }

  /** @param {!Object} note */
  focusNote(note) {
    this.pages[note.page - 1].noteLayer
        .querySelector(`[data-id="${note.id}"] textarea`)
        .focus({preventScroll: true});
  }

  /** @param {!Object} values A new annotation, focused if it is a note. */
  async create(values) {
    try {
      const annotation = await api.createAnnotation(this.placement.id, values);
      this.annotations.push(annotation);
      this.drawAnnotations();
      if (annotation.kind === 'note') this.focusNote(annotation);
    } catch (error) {
      report(error);
    }
  }

  /**
   * @param {!Object} annotation
   * @param {!Object} changes
   */
  async update(annotation, changes) {
    this.hidePopover();
    try {
      Object.assign(annotation,
          await api.updateAnnotation(annotation.id, changes));
      this.drawAnnotations();
    } catch (error) {
      report(error);
    }
  }

  /**
   * Saves a note edit once the user pauses.
   * @param {!Object} annotation
   * @param {!Object} changes
   */
  saveLater(annotation, changes) {
    const pending = this.cancelSave(annotation);
    const merged = {...pending?.changes, ...changes};
    const save = () => {
      this.cancelSave(annotation);
      api.updateAnnotation(annotation.id, merged)
          .then(() => this.renderList(), report);
    };
    this.pendingSaves.set(annotation.id, {
      changes: merged, save, timer: setTimeout(save, SAVE_DELAY_MS),
    });
  }

  /**
   * @param {!Object} annotation
   * @return {(!Object|undefined)} The cancelled pending save, if any.
   */
  cancelSave(annotation) {
    const pending = this.pendingSaves.get(annotation.id);
    clearTimeout(pending?.timer);
    this.pendingSaves.delete(annotation.id);
    return pending;
  }

  /** @param {!Object} annotation */
  async remove(annotation) {
    this.hidePopover();
    this.cancelSave(annotation);
    try {
      await api.deleteAnnotation(annotation.id);
      this.annotations = this.annotations.filter((a) => a !== annotation);
      this.drawAnnotations();
    } catch (error) {
      report(error);
    }
  }
}
