/**
 * @fileoverview Project journal: dated entries in Markdown, with TikZ
 * diagrams and images, written by the user or by AI assistants.
 */

import {api} from './api.js';
import {formatDate, t} from './i18n.js';
import {renderMarkdown} from './markdown.js';
import {ask, chooseFiles, h, icon, report, setChildren} from './ui.js';

/** Kinds of entries, to sort the journal; '' is an uncategorised entry. */
const CATEGORIES = [
  'idea', 'experiment', 'result', 'problem', 'decision', 'reading'];

/** @type {string} The category shown, or '' to show every entry. */
let shownCategory = '';

/**
 * Shows the journal of a project.
 * @param {!HTMLElement} main
 * @param {!Object} project
 * @param {function(): !Promise} reload Reloads the project and this view.
 */
export async function renderJournal(main, project, reload) {
  const allEntries = await api.listJournal(project.id);
  const used = CATEGORIES.filter((category) =>
    allEntries.some((entry) => entry.category === category));
  if (!used.includes(shownCategory)) shownCategory = '';
  const entries = allEntries.filter((entry) =>
    !shownCategory || entry.category === shownCategory);
  const days = new Map();
  for (const entry of entries) {
    const day = formatDate(entry.created_at, {dateStyle: 'full'});
    days.set(day, [...days.get(day) ?? [], entry]);
  }
  setChildren(main,
      h('header.view-header', {},
          h('h1', {}, t('journal')),
          h('p.muted', {}, t('journal.subtitle'))),
      composer(project, reload),
      used.length > 0 && categoryFilter(allEntries, used,
          () => renderJournal(main, project, reload).catch(report)),
      entries.length ? null : h('p.empty-hint', {}, t('journal.empty')),
      [...days].map(([day, dayEntries]) => h('section.journal-day', {},
          h('h2', {}, day),
          dayEntries.map((entry) => entryElement(entry, reload)))));
}

/**
 * @param {!Array<!Object>} entries Every entry of the journal.
 * @param {!Array<string>} used The categories some entry has.
 * @param {function()} rerender Shows the journal again, filtered.
 * @return {!HTMLElement} Buttons to show only the entries of a category.
 */
function categoryFilter(entries, used, rerender) {
  const option = (category, label, count) => h(
      `button.chip.category${category ? `.cat-${category}` : ''}` +
      `${category === shownCategory ? '.active' : ''}`, {
        onclick: () => {
          shownCategory = category;
          rerender();
        },
      }, label, h('span.category-count', {}, String(count)));
  return h('div.category-filter', {},
      option('', t('journal.all'), entries.length),
      used.map((category) => option(category, t(`category.${category}`),
          entries.filter((entry) => entry.category === category).length)));
}

/**
 * @param {string} selected The category chosen, or ''.
 * @param {function(string)} choose Called with the new category, or ''.
 * @return {!HTMLElement} Buttons to choose the category of an entry.
 */
function categoryPicker(selected, choose) {
  const picker = h('div.category-picker', {});
  const render = () => picker.replaceChildren(...CATEGORIES.map((category) =>
    h(`button.chip.category.cat-${category}` +
        `${category === selected ? '.active' : ''}`, {
      type: 'button',
      onclick: () => {
        selected = category === selected ? '' : category;
        choose(selected);
        render();
      },
    }, t(`category.${category}`))));
  render();
  return picker;
}

/**
 * @param {!Object} project
 * @param {function(): !Promise} reload
 * @return {!HTMLElement} The form to write a new entry, with images.
 */
function composer(project, reload) {
  let category = '';
  const images = [];
  const previews = h('div.pending-images');
  const addImages = (files) => {
    images.push(...files.filter((file) => file.type.startsWith('image/')));
    previews.replaceChildren(...images.map((file, index) =>
      h('figure.pending-image', {},
          h('img', {src: URL.createObjectURL(file), alt: file.name}),
          h('button.icon-button.small', {
            title: t('journal.removeImage'),
            onclick: () => {
              images.splice(index, 1);
              addImages([]);
            },
          }, icon('x')))));
  };
  const submit = async () => {
    if (!textarea.value.trim() && !images.length) return;
    button.disabled = true;
    try {
      const entry = await api.addJournalEntry(
          project.id, textarea.value, category);
      for (const image of images) {
        await api.addJournalImage(entry.id, image);
      }
      await reload();
    } catch (error) {
      button.disabled = false;
      report(error);
    }
  };
  const textarea = h('textarea.paste.journal-input', {
    rows: 4,
    placeholder: t('journal.placeholder'),
    onkeydown: (event) => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) submit();
    },
    onpaste: (event) => addImages([...event.clipboardData.files]),
  });
  const button = h('button.button.primary', {onclick: submit},
      icon('plus'), t('journal.add'));
  return h('div.paste-box.composer', {
    ondragover: (event) => event.preventDefault(),
    ondrop: (event) => {
      event.preventDefault();
      addImages([...event.dataTransfer.files]);
    },
  }, textarea, previews,
  h('div.paste-actions', {},
      categoryPicker(category, (chosen) => category = chosen),
      h('button.button.small.ghost', {
        onclick: () => chooseFiles('image/*', addImages, true),
      }, icon('image'), t('journal.images')),
      h('kbd', {}, t('paste.hint')), button));
}

/**
 * @param {!Object} entry
 * @param {function(): !Promise} reload
 * @return {!HTMLElement}
 */
function entryElement(entry, reload) {
  const body = h('div.markdown', {}, renderMarkdown(entry.body));
  const edit = () => {
    let category = entry.category;
    const textarea = h('textarea.paste.journal-input', {
      value: entry.body, rows: Math.max(4, entry.body.split('\n').length),
    });
    body.replaceChildren(textarea, h('div.edit-actions', {},
        categoryPicker(category, (chosen) => category = chosen),
        h('button.button.small.ghost', {
          onclick: () => body.replaceChildren(renderMarkdown(entry.body)),
        }, t('cancel')),
        h('button.button.small.primary', {
          onclick: () => api.updateJournalEntry(
              entry.id, textarea.value, category).then(reload, report),
        }, t('save'))));
    textarea.focus();
  };
  const remove = async () => {
    const confirmed = await ask({
      title: t('journal.delete'), message: t('journal.deleteConfirm'),
      action: t('delete'), danger: true,
    });
    if (confirmed) api.deleteJournalEntry(entry.id).then(reload, report);
  };
  return h('article.entry', {},
      h('header.entry-header', {},
          h('time', {dateTime: entry.created_at},
              formatDate(entry.created_at, {timeStyle: 'short'})),
          entry.category && h(`span.chip.category.cat-${entry.category}`, {},
              t(`category.${entry.category}`)),
          entry.author && h('span.chip.agent', {}, icon('bot'), entry.author),
          entry.updated_at && h('span.muted.small', {}, t('journal.edited',
              {date: formatDate(entry.updated_at,
                  {dateStyle: 'medium', timeStyle: 'short'})})),
          h('span.entry-actions', {},
              h('button.icon-button.small', {
                title: t('journal.edit'), onclick: edit,
              }, icon('pencil')),
              h('button.icon-button.small.danger', {
                title: t('journal.delete'), onclick: remove,
              }, icon('trash')))),
      body,
      entry.images.length > 0 && h('div.entry-images', {},
          entry.images.map((image) => imageElement(image, reload))));
}

/**
 * @param {{id: number}} image
 * @param {function(): !Promise} reload
 * @return {!HTMLElement} A thumbnail that opens full size when clicked.
 */
function imageElement(image, reload) {
  const url = api.journalImageUrl(image.id);
  return h('figure.entry-image', {},
      h('img', {src: url, alt: '', loading: 'lazy', onclick: () => {
        const viewer = h('dialog.lightbox', {
          onclick: () => viewer.close(),
          onclose: () => viewer.remove(),
        }, h('img', {src: url, alt: ''}));
        document.body.append(viewer);
        viewer.showModal();
      }}),
      h('button.icon-button.small.danger', {
        title: t('journal.removeImage'),
        onclick: () => api.deleteJournalImage(image.id).then(reload, report),
      }, icon('x')));
}
