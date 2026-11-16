/**
 * @fileoverview Reading notes on a paper, as filed in one folder: dated
 * journal entries linked to it, any number of them.
 */

import {api} from './api.js';
import {formatDate, t} from './i18n.js';
import {renderMarkdown} from './markdown.js';
import {h, icon, report, setChildren} from './ui.js';

/**
 * Creates the list of the reading notes on a paper, newest first, below a
 * box to write a new one.
 * @param {number} projectId
 * @param {!Object} placement Its `note_count` is kept up to date.
 * @param {function()=} onChange Called after a note is added.
 * @return {!HTMLElement}
 */
export function readingNotes(projectId, placement, onChange = () => {}) {
  const list = h('div.reading-notes-list');
  const load = () => api.listReadingNotes(projectId, placement.id)
      .then((notes) => {
        placement.note_count = notes.length;
        setChildren(list, notes.length ? notes.map(noteElement) :
            h('p.muted.small', {}, t('notes.empty')));
      }, report);
  const add = async () => {
    if (!textarea.value.trim()) return;
    try {
      await api.addJournalEntry(
          projectId, textarea.value, 'reading', placement.id);
      textarea.value = '';
      await load();
      onChange();
    } catch (error) {
      report(error);
    }
  };
  const textarea = h('textarea.notes', {
    placeholder: t('notes.placeholder'),
    onkeydown: (event) => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) add();
    },
  });
  load();
  return h('div.reading-notes', {},
      textarea,
      h('div.edit-actions', {},
          h('kbd', {}, t('paste.hint')),
          h('button.button.small.primary', {onclick: add},
              icon('plus'), t('notes.add'))),
      list);
}

/**
 * @param {!Object} note A journal entry.
 * @return {!HTMLElement}
 */
function noteElement(note) {
  return h('article.reading-note', {},
      h('header.entry-header', {},
          h('time', {dateTime: note.created_at}, formatDate(
              note.created_at, {dateStyle: 'medium', timeStyle: 'short'})),
          note.author && h('span.chip.agent', {}, icon('bot'), note.author)),
      h('div.markdown', {}, renderMarkdown(note.body)));
}
