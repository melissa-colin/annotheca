/**
 * @fileoverview Preview of a PDF attached to the journal: one page at a time,
 * with page turning, and a larger view in a dialog.
 */

import * as pdfjs from '../vendor/pdfjs/pdf.min.mjs';

import {t} from './i18n.js';
import {h, icon, report} from './ui.js';

pdfjs.GlobalWorkerOptions.workerSrc =
    new URL('../vendor/pdfjs/pdf.worker.min.mjs', import.meta.url).href;

const PREVIEW_SIZE = {width: 360, height: Infinity};
/** The larger view fits the window, up to this width. */
const LARGE_WIDTH_PX = 960;
/** Height taken in the larger view by its title and page buttons. */
const LARGE_CHROME_PX = 140;

/**
 * Creates the preview of a PDF, loaded once it scrolls into view.
 * @param {string} url Where the PDF is served.
 * @param {string} name Its file name.
 * @return {!HTMLElement}
 */
export function pdfPreview(url, name) {
  let loading = null;
  const load = () => loading ??= pdfjs.getDocument({url}).promise;
  const open = async () => {
    const size = {
      width: Math.min(LARGE_WIDTH_PX, window.innerWidth * 0.9),
      height: window.innerHeight * 0.95 - LARGE_CHROME_PX,
    };
    const dialog = h('dialog.lightbox.pdf-lightbox', {
      onclick: (event) => {
        if (event.target === dialog) dialog.close();
      },
      onclose: () => dialog.remove(),
    }, h('div.pdf-lightbox-header', {},
        h('strong', {}, name),
        h('button.icon-button', {
          title: t('close'), onclick: () => dialog.close(),
        }, icon('x'))),
    pager(await load(), size, preview.page));
    document.body.append(dialog);
    dialog.showModal();
  };
  const figure = h('figure.pdf-preview', {}, h('div.pdf-loading', {}, name));
  let preview = null;
  const observer = new IntersectionObserver(async ([visible]) => {
    if (!visible.isIntersecting) return;
    observer.disconnect();
    try {
      preview = pager(await load(), PREVIEW_SIZE, 1,
          h('button.button.small', {onclick: open},
              icon('external'), t('journal.openLarger')));
      figure.replaceChildren(preview);
    } catch (error) {
      report(error);
    }
  });
  observer.observe(figure);
  return figure;
}

/**
 * Shows one page of a document, with buttons to turn the pages.
 * @param {!Object} pdf The pdf.js document.
 * @param {{width: number, height: number}} size The largest size of a
 *     page, in CSS pixels.
 * @param {number} first The page shown first.
 * @param {?HTMLElement=} extra Shown after the page buttons.
 * @return {!HTMLElement} Its `page` property is the page shown.
 */
function pager(pdf, size, first, extra = null) {
  let task = null;
  const label = h('span.muted.small');
  const frame = h('div.pdf-page', {});
  const previous = h('button.icon-button.small', {
    title: t('journal.previousPage'), onclick: () => show(view.page - 1),
  }, icon('arrowLeft'));
  const next = h('button.icon-button.small.flip', {
    title: t('journal.nextPage'), onclick: () => show(view.page + 1),
  }, icon('arrowLeft'));
  const view = h('div.pdf-pager', {
    tabIndex: 0,
    onkeydown: (event) => {
      if (event.key === 'ArrowLeft') show(view.page - 1);
      if (event.key === 'ArrowRight') show(view.page + 1);
    },
  }, frame, h('div.pdf-controls', {}, previous, label, next, extra));
  const show = async (number) => {
    if (number < 1 || number > pdf.numPages) return;
    view.page = number;
    label.textContent = t('journal.page', {n: number, total: pdf.numPages});
    previous.disabled = number === 1;
    next.disabled = number === pdf.numPages;
    task?.cancel();
    const page = await pdf.getPage(number);
    const natural = page.getViewport({scale: 1});
    const viewport = page.getViewport({scale: Math.min(
        size.width / natural.width, size.height / natural.height)});
    const ratio = window.devicePixelRatio || 1;
    const canvas = h('canvas', {
      width: Math.floor(viewport.width * ratio),
      height: Math.floor(viewport.height * ratio),
    });
    canvas.style.width = `${viewport.width}px`;
    task = page.render({
      canvasContext: canvas.getContext('2d'), viewport,
      transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0],
    });
    try {
      await task.promise;
      frame.replaceChildren(canvas);
    } catch (error) {
      // Turning pages quickly cancels the pages being drawn.
      if (error.name !== 'RenderingCancelledException') report(error);
    }
  };
  show(first);
  return view;
}
