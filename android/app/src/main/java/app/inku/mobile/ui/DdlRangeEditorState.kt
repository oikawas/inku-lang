package app.inku.mobile.ui

import androidx.compose.foundation.text.input.TextFieldBuffer
import androidx.compose.ui.text.TextRange

internal data class DdlEditorSnapshot(
    val source: String,
    val selection: TextRange,
    val composition: TextRange? = null,
    val focused: Boolean = true,
    val editable: Boolean = true,
)

internal fun DdlNamedRange.contains(selection: TextRange): Boolean =
    if (selection.collapsed) selection.start > start && selection.start < end
    else selection.min < end && selection.max > start

internal fun DdlNamedRange.nameStart(source: String): Int =
    start + source.substring(start, end - numbers.length).lastIndexOf(name)

internal data class DdlSourceChange(val start: Int, val end: Int, val replacement: String) {
    fun map(position: Int, after: Boolean = false): Int = when {
        position < start -> position
        position > end -> position + replacement.length - (end - start)
        start == end -> start + if (after) replacement.length else 0
        position == end -> start + replacement.length
        position == start -> start
        else -> start + if (after) replacement.length else 0
    }

    companion object {
        fun between(before: String, after: String): DdlSourceChange? {
            if (before == after) return null
            var start = 0
            while (start < minOf(before.length, after.length) && before[start] == after[start]) start++
            var suffix = 0
            while (suffix < minOf(before.length, after.length) - start &&
                before[before.lastIndex - suffix] == after[after.lastIndex - suffix]) suffix++
            return DdlSourceChange(start, before.length - suffix, after.substring(start, after.length - suffix))
        }
    }
}

internal data class DdlEditorLabel(val range: DdlNamedRange, val start: Int, val end: Int, val dotted: Boolean)

/** Only presentation deletions. BasicTextField owns their bidirectional offset mapping. */
internal class DdlEditorProjection(
    val source: String,
    val deletions: List<DdlSourceChange>,
    val labels: List<DdlEditorLabel>,
) {
    fun applyTo(buffer: TextFieldBuffer) {
        deletions.asReversed().forEach { buffer.replace(it.start, it.end, "") }
    }

    fun displayOffset(original: Int): Int = original - deletions.sumOf {
        (original - it.start).coerceIn(0, it.end - it.start)
    }
}

internal fun ddlEditorProjection(snapshot: DdlEditorSnapshot, table: CompositionRangeTable): DdlEditorProjection {
    val ranges = ddlNamedRanges(snapshot.source, table)
    val deletions = mutableListOf<DdlSourceChange>()
    // Copy/cut use the presented text in Foundation. Keep every selected range raw,
    // including while a context menu has focus, so its ordinary clipboard actions are lossless.
    fun open(range: DdlNamedRange) = ((snapshot.focused || !snapshot.selection.collapsed) && range.contains(snapshot.selection)) ||
        snapshot.composition?.let(range::contains) == true
    ranges.filter { it.foldable && !open(it) }.forEach { range ->
        val nameStart = range.nameStart(snapshot.source)
        // Keep the actual article and name, so their character offsets remain precise.
        val prefix = snapshot.source.substring(range.start, nameStart)
        val articleStart = if (range.article.isEmpty()) nameStart else range.start + prefix.lastIndexOf(range.article)
        if (articleStart > range.start) deletions += DdlSourceChange(range.start, articleStart, "")
        val articleEnd = articleStart + range.article.length
        if (articleEnd < nameStart) deletions += DdlSourceChange(articleEnd, nameStart, "")
        deletions += DdlSourceChange(nameStart + range.name.length, range.end, "")
    }
    val projection = DdlEditorProjection(snapshot.source, deletions.sortedBy { it.start }, emptyList())
    return DdlEditorProjection(snapshot.source, projection.deletions, ranges.map { range ->
        val nameStart = range.nameStart(snapshot.source)
        DdlEditorLabel(range, projection.displayOffset(nameStart), projection.displayOffset(nameStart + range.name.length),
            range.foldable || open(range))
    })
}

internal data class DdlEditorRangeStatus(
    val active: DdlNamedRange? = null,
    val bounds: DdlRangeBounds? = null,
    val invalid: Boolean = false,
)

internal data class DdlEditorUpdate(
    val snapshot: DdlEditorSnapshot,
    val names: List<DdlSourceChange>,
    val status: DdlEditorRangeStatus,
) {
    fun applyTo(buffer: TextFieldBuffer) {
        names.asReversed().forEach { buffer.replace(it.start, it.end, it.replacement) }
    }
}

/** Track incomplete edits and defer name changes until both the caret and IME leave them. */
internal class DdlRangeEditorSession(private val table: CompositionRangeTable) {
    private var previous: DdlEditorSnapshot? = null
    private var status = DdlEditorRangeStatus()
    private var pendingNames = emptySet<Int>()

    fun reset() {
        previous = null
        status = DdlEditorRangeStatus()
        pendingNames = emptySet()
    }

    fun update(snapshot: DdlEditorSnapshot): DdlEditorUpdate {
        val change = previous?.let { DdlSourceChange.between(it.source, snapshot.source) }
        fun mapped(range: DdlNamedRange?) = range?.let {
            it.copy(start = change?.map(it.start) ?: it.start, end = change?.map(it.end, after = true) ?: it.end)
        }
        val oldActive = mapped(status.active)
        val ranges = ddlNamedRanges(snapshot.source, table)
        pendingNames = pendingNames.map { change?.map(it) ?: it }.toSet()
        if (change != null) {
            val oldRanges = previous?.let { ddlNamedRanges(it.source, table) }.orEmpty()
            oldRanges.forEach { old ->
                val start = change.map(old.start)
                val next = ranges.firstOrNull { it.start == start }
                if (next != null && old.name != next.name) pendingNames = pendingNames - start
                else if ((next != null && old.numbers != next.numbers) ||
                    (status.active?.start == old.start && change.start >= old.end - old.numbers.length && change.start < old.end)) {
                    pendingNames = pendingNames + start
                }
            }
        }

        val names = mutableListOf<DdlSourceChange>()
        if (snapshot.composition == null && snapshot.editable) {
            pendingNames.toList().forEach { start ->
                val range = ranges.firstOrNull { it.start == start }
                if (range != null && snapshot.focused && range.contains(snapshot.selection)) return@forEach
                range?.bounds?.let(table::at)?.words(range.language)?.let { name ->
                    if (name != range.name) {
                        val from = range.nameStart(snapshot.source)
                        names += DdlSourceChange(from, from + range.name.length, name)
                    }
                }
                pendingNames = pendingNames - start
            }
        }
        names.sortBy { it.start }
        var source = snapshot.source
        var selection = snapshot.selection
        var fallback = oldActive
        names.asReversed().forEach { edit ->
            source = source.replaceRange(edit.start, edit.end, edit.replacement)
            selection = TextRange(edit.map(selection.start, after = true), edit.map(selection.end, after = true))
            fallback = fallback?.let { it.copy(start = edit.map(it.start), end = edit.map(it.end, after = true)) }
            pendingNames = pendingNames.map { edit.map(it) }.toSet()
        }
        val updated = snapshot.copy(source = source, selection = selection)
        val finalRanges = if (names.isEmpty()) ranges else ddlNamedRanges(source, table)
        val active = if (!snapshot.focused) null else finalRanges.firstOrNull { it.contains(selection) }
            ?: fallback?.takeIf { candidate ->
                finalRanges.none { it.start == candidate.start } && candidate.end > candidate.start &&
                    (candidate.contains(selection) || (selection.collapsed && selection.start == candidate.end))
            }?.copy(bounds = null, foldable = false)
        val bounds = active?.bounds ?: status.bounds.takeIf { active != null && active.start == fallback?.start }
        status = DdlEditorRangeStatus(active, bounds, finalRanges.any { it.bounds == null } || (active != null && active.bounds == null))
        previous = updated
        return DdlEditorUpdate(updated, names, status)
    }
}
