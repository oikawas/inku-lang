package app.inku.mobile.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.PressInteraction
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.input.OutputTransformation
import androidx.compose.foundation.text.input.TextFieldLineLimits
import androidx.compose.foundation.text.input.TextFieldState
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.TextRange
import app.inku.mobile.ui.theme.Dimens
import app.inku.mobile.ui.theme.InputWellSurface
import app.inku.mobile.ui.theme.LocalUiTextScale
import app.inku.mobile.ui.theme.PillInkOnDark
import app.inku.mobile.ui.theme.PillInkOnLight
import app.inku.mobile.ui.theme.TypeScale
import kotlinx.coroutines.yield

/** One native text field: raw text, IME and selections remain in TextFieldState. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun DdlRangeEditor(
    state: TextFieldState,
    focused: Boolean,
    onFocusChanged: (Boolean) -> Unit,
    tokens: List<DdlVocabularyToken>,
    modifier: Modifier = Modifier,
    readOnly: Boolean = false,
    onWordTap: () -> Unit = {},
) {
    val table = LocalCompositionRangeTable.current
    val focusRequester = remember { FocusRequester() }
    val bringIntoView = remember { BringIntoViewRequester() }
    val scope = rememberCoroutineScope()
    val interaction = remember { MutableInteractionSource() }
    val scroll = rememberScrollState()
    var getLayout by remember { mutableStateOf<(() -> TextLayoutResult?)?>(null) }
    val snapshot = DdlEditorSnapshot(state.text.toString(), state.selection, state.composition, focused, !readOnly)
    val projection = remember(snapshot, table) { ddlEditorProjection(snapshot, table) }
    val currentProjection by rememberUpdatedState(projection)
    val currentFocused by rememberUpdatedState(focused)
    val wordTap by rememberUpdatedState(onWordTap)
    val placeColor = tokens.firstOrNull { it.group.key == "basho" }?.color ?: MaterialTheme.colorScheme.primaryContainer
    val placeInk = if (isLightColor(placeColor)) PillInkOnLight else PillInkOnDark
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    val output = remember(state, table, tokens, placeColor, placeInk, muted) {
        OutputTransformation {
            val displayed = ddlEditorProjection(DdlEditorSnapshot(
                state.text.toString(), state.selection, state.composition, currentFocused,
            ), table)
            displayed.applyTo(this)
            val text = asCharSequence().toString()
            val occupied = BooleanArray(text.length)
            tokens.forEach { token ->
                if (token.word.isEmpty()) return@forEach
                var start = text.indexOf(token.word)
                while (start >= 0) {
                    val end = start + token.word.length
                    if ((start until end).none { occupied[it] }) {
                        addStyle(SpanStyle(
                            background = token.color,
                            color = if (isLightColor(token.color)) PillInkOnLight else PillInkOnDark,
                        ), start, end)
                        for (index in start until end) occupied[index] = true
                    }
                    start = text.indexOf(token.word, end)
                }
            }
            displayed.labels.forEach { label ->
                addStyle(SpanStyle(background = placeColor, color = placeInk), label.start, label.end)
                val start = displayed.displayOffset(label.range.end - label.range.numbers.length)
                val end = displayed.displayOffset(label.range.end)
                if (end > start) {
                    addStyle(SpanStyle(color = muted), start, end)
                }
            }
        }
    }

    // Observe the field's own press interactions; do not intercept selection drags or IME gestures.
    LaunchedEffect(state, interaction) {
        var pressed: Pair<String, DdlNamedRange?>? = null
        interaction.interactions.collect { event ->
            when (event) {
                is PressInteraction.Press -> {
                    val layout = getLayout?.invoke()
                    val point = event.pressPosition + Offset(0f, scroll.value.toFloat())
                    val label = layout?.let { result ->
                        if (point.y < 0 || point.y >= result.size.height) null else {
                            val offset = result.getOffsetForPosition(point)
                            currentProjection.labels.firstOrNull { candidate ->
                                candidate.end <= result.layoutInput.text.length &&
                                    offset in candidate.start until candidate.end &&
                                    result.getBoundingBox(offset).let { box -> point.x in box.left..box.right && point.y in box.top..box.bottom }
                            }
                        }
                    }
                    pressed = currentProjection.source to label?.range
                }
                is PressInteraction.Release -> {
                    val tap = pressed
                    pressed = null
                    yield()
                    if (tap != null && state.composition == null && state.text.toString() == tap.first) {
                        val range = tap.second
                        if (range != null) {
                            focusRequester.requestFocus()
                            state.edit { selection = TextRange(range.end - range.numbers.length + 1) }
                        } else if (currentProjection.labels.none { it.range.contains(state.selection) }) wordTap()
                    }
                }
                is PressInteraction.Cancel -> pressed = null
            }
        }
    }
    Box(modifier
        .bringIntoViewRequester(bringIntoView)
        .background(InputWellSurface, RoundedCornerShape(Dimens.radiusCard))
        .border(Dimens.hairline, MaterialTheme.colorScheme.outline, RoundedCornerShape(Dimens.radiusCard))
        .padding(horizontal = Dimens.spaceM, vertical = Dimens.spaceXs)) {
        BasicTextField(
            state = state,
            readOnly = readOnly,
            modifier = Modifier.fillMaxSize().focusRequester(focusRequester)
                .onFocusChanged {
                    onFocusChanged(it.isFocused)
                    if (it.isFocused) scope.launchImeBringIntoViewGuard(bringIntoView)
                }
                .drawWithContent {
                    drawContent()
                    val layout = getLayout?.invoke() ?: return@drawWithContent
                    projection.labels.filter { it.dotted }.forEach { label ->
                        if (label.end > layout.layoutInput.text.length) return@forEach
                        var start = label.start
                        while (start < label.end) {
                            val line = layout.getLineForOffset(start)
                            val end = minOf(label.end, layout.getLineEnd(line, visibleEnd = true))
                            if (end <= start) break
                            val first = layout.getBoundingBox(start)
                            val last = layout.getBoundingBox(end - 1)
                            val y = first.bottom - scroll.value
                            drawLine(placeInk, Offset(first.left, y), Offset(last.right, y),
                                strokeWidth = Dimens.hairline.toPx(), cap = StrokeCap.Round,
                                pathEffect = PathEffect.dashPathEffect(floatArrayOf(1f, 5f)))
                            start = end
                        }
                    }
                },
            textStyle = MaterialTheme.typography.bodySmall.copy(
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = TypeScale.editorBody * LocalUiTextScale.current,
                lineHeight = TypeScale.editorLineHeight * LocalUiTextScale.current,
            ),
            cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
            outputTransformation = output,
            onTextLayout = { getLayout = it },
            interactionSource = interaction,
            lineLimits = TextFieldLineLimits.MultiLine(minHeightInLines = 1),
            scrollState = scroll,
        )
    }
}
