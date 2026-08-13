// The application is an authenticated, browser-only workspace. Its reactive
// settings live in module-scoped Svelte state and are restored after mount, so
// rendering the workspace on the server would create process-wide state shared
// by unrelated requests.
export const ssr = false;
