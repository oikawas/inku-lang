package app.inku.mobile.ui

import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.input.pointer.PointerEventType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.TextStyle
import app.inku.mobile.ui.i18n.LocalStrings
import app.inku.mobile.ui.i18n.LocalUiLanguage
import app.inku.mobile.ui.theme.Dimens
import app.inku.mobile.ui.theme.PillInkOnDark
import app.inku.mobile.ui.theme.PillInkOnLight

internal val LocalCompositionRangeTable = staticCompositionLocalOf { CompositionRangeTable.Empty }
internal val LocalDdlRangePreview = staticCompositionLocalOf<(DdlRangePreview?) -> Unit> { {} }

/** A display projection; the copy/export/full editor keep using [source]. */
@Composable
internal fun RangeDdlText(
    source: String,
    modifier: Modifier = Modifier,
    style: TextStyle = MaterialTheme.typography.bodySmall,
    onEditSource: ((String) -> Unit)? = null,
    onOpenEditor: (() -> Unit)? = null,
    enabled: Boolean = true,
    preview: @Composable ((DdlRangeBounds?) -> Unit)? = null,
) {
    val table = LocalCompositionRangeTable.current
    val showPreview = LocalDdlRangePreview.current
    val strings = LocalStrings.current
    val tokens = rememberDdlVocabularyTokens(LocalUiLanguage.current)
    val placeColor = tokens.firstOrNull { it.group.key == "basho" }?.color ?: MaterialTheme.colorScheme.primaryContainer
    val placeInk = if (isLightColor(placeColor)) PillInkOnLight else PillInkOnDark
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    var edit by remember { mutableStateOf<DdlRangeEdit?>(null) }
    var hoveredBounds by remember { mutableStateOf<DdlRangeBounds?>(null) }
    var layout by remember { mutableStateOf<TextLayoutResult?>(null) }
    LaunchedEffect(source) {
        if (edit?.source != source) edit = null
        hoveredBounds = null
    }
    val display = remember(source, table, edit?.range?.start) { displayDdlRanges(source, table, edit?.range?.start) }
    val text = remember(display, tokens, placeInk, muted) {
        val highlighted = DdlKeywordHighlightTransformation(tokens).filter(AnnotatedString(display.text)).text
        AnnotatedString.Builder(highlighted).apply {
            display.spans.forEach { span ->
                addStyle(SpanStyle(color = placeInk), span.start, span.nameEnd)
                if (!span.folded) addStyle(SpanStyle(color = muted), span.nameEnd, span.end)
            }
        }.toAnnotatedString()
    }
    fun at(position: Offset): RangeDisplaySpan? {
        val result = layout ?: return null
        if (position.y < 0 || position.y > result.size.height) return null
        val offset = result.getOffsetForPosition(position)
        return display.spans.firstOrNull { offset in it.start until it.end &&
            result.getBoundingBox(offset).let { box -> position.x >= box.left && position.x <= box.right && position.y >= box.top && position.y <= box.bottom } }
    }
    fun show(bounds: DdlRangeBounds?, draft: String = source) {
        showPreview(bounds?.let { DdlRangePreview(draft, it) })
    }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
        Text(
            text = text,
            style = style,
            modifier = Modifier.fillMaxWidth()
                .pointerInput(display, enabled) {
                    detectTapGestures(onTap = { position ->
                        val range = at(position)?.range
                        if (range != null && enabled) {
                            edit = DdlRangeEdit.open(source, range)
                            show(range.bounds)
                        } else if (enabled) onOpenEditor?.invoke()
                    })
                }
                .pointerInput(display) {
                    awaitPointerEventScope {
                        while (true) {
                            val event = awaitPointerEvent()
                            when (event.type) {
                                PointerEventType.Enter, PointerEventType.Move -> {
                                    hoveredBounds = event.changes.firstOrNull()?.position?.let { at(it)?.range?.bounds }
                                    show(hoveredBounds ?: edit?.lastValidBounds)
                                }
                                PointerEventType.Exit -> {
                                    hoveredBounds = null
                                    show(edit?.lastValidBounds)
                                }
                            }
                        }
                    }
                }
                .drawBehind {
                    val result = layout ?: return@drawBehind
                    drawDdlKeywordHighlights(result, display.text, tokens)
                    display.spans.forEach { span ->
                        var start = span.start
                        while (start < span.nameEnd) {
                            val line = result.getLineForOffset(start)
                            val end = minOf(span.nameEnd, result.getLineEnd(line))
                            if (end <= start) break
                            val first = result.getBoundingBox(start)
                            val last = result.getBoundingBox(end - 1)
                            drawRect(placeColor, Offset(first.left, first.top), Size(last.right - first.left, first.bottom - first.top))
                            if (span.folded || edit?.range?.start == span.range.start) drawLine(
                                placeInk, Offset(first.left, first.bottom), Offset(last.right, last.bottom),
                                strokeWidth = Dimens.hairline.toPx(), cap = StrokeCap.Round,
                                pathEffect = PathEffect.dashPathEffect(floatArrayOf(1f, 5f)),
                            )
                            start = end
                        }
                    }
                },
            onTextLayout = { layout = it },
        )
        if (edit != null || hoveredBounds != null) preview?.invoke(hoveredBounds ?: edit?.lastValidBounds)
        edit?.let { current ->
            if (onEditSource != null) {
                OutlinedTextField(
                    value = current.numbers,
                    onValueChange = { value ->
                        val next = current.update(value, table)
                        edit = next
                        onEditSource(next.source)
                        show(next.lastValidBounds, next.source)
                    },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text(strings.rangeNumbers) },
                    textStyle = style.copy(color = muted),
                    isError = !current.valid,
                    supportingText = { Text(if (current.valid) strings.rangeEditNote else strings.rangeInvalid) },
                    enabled = enabled,
                    singleLine = true,
                )
            }
            TextButton(onClick = {
                edit = null
                show(null)
            }) { Text(strings.rangeClose) }
        }
    }
}
