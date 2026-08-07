package app.inku.mobile.data.lineage

/**
 * Which lineage edge a redraw declares.
 *
 * The server decides nothing here: it validates the kind, stores it and reads
 * it back, and every value it holds arrived in the request body. What makes an
 * operation one kind rather than another is written in `SPEC.ja.md` (:187,
 * :614, :618, :688, :1198, :1883), so web's rule is that spec's implementation
 * and this is a one-for-one port of it rather than a client invention.
 *
 * The branch order is the rule, not an accident of writing. One edge, one cause
 * (SPEC.ja.md:614): a run that moved the canvas ratio *and* the description
 * writes a single `canvas_aspect_change`, because the ratio is asked first.
 * Reordering these lines changes which single cause the lineage records.
 *
 * Returned as a `String` because that is what `LineageDeclaration` carries;
 * every value here is in `DerivationKindRegistry.KINDS`, and `LineagePlanner`
 * rejects anything that is not.
 */
object SubmitDerivationKind {

    /**
     * The kind a redraw from the describe screen writes. Ported from
     * `submitDerivationKind` (web/src/lib/derivation.ts:64-75).
     *
     * The 写生 (Stage 0.5) grain branch web has between `textChanged` and
     * `replay` is absent because this client has no such layer to change the
     * grain of; contract 5/5 brings the branch together with the layer.
     */
    fun forDescribeSubmit(
        hasParent: Boolean,
        canvasAspectChanged: Boolean,
        textChanged: Boolean,
    ): String? {
        if (canvasAspectChanged) return CANVAS_ASPECT_CHANGE
        if (!hasParent) return null
        if (textChanged) return DESCRIPTION_EDIT
        return REPLAY
    }

    /**
     * The kind the DDL screen writes. Ported from the replay path
     * (web/src/routes/+page.svelte:3469-3471), where an edited DDL is
     * `ddl_edit` and an untouched one is `replay`.
     */
    fun forDdlSubmit(
        hasParent: Boolean,
        canvasAspectChanged: Boolean,
        ddlEdited: Boolean,
    ): String? {
        if (canvasAspectChanged) return CANVAS_ASPECT_CHANGE
        if (!hasParent) return null
        return if (ddlEdited) DDL_EDIT else REPLAY
    }

    const val CANVAS_ASPECT_CHANGE = "canvas_aspect_change"
    const val DESCRIPTION_EDIT = "description_edit"
    const val DDL_EDIT = "ddl_edit"
    const val REPLAY = "replay"
}
