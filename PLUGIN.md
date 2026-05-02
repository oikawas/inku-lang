# inku Plugin Guide

inku keeps the drawing pipeline small and treats optional behavior as plugins.
The first reference plugin is `canvas-aspect`, which changes the SVG canvas
aspect ratio without changing the Stage 1/Stage 2 DDL or JSON Score contract.

## Current Architecture

The plugin system currently has one hook:

```text
canvas-size hook
  UI plugin button -> per-user plugin storage -> API request field -> renderer canvas size
                   -> aspect-aware placeholder before the next render
```

Core code owns authentication, DDL generation, JSON Score validation, history,
and SVG rendering.  A plugin should provide a narrow option surface and pass its
state through the hook.  This keeps the core schema stable while allowing
extensions to affect rendering.

## Reference Plugin: canvas-aspect

Files:

```text
server/src/inku_server/plugins/__init__.py
server/src/inku_server/plugins/system/canvas_aspect/__init__.py
server/src/inku_server/plugins/user/__init__.py
web/src/lib/plugins/system/canvas-aspect/index.ts
web/src/lib/plugins/user/README.md
web/src/lib/components/CanvasAspectPlugin.svelte
```

System plugins and user plugins are separated by directory.  Each plugin owns a
dedicated directory:

```text
server/src/inku_server/plugins/
  __init__.py                    # stable registry / re-export surface
  system/
    canvas_aspect/
      __init__.py                # bundled canvas-aspect hook implementation
  user/
    __init__.py                  # reserved namespace for future user plugins

web/src/lib/plugins/
  system/
    canvas-aspect/
      index.ts                   # bundled canvas-aspect UI data/helpers
  user/
    README.md                    # reserved location for future user plugins
```

System plugins are shipped with inku and may be used by the reference UI.
User plugins are reserved for locally installed or third-party extensions; the
runtime loader is not implemented yet.

The plugin supports these aspect identifiers:

| Category | ID | Ratio | Purpose |
| --- | --- | --- | --- |
| Basic | `square` | 1:1 | Default ordered square canvas |
| Standard | `golden` | 1.618:1 | Golden-ratio rectangle |
| Modern | `a4` | 1:1.414 | Root rectangle / print standard |
| Modern | `b4` | 1:1.414 | Root rectangle / print standard |
| Classic JP | `pillar` | 1:5 | Tall Japanese pillar-picture format |
| Ukiyoe | `oban` | 2:3 | Ukiyo-e oban proportion |
| Cinema | `wide` | 2.35:1 | Cinematic panorama |
| Classic JP | `byobu` | 2.2:1 | Japanese folding screen format based on one half of a six-panel pair |
| Mobile | `vertical` | 9:16 | Smartphone vertical format |

## User Storage

Each user has a JSON plugin extension field in the server DB:

```json
{
  "canvas-aspect": {
    "selected": "golden"
  }
}
```

API endpoints:

```text
GET /api/auth/me/plugin-storage
PUT /api/auth/me/plugin-storage
PUT /api/auth/me/plugin-storage/{plugin_id}
```

The storage object is intentionally generic.  Plugin IDs must be short,
non-empty strings using alphanumeric characters plus `-`, `_`, or `.`.  Values
must be JSON objects, and total storage is size-limited.

## Renderer Contract

The renderer receives `canvas_aspect` from `/api/paint`, `/api/compose`, and
history replay/save paths.  The canvas-size hook changes SVG `width`, `height`,
and `viewBox`.

Normalized coordinates remain `0.0-1.0`:

```text
x -> canvas width
y -> canvas height
circle radius / arc radius -> shorter canvas side
ellipse / rectangle size -> canvas width and height
```

This avoids stretching circles into ellipses when a wide or vertical canvas is
selected.

## UI Contract

The plugin invocation button is placed in the prompt header before model
selection.  A plugin UI should live in its own Svelte component and should not
embed large behavior directly in `+page.svelte`.

When a user selects a new canvas aspect, the current rendered SVG is cleared and
the drawing panel returns to an aspect-aware placeholder.  This avoids showing a
previous square or wide render under a newly selected canvas setting.  The next
paint/compose request then renders with the selected `canvas_aspect`.

The canvas display reads the actual SVG `viewBox` when possible, so old history
items keep their original aspect ratio even after the current plugin setting is
changed.

The drawing status bar also exposes the active canvas aspect.  For a fresh
render it displays the current `canvas-aspect` selection; for history display it
prefers the saved JSON Score `canvas` value, so the user can see which canvas
type produced that item.  Export controls stay separate from this context
display and use compact download icons for SVG / PNG actions.

## Adding Another Hook

Future hooks should follow the same shape:

1. Add the server implementation under `server/src/inku_server/plugins/system/<plugin_name>/` or `server/src/inku_server/plugins/user/<plugin_name>/`.
2. Re-export the stable hook surface from `server/src/inku_server/plugins/__init__.py` when core API or renderer code needs it.
3. Add the frontend module under `web/src/lib/plugins/system/<plugin-id>/` or `web/src/lib/plugins/user/<plugin-id>/`.
4. Add a component under `web/src/lib/components/` only for the visible plugin UI.
5. Store user choices under `/api/auth/me/plugin-storage/{plugin_id}`.
6. Pass only the needed hook value into the core API or renderer.
7. Document the hook contract in this file.

For example, a future natural-primitive plugin such as `leaf` should first
define whether it extends JSON Score, Stage 2 composition, or only the SVG
renderer.  If it changes the score schema, it needs a stricter compatibility
plan than the canvas-size hook.
