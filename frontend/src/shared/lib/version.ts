/**
 * Application version, injected at build time from `package.json` via the Vite
 * `__APP_VERSION__` define. Kept in step with the backend `pyproject.toml`
 * version and the published Docker image tag.
 */
export const APP_VERSION = __APP_VERSION__
