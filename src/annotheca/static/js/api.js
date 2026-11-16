/**
 * @fileoverview Client for the Annotheca HTTP API.
 */

/**
 * Sends a request and returns the decoded JSON response.
 * @param {string} method
 * @param {string} path Path below /api.
 * @param {(!Object|!Blob)=} body JSON payload, or a file.
 * @return {!Promise<*>}
 * @throws {Error} With the server's error code as message.
 */
async function request(method, path, body) {
  const init = {method, headers: {}};
  if (body instanceof Blob) {
    init.body = body;
    init.headers['Content-Type'] = body.type || 'application/octet-stream';
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    const detail = await response.json().then((data) => data.detail, () => '');
    throw new Error(typeof detail === 'string' ? detail : 'generic');
  }
  return response.status === 204 ? null : response.json();
}

export const api = {
  listProjects: () => request('GET', '/projects'),
  getProject: (id) => request('GET', `/projects/${id}`),
  createProject: (name) => request('POST', '/projects', {name}),
  createFolder: (projectId, name) =>
    request('POST', `/projects/${projectId}/folders`, {name}),
  rename: (kind, id, name) => request('PATCH', `/${kind}s/${id}`, {name}),
  remove: (kind, id) => request('DELETE', `/${kind}s/${id}`),
  exportUrl: (projectId) => `/api/projects/${projectId}/bibtex`,
  bundleUrl: (projectId) => `/api/projects/${projectId}/bundle`,
  importBundle: (file) => request('POST', '/projects/import', file),

  addPapers: (folderId, body) =>
    request('POST', `/folders/${folderId}/papers`, body),
  removePlacement: (id) => request('DELETE', `/placements/${id}`),
  setNotes: (placementId, notes) =>
    request('PUT', `/placements/${placementId}/notes`, {notes}),
  pdfUrl: (paperId) => `/api/papers/${paperId}/pdf`,
  uploadPdf: (paperId, file) => request('PUT', `/papers/${paperId}/pdf`, file),
  fetchPdf: (paperId) => request('POST', `/papers/${paperId}/pdf/fetch`),

  listAnnotations: (placementId) =>
    request('GET', `/placements/${placementId}/annotations`),
  createAnnotation: (placementId, annotation) =>
    request('POST', `/placements/${placementId}/annotations`, annotation),
  updateAnnotation: (id, changes) =>
    request('PATCH', `/annotations/${id}`, changes),
  deleteAnnotation: (id) => request('DELETE', `/annotations/${id}`),

  listJournal: (projectId) => request('GET', `/projects/${projectId}/journal`),
  addJournalEntry: (projectId, body) =>
    request('POST', `/projects/${projectId}/journal`, {body}),
  updateJournalEntry: (id, body) => request('PATCH', `/journal/${id}`, {body}),
  deleteJournalEntry: (id) => request('DELETE', `/journal/${id}`),
  addJournalImage: (entryId, file) =>
    request('POST', `/journal/${entryId}/images`, file),
  deleteJournalImage: (id) => request('DELETE', `/journal-images/${id}`),
  journalImageUrl: (id) => `/api/journal-images/${id}`,

  listTodos: (projectId) => request('GET', `/projects/${projectId}/todos`),
  addTodo: (projectId, text) =>
    request('POST', `/projects/${projectId}/todos`, {text}),
  updateTodo: (id, changes) => request('PATCH', `/todos/${id}`, changes),
  deleteTodo: (id) => request('DELETE', `/todos/${id}`),
};
