package app.inku.mobile.pipeline

/**
 * 写生 (Stage 0.5). The values, the states and the labels, in one place.
 *
 * The layer rewrites the description as prose in the language of things before
 * Stage 1 reads it (`server/src/inku_server/sketch.py`, `web/src/lib/sketch.ts`).
 * One control carries three states: `off` (the plain path, the description goes
 * straight to Stage 1), `fine` and `coarse`. Fine and coarse do not change how
 * much is said -- only how big the pieces are.
 *
 * English: the layer is "Sketch from life" and the short form "Sketch" is never
 * used alone (author decision 2026-08-03) -- in the Stage 1 vocabulary `sketch`
 * already means a pale pencil weight (`WebDdlSpec`).
 *
 * **Two normalizers with the same name on the two sources.** The server's
 * `normalize_sketch_grain` (`sketch.py:43`) rounds anything unknown up to the
 * default `fine`, because it is resolving a *requested* grain. web's
 * `normalizeSketchGrain` (`sketch.ts:82`) returns `null` for anything unknown,
 * because it is reading a *recorded* grain off a saved work, and a work with no
 * grain recorded has none. Rounding the second one to `fine` would make every
 * work drawn before the column look like it was drawn at the default. They are
 * kept apart here as [normalizeGrain] and [recordedGrainOf].
 */
enum class SketchGrain(val wire: String) {
    Fine("fine"),
    Coarse("coarse"),
}

/** What the author asked the layer to do. `off` is a grain nobody asked for. */
enum class SketchMode(val wire: String) {
    Off("off"),
    Fine("fine"),
    Coarse("coarse"),
}

/**
 * What the record says the layer did for one work. Five values, plus a sixth
 * state the record can be in: no value at all, held here as a `null`
 * [SketchState]. That absence is NOT [Off] -- `off` is a choice the author
 * made, and the works that predate the column made no such choice.
 */
enum class SketchState(val wire: String) {
    Fine("fine"),
    Coarse("coarse"),
    Fallback("fallback"),
    Off("off"),
    NotApplicable("not_applicable"),
}

object Sketches {

    /** `SKETCH_GRAINS` / `DEFAULT_SKETCH_GRAIN` (`sketch.py:35-36`). */
    val GRAINS: List<SketchGrain> = listOf(SketchGrain.Fine, SketchGrain.Coarse)
    val DEFAULT_GRAIN: SketchGrain = SketchGrain.Fine

    /** `SKETCH_MODES` / `DEFAULT_SKETCH_MODE` (`sketch.ts:22`, `:26`). The
     *  author's default: the layer runs, cutting fine. */
    val MODES: List<SketchMode> = listOf(SketchMode.Off, SketchMode.Fine, SketchMode.Coarse)
    val DEFAULT_MODE: SketchMode = SketchMode.Fine

    /** `SKETCH_STATES` (`sketch.py:40`, `sketch.ts:20`), in the server's order. */
    val STATES: List<SketchState> = listOf(
        SketchState.Fine,
        SketchState.Coarse,
        SketchState.Fallback,
        SketchState.Off,
        SketchState.NotApplicable,
    )

    /**
     * Resolve a *requested* grain. An absent or unknown value means the default.
     * One-for-one with `normalize_sketch_grain` (`sketch.py:43-46`), including
     * its `str(value or "").strip().lower()`.
     *
     * `"off"` resolves to `fine` here, and that is not a slip: `off` is a state
     * of the control, not a grain, and it never reaches this function. That is
     * why [SketchMode] and [SketchGrain] are two types.
     */
    fun normalizeGrain(value: String?): SketchGrain {
        val grain = (value ?: "").trim().lowercase()
        return GRAINS.firstOrNull { it.wire == grain } ?: DEFAULT_GRAIN
    }

    /**
     * Accept a state a caller claims for its own path. Unknown values are not
     * silently rewritten. One-for-one with `normalize_sketch_state`
     * (`sketch.py:253-259`).
     */
    fun normalizeState(value: String?): SketchState? {
        if (value == null) return null
        val state = value.trim().lowercase()
        return STATES.firstOrNull { it.wire == state }
    }

    /**
     * Read a grain *recorded* on a saved work. One-for-one with web's
     * `normalizeSketchGrain` (`sketch.ts:82-84`) -- an exact match on the two
     * words, with no trimming and no case folding, and `null` for everything
     * else. Works saved before the column have no grain recorded, and this is
     * the function that says so.
     */
    fun recordedGrainOf(value: String?): SketchGrain? =
        GRAINS.firstOrNull { it.wire == value }

    /** `sketchGrainOf` (`sketch.ts:86-88`): the mode `off` carries no grain. */
    fun grainOf(mode: SketchMode): SketchGrain? = when (mode) {
        SketchMode.Off -> null
        SketchMode.Fine -> SketchGrain.Fine
        SketchMode.Coarse -> SketchGrain.Coarse
    }

    /** `sketchModeOf` (`sketch.ts:90-92`): a work with no grain was drawn off. */
    fun modeOf(grain: String?): SketchMode = when (recordedGrainOf(grain)) {
        SketchGrain.Fine -> SketchMode.Fine
        SketchGrain.Coarse -> SketchMode.Coarse
        null -> SketchMode.Off
    }

    /** `sketchModeLabel` (`sketch.ts:29-33`). Japanese is the canonical wording. */
    fun modeLabel(mode: SketchMode, isJapanese: Boolean): String = when (mode) {
        SketchMode.Off -> if (isJapanese) "切" else "Off"
        SketchMode.Fine -> if (isJapanese) "細かく" else "Fine"
        SketchMode.Coarse -> if (isJapanese) "大きく" else "Coarse"
    }

    /** `sketchModeHint` (`sketch.ts:35-49`). */
    fun modeHint(mode: SketchMode, isJapanese: Boolean): String = when (mode) {
        SketchMode.Off ->
            if (isJapanese) {
                "写生を通さず、記述をそのまま解釈へ渡す"
            } else {
                "Skip the layer and send the description straight to interpretation"
            }
        SketchMode.Fine ->
            if (isJapanese) {
                "細かく区切って解釈する。一文に一つのことを書く"
            } else {
                "Cut fine: one fact per short sentence, so more instructions come out"
            }
        SketchMode.Coarse ->
            if (isJapanese) {
                "大きく区切って深く解釈する。関係のあることを一文に束ねる"
            } else {
                "Cut coarse: related facts bundled into longer sentences, each read more deeply"
            }
    }

    /**
     * A note shown beside an option. `sketchModeNote` (`sketch.ts:55-58`): off
     * is kept -- the layer can still be skipped -- but it is not what a work
     * should normally be drawn through, and the control is the only place that
     * says so.
     */
    fun modeNote(mode: SketchMode, isJapanese: Boolean): String =
        if (mode != SketchMode.Off) "" else if (isJapanese) "（推奨しない）" else "(not recommended)"
}
