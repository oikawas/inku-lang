# Printmaking implementation notes (v1.87)

The existing extension points are `Weight` and `Instruction` in `schema.py`, the v1.71 `SurfaceSpec` / `CanvasGroundSpec` profile renderer, and `_texture_seed`, which already derives deterministic material variation from Score, kind, index, and `render_seed`. The v1.87 implementation reuses these paths and does not add an rh2 input.

Stroke performance is server-side and deterministic: L0 intended geometry, L1 damped tracking, L2 one multi-octave latent energy signal shared by width and lateral deviation, L3 at most two sparse events, and L4 a tool grammar table. Rotring explicitly bypasses the engine. Variable width is encoded as one outline path; drypoint adds one one-sided burr polyline. Output uses 49 center samples (98 outline vertices), below the 200-point hard budget, and adds no per-line filter definitions.

Surface profiles continue to use the v1.71 mechanism. Display clips textures; editable and compat use vector marks. Hatch and crosshatch expose measured spacing metadata, while aquatint emits two to four discrete step labels. Mezzotint remains dark without filter support. Rendering order is ground, additive marks, carve marks, and plate tone.

Printmaking is input-driven. Stage 1.5 contains no print candidates. Composer literal gates drop unmarked print fields and drop carve when no dark ground exists; they never add or repair ground, mode, or print weights. Rope was removed rather than retained as an unreleased compatibility alias.

Preflight budget target: one mezzotint score with 20 carve marks should render in under 2 seconds and produce less than 1.5 MB SVG. See `server/tests/test_printmaking.py` for deterministic, schema, geometry, profile, and budget checks.
