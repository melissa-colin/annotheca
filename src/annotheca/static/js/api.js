/**
 * @fileoverview Client for the Annotheca HTTP API.
 */

/**
 * Sends a request and returns the decoded JSON response.
 * @param {string} method
 * @param {string} path Path below /api.
 * @param {(!Object|!Blob)=} body JSON payload, or a PDF file.
 * @return {!Promise<*>}
 * @throws {Error} With the server's error code as message.
 */
async function request(method, path, body) {
  const init = {method, headers: {}};
  if (body instanceof Blob) {
    init.body = body;
    init.headers['Content-Type'] = 'application/pdf';
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

  addPapers: (folderId, body) =>
    request('POST', `/folders/${folderId}/papers`, body),
  removePlacement: (id) => request('DELETE', `/placements/${id}`),
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
};
