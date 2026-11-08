/**
 * @fileoverview Per-browser preferences. Storage may be unavailable (private
 * windows, blocked site data), in which case preferences are simply not kept.
 */

const PREFIX = 'annotheca.';

/**
 * @param {string} key
 * @return {*} The stored value, or null.
 */
export function load(key) {
  try {
    return JSON.parse(localStorage.getItem(PREFIX + key));
  } catch {
    return null;
  }
}

/**
 * @param {string} key
 * @param {*} value Any JSON-serializable value.
 */
export function save(key, value) {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Preferences are a convenience; losing them is fine.
  }
}
