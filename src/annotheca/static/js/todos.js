/**
 * @fileoverview Project to-do list: what is left to do, and what got done.
 */

import {api} from './api.js';
import {formatDate, t} from './i18n.js';
import {h, icon, report, setChildren} from './ui.js';

/**
 * Shows the to-do list of a project.
 * @param {!HTMLElement} main
 * @param {!Object} project
 * @param {function(): !Promise} reload Reloads the project and this view.
 */
export async function renderTodos(main, project, reload) {
  const todos = await api.listTodos(project.id);
  const open = todos.filter((todo) => !todo.done_at);
  const done = todos.filter((todo) => todo.done_at);
  const input = h('input.input.todo-input', {
    placeholder: t('todo.placeholder'),
    onkeydown: (event) => {
      if (event.key !== 'Enter' || !input.value.trim()) return;
      api.addTodo(project.id, input.value).then(reload, report);
    },
  });
  setChildren(main,
      h('header.view-header', {},
          h('h1', {}, t('todo')),
          h('p.muted', {}, t('todo.subtitle'))),
      input,
      h('ul.todo-list', {}, open.map((todo) => todoItem(todo, reload))),
      !todos.length && h('p.empty-hint', {}, t('todo.empty')),
      done.length > 0 && h('details.todo-done', {},
          h('summary', {}, t('todo.done', {n: done.length})),
          h('ul.todo-list', {}, done.map((todo) => todoItem(todo, reload)))));
  input.focus();
}

/**
 * @param {!Object} todo
 * @param {function(): !Promise} reload
 * @return {!HTMLElement}
 */
function todoItem(todo, reload) {
  const update = (changes) =>
    api.updateTodo(todo.id, changes).then(reload, report);
  const text = h('span.todo-text', {
    title: t('todo.editHint'),
    ondblclick: () => {
      const input = h('input.input', {
        value: todo.text,
        onkeydown: (event) => {
          if (event.key === 'Enter') update({text: input.value});
          if (event.key === 'Escape') input.replaceWith(text);
        },
        onblur: () => input.replaceWith(text),
      });
      text.replaceWith(input);
      input.select();
    },
  }, todo.text);
  return h(`li.todo${todo.done_at ? '.is-done' : ''}`, {},
      h('input', {
        type: 'checkbox', checked: Boolean(todo.done_at),
        ariaLabel: todo.text,
        onchange: () => update({done: !todo.done_at}),
      }),
      text,
      todo.author && h('span.chip.agent', {}, icon('bot'), todo.author),
      h('span.muted.small', {}, todo.done_at ?
          t('todo.doneOn', {date: formatDate(todo.done_at)}) :
          formatDate(todo.created_at)),
      h('button.icon-button.small.danger', {
        title: t('todo.delete'),
        onclick: () => api.deleteTodo(todo.id).then(reload, report),
      }, icon('trash')));
}
