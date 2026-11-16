/**
 * @fileoverview Project journal: dated entries in Markdown, with TikZ
 * diagrams and images, written by the user or by AI assistants.
 */

import {api} from './api.js';
import {formatDate, t} from './i18n.js';
import {renderMarkdown} from './markdown.js';
import {ask, chooseFiles, h, icon, report, setChildren} from './ui.js';

/**
 * Shows the journal of a project.
 * @param {!HTMLElement} main
 * @param {!Object} project
 * @param {function(): !Promise} reload Reloads the project and this view.
 */
export async function renderJournal(main, project, reload) {
  const entries = await api.listJournal(project.id);
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
      entries.length ? null : h('p.empty-hint', {}, t('journal.empty')),
      [...days].map(([day, dayEntries]) => h('section.journal-day', {},
          h('h2', {}, day),
          dayEntries.map((entry) => entryElement(entry, reload)))));
}

/**
 * @param {!Object} project
 * @param {function(): !Promise} reload
 * @return {!HTMLElement} The form to write a new entry, with images.
 */
function composer(project, reload) {
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
      const entry = await api.addJournalEntry(project.id, textarea.value);
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
    const textarea = h('textarea.paste.journal-input', {
      value: entry.body, rows: Math.max(4, entry.body.split('\n').length),
    });
    body.replaceChildren(textarea, h('div.edit-actions', {},
        h('button.button.small.ghost', {
          onclick: () => body.replaceChildren(renderMarkdown(entry.body)),
        }, t('cancel')),
        h('button.button.small.primary', {
          onclick: () => api.updateJournalEntry(entry.id, textarea.value)
              .then(reload, report),
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
