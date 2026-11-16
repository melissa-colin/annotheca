/**
 * @fileoverview Trash: deleted projects and papers, to restore or delete
 * for good.
 */

import {api} from './api.js';
import {formatDate, t} from './i18n.js';
import {ask, h, icon, report, setChildren, toast} from './ui.js';

/** Days before the trash is emptied, as TRASH_DAYS in library.py. */
export const TRASH_DAYS = 30;

/**
 * Shows the trash.
 * @param {!HTMLElement} main
 * @param {function(): !Promise} reload Reloads this view.
 */
export async function renderTrash(main, reload) {
  const {projects, papers} = await api.listTrash();
  const empty = !projects.length && !papers.length;
  setChildren(main,
      h('header.view-header.with-actions', {},
          h('div', {},
              h('h1', {}, t('trash')),
              h('p.muted', {}, t('trash.subtitle', {days: TRASH_DAYS}))),
          !empty && h('button.button.danger', {
            onclick: () => emptyTrash(reload),
          }, icon('trash'), t('trash.emptyAll'))),
      empty && h('p.empty-hint', {}, t('trash.empty')),
      projects.length > 0 && h('section.trash-section', {},
          h('h2', {}, t('trash.projects')),
          projects.map((project) => trashedItem(
              'project', project, project.name,
              t('papers', {n: project.paper_count}), reload))),
      papers.length > 0 && h('section.trash-section', {},
          h('h2', {}, t('trash.papers')),
          papers.map((paper) => trashedItem(
              'placement', paper, paper.title,
              `${paper.project} · ${paper.folder}`, reload))));
}

/**
 * @param {string} kind 'project' or 'placement'.
 * @param {{id: number, deleted_at: string}} item
 * @param {string} name
 * @param {string} details
 * @param {function(): !Promise} reload
 * @return {!HTMLElement}
 */
function trashedItem(kind, item, name, details, reload) {
  const deleteForGood = async () => {
    const confirmed = await ask({
      title: t('trash.deleteForGood'),
      message: t('trash.deleteForGoodConfirm', {name}),
      action: t('trash.deleteForGood'), danger: true,
    });
    if (confirmed) api.deleteForGood(kind, item.id).then(reload, report);
  };
  return h('article.trashed', {},
      icon(kind === 'project' ? 'book' : 'file'),
      h('div.trashed-body', {},
          h('strong', {}, name),
          h('span.muted.small', {}, [details, t('trash.deletedOn',
              {date: formatDate(item.deleted_at)})].join(' · '))),
      h('button.button.small', {
        onclick: () => api.restore(kind, item.id).then(() => {
          toast(t('trash.restored', {name}));
          return reload();
        }, report),
      }, icon('undo'), t('trash.restore')),
      h('button.icon-button.danger', {
        title: t('trash.deleteForGood'), onclick: deleteForGood,
      }, icon('trash')));
}

/** @param {function(): !Promise} reload */
async function emptyTrash(reload) {
  const confirmed = await ask({
    title: t('trash.emptyAll'), message: t('trash.emptyConfirm'),
    action: t('trash.emptyAll'), danger: true,
  });
  if (confirmed) api.emptyTrash().then(reload, report);
}
