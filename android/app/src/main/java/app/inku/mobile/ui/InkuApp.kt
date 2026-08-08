package app.inku.mobile.ui

import app.inku.mobile.ui.mascot.MascotArt
import app.inku.mobile.ui.theme.*
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.tween
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.Easing
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.graphics.drawscope.withTransform
import android.content.Context
import android.content.Intent
import android.content.ClipData
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas as AndroidCanvas
import android.net.Uri
import android.util.LruCache
import android.view.OrientationEventListener
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.AssistChip
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.PlainTooltip
import androidx.compose.material3.TooltipBox
import androidx.compose.material3.TooltipDefaults
import androidx.compose.material3.rememberTooltipState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.PointerInputChange
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInWindow
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.OffsetMapping
import androidx.compose.ui.text.input.TransformedText
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.platform.testTag
import androidx.core.content.FileProvider
import app.inku.mobile.BuildConfig
import app.inku.mobile.data.db.ExportTemplateEntity
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.HistoryListItem
import app.inku.mobile.data.lineage.LineageGraphNode
import app.inku.mobile.data.lineage.LineageGraphResult
import app.inku.mobile.data.refinement.ComparisonPlanner
import app.inku.mobile.data.refinement.LanguageCombo
import app.inku.mobile.data.refinement.ModelCompareMode
import app.inku.mobile.data.refinement.RefinementElement
import app.inku.mobile.data.refinement.RefinementPlanner
import app.inku.mobile.data.refinement.VariationAmplitude
import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.DerivationKindRegistry
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.CompatibilityConstants
import app.inku.mobile.pipeline.InstructionLanguages
import app.inku.mobile.pipeline.Sketches
import app.inku.mobile.pipeline.WebDdlSpec
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import kotlin.math.abs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import com.caverock.androidsvg.SVG
import org.json.JSONArray
import org.json.JSONObject

private const val HISTORY_SWIPE_MIN_DISTANCE_PX = 96f
private const val HISTORY_SWIPE_AXIS_LOCK = 1.6f

/** How often the running row redraws its elapsed time. */
private const val RUN_STATUS_TICK_MS = 100L

/** The description field. The instrumented IME test needs to reach it by name. */
internal const val DESCRIPTION_INPUT_TAG = "description_input"

/** What the main action says, in both the in-flow button and the IME bar. */
internal const val DRAW_ACTION_LABEL = "描画する"

/**
 * What the double tap goes to when the artwork is already at or above its own
 * size, so that 1:1 would be a zoom *out* and the gesture would look broken.
 */
private const val PRESENTATION_FALLBACK_ZOOM = 2.0f
private const val PRESENTATION_PREFS_NAME = "presentation_preferences"
private const val PRESENTATION_CAPTION_VISIBLE_KEY = "caption_visible"
private val SvgViewBoxRegex = Regex("""\bviewBox\s*=\s*["']\s*[-+]?[0-9.]+\s+[-+]?[0-9.]+\s+([-+]?[0-9.]+)\s+([-+]?[0-9.]+)\s*["']""")
private val SvgWidthRegex = Regex("""\bwidth\s*=\s*["']\s*([-+]?[0-9.]+)""")
private val SvgHeightRegex = Regex("""\bheight\s*=\s*["']\s*([-+]?[0-9.]+)""")

private enum class DeviceRotation {
    Portrait,
    LandscapeLeft,
    ReversePortrait,
    LandscapeRight,
}

private val DeviceRotation.clockwiseDegrees: Int
    get() = when (this) {
        DeviceRotation.Portrait -> 0
        DeviceRotation.LandscapeLeft -> 90
        DeviceRotation.ReversePortrait -> 180
        DeviceRotation.LandscapeRight -> 270
    }

internal data class SaijikiGroup(val label: String, val en: String, val words: List<String>)
private data class DdlVocabularyToken(val word: String, val group: SaijikiGroup, val color: Color)
private data class ModelChoice(val id: String, val label: String, val providerName: String)
private data class ModelOptionChoice(val rawId: String, val qualifiedId: String, val label: String, val notes: String? = null)
private data class ProviderModelCandidate(val id: String, val label: String, val notes: String? = null)

private object HistoryThumbnailCache {
    private const val THUMBNAIL_PX = 384
    private const val MAX_CACHE_KB = 24 * 1024
    private val cache = object : LruCache<String, ImageBitmap>(MAX_CACHE_KB) {
        override fun sizeOf(key: String, value: ImageBitmap): Int {
            return ((value.width.toLong() * value.height.toLong() * 4L) / 1024L).coerceAtLeast(1L).toInt()
        }
    }

    suspend fun get(context: Context, renderHash: String, thumbnailPath: String?): ImageBitmap? {
        val key = "$renderHash:$THUMBNAIL_PX"
        synchronized(cache) {
            cache.get(key)?.let { return it }
        }
        return withContext(Dispatchers.Default) {
            val rendered = thumbnailPath
                ?.takeIf { isAppThumbnailPath(context, it) }
                ?.let { path -> runCatching { BitmapFactory.decodeFile(path)?.asImageBitmap() }.getOrNull() }
            if (rendered != null) {
                synchronized(cache) {
                    cache.put(key, rendered)
                }
            }
            rendered
        }
    }

    private fun isAppThumbnailPath(context: Context, path: String): Boolean {
        return runCatching {
            val root = File(context.filesDir, "thumbnails").canonicalFile
            val target = File(path).canonicalFile
            target.path.startsWith(root.path + File.separator)
        }.getOrDefault(false)
    }
}

private object ArtworkBitmapCache {
    private const val MAX_RENDER_PX = 2048
    private const val MAX_CACHE_KB = 64 * 1024
    private val cache = object : LruCache<String, ImageBitmap>(MAX_CACHE_KB) {
        override fun sizeOf(key: String, value: ImageBitmap): Int {
            return ((value.width.toLong() * value.height.toLong() * 4L) / 1024L).coerceAtLeast(1L).toInt()
        }
    }

    suspend fun get(item: HistoryItemEntity, size: IntSize, rotationDegrees: Int): ImageBitmap? {
        if (size.width <= 0 || size.height <= 0) return null
        val scale = minOf(1f, MAX_RENDER_PX.toFloat() / maxOf(size.width, size.height).toFloat())
        val width = maxOf(1, (size.width * scale).toInt())
        val height = maxOf(1, (size.height * scale).toInt())
        val key = "${item.renderHash}:$width:$height:${rotationDegrees.floorMod360()}"
        synchronized(cache) {
            cache.get(key)?.let { return it }
        }
        return withContext(Dispatchers.Default) {
            val rendered = renderArtworkBitmap(item.displaySvg, width, height, rotationDegrees)
            if (rendered != null) {
                synchronized(cache) {
                    cache.put(key, rendered)
                }
            }
            rendered
        }
    }

    private fun renderArtworkBitmap(svgText: String, width: Int, height: Int, rotationDegrees: Int): ImageBitmap? {
        return runCatching {
            val parsed = SVG.getFromString(svgText)
            val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
            val native = AndroidCanvas(bitmap)
            renderSvgIntoNativeCanvas(parsed, native, width.toFloat(), height.toFloat(), rotationDegrees)
            bitmap.asImageBitmap()
        }.getOrNull()
    }
}

internal val saijikiGroups = listOf(
    SaijikiGroup("かたち", "forms", listOf("円", "楕円", "三角", "四角", "線", "弧")),
    SaijikiGroup("てざわり", "touches", listOf("鉛筆", "ペン", "ロットリング", "クレヨン", "チョーク", "細筆", "太筆", "ビュラン", "ドライポイント", "コンピュータ")),
    SaijikiGroup("つらなり", "continuity", listOf("実線", "破線", "点線", "一点鎖線")),
    SaijikiGroup("いろ", "colors", listOf("白", "黒", "青", "赤", "緑", "灰")),
    SaijikiGroup("ゆらぎ", "movements", listOf("細かく", "大きく", "ゆっくり", "速く", "揺れる", "波打つ", "震える", "滲む")),
    SaijikiGroup("ばしょ", "places", listOf("上", "下", "中央", "左端", "右端", "上端", "下端", "中心", "隅")),
    SaijikiGroup("うごき", "motions", listOf("置く", "並べる", "埋める", "散らす", "引く")),
    SaijikiGroup("かたむき", "angles", listOf("水平", "垂直", "斜め", "右上がり", "右下がり", "回転")),
    SaijikiGroup("わりあい", "proportions", listOf("縦長", "横長", "全幅", "半幅", "半円", "上弦", "下弦", "三日月")),
)

private val saijikiGroupColors = listOf(
    SaijikiGroupSand,
    SaijikiGroupSky,
    SaijikiGroupLeaf,
    SaijikiGroupClay,
    SaijikiGroupIris,
    SaijikiGroupMint,
    SaijikiGroupAmber,
    SaijikiGroupSlate,
    SaijikiGroupBlossom,
)

@Composable
fun InkuApp() {
    val viewModel: InkuViewModel = androidx.lifecycle.viewmodel.compose.viewModel()
    val state by viewModel.state.collectAsState()
    val deviceRotation = rememberDeviceRotation(enabled = state.canvasPresentationMode)

    // One back key, one destination per screen state. Android's back always means
    // "up one level"; before this it meant "leave the app" from everywhere except
    // a dialog, so the full screen and the four tabs were one-way doors.
    val backTarget: (() -> Unit)? = when {
        state.canvasPresentationMode -> viewModel::exitCanvasPresentationMode
        state.confirmDdlOverwrite -> viewModel::cancelDdlOverwrite
        state.ddlEditorOpen -> viewModel::closeDdlEditor
        state.modelSelectionOpen -> viewModel::cancelModelSelection
        state.catalogSelectionOpen -> viewModel::cancelCatalogSelection
        state.canvasSelectionOpen -> viewModel::closeTransientPanel
        state.tab == AppTab.Settings && state.settingsPane != SettingsPane.Home ->
            ({ viewModel.setSettingsPane(SettingsPane.Home) })
        state.tab != AppTab.Compose -> ({ viewModel.setTab(AppTab.Compose) })
        // The compose screen is the root. Back leaves the app from here.
        else -> null
    }
    BackHandler(enabled = backTarget != null) { backTarget?.invoke() }

    MaterialTheme(colorScheme = InkuColors) {
        Scaffold(
            bottomBar = {
                // While the description is being written the four destinations
                // step aside: keeping them would hold a bar's worth of height
                // between the keyboard and 「描画する」, and going somewhere else
                // is not what one is about to do mid-sentence.
                if (!state.canvasPresentationMode && !state.descriptionFocused) {
                    BottomNavigationBar(state.tab, viewModel)
                }
            },
            containerColor = MaterialTheme.colorScheme.background,
        ) { padding ->
            val contentPadding = if (state.canvasPresentationMode) PaddingValues(0.dp) else padding
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(contentPadding)
                    // `contentPadding` already holds the navigation bar, so
                    // without this `imePadding` adds the keyboard on top of an
                    // inset the keyboard covers -- a bar's worth of dead space
                    // between the content and the keys.
                    .consumeWindowInsets(contentPadding)
                    .imePadding()
                    .background(MaterialTheme.colorScheme.background),
            ) {
                if (state.canvasPresentationMode) {
                    CanvasHeroCard(state, viewModel, modifier = Modifier.fillMaxSize(), deviceRotation = deviceRotation)
                } else {
                    when (state.tab) {
                        AppTab.Compose -> ComposeScreen(state, viewModel)
                        AppTab.History -> {
                            val history by viewModel.historyItems.collectAsState()
                            HistoryScreen(state, history, viewModel)
                        }
                        AppTab.Lineage -> LineageScreen(state, viewModel)
                        AppTab.Settings -> SettingsPanel(state, viewModel, modifier = Modifier.fillMaxSize().padding(Dimens.spaceL))
                    }
                }
                if (state.confirmDdlOverwrite) {
                    DdlOverwriteDialog(viewModel)
                }
                if (state.ddlEditorOpen) {
                    DdlEditorDialog(state, viewModel)
                }
                if (state.modelSelectionOpen) {
                    ModelSelectionDialog(state, viewModel)
                }
                if (state.catalogSelectionOpen) {
                    ColorCatalogSelectionDialog(state, viewModel)
                }
                if (state.canvasSelectionOpen) {
                    CanvasAspectSelectionDialog(state, viewModel)
                }
            }
        }
    }
}

@Composable
private fun DdlOverwriteDialog(viewModel: InkuViewModel) {
    AlertDialog(
        onDismissRequest = viewModel::cancelDdlOverwrite,
        title = { Text("DDLの編集結果が失われます") },
        text = { Text("通常の描画を実行すると、現在の解釈（正規化DDL）は Stage 1 の結果で上書きされます。") },
        confirmButton = {
            TextButton(onClick = viewModel::confirmDdlOverwriteRegenerate) {
                Text("OK")
            }
        },
        dismissButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                TextButton(onClick = viewModel::cancelDdlOverwrite) {
                    Text("キャンセル")
                }
                TextButton(onClick = viewModel::confirmDdlOverwriteRenderEdited) {
                    Text("DDLから描画")
                }
            }
        },
    )
}

@Composable
private fun DdlEditorDialog(state: InkuUiState, viewModel: InkuViewModel) {
    var editorValue by remember {
        mutableStateOf(TextFieldValue(state.ddl, selection = TextRange(state.ddl.length)))
    }
    var vocabularyOpen by remember { mutableStateOf(false) }
    var vocabularyQuery by remember { mutableStateOf("") }
    val vocabularyTokens = rememberDdlVocabularyTokens()
    val allVocabularyWords = remember(vocabularyTokens) { vocabularyTokens.map { it.word } }
    val detectedWords = remember(editorValue.text) {
        vocabularyTokens.filter { editorValue.text.contains(it.word) }
    }
    val selectedWord = remember(editorValue.selection, editorValue.text, vocabularyTokens) {
        selectedVocabularyToken(editorValue, vocabularyTokens)
    }
    val filteredGroups = remember(vocabularyQuery) {
        val query = vocabularyQuery.trim()
        if (query.isBlank()) {
            saijikiGroups
        } else {
            saijikiGroups.mapNotNull { group ->
                val words = group.words.filter { word ->
                    word.contains(query, ignoreCase = true) ||
                        group.label.contains(query, ignoreCase = true) ||
                        group.en.contains(query, ignoreCase = true)
                }
                if (words.isEmpty()) null else group.copy(words = words)
            }
        }
    }
    fun updateEditor(value: TextFieldValue) {
        editorValue = value
        viewModel.setDdl(value.text)
    }
    fun insertVocabulary(word: String) {
        updateEditor(insertWordAtSelection(editorValue, word))
    }
    fun selectVocabulary(word: String) {
        updateEditor(selectNextWordOccurrence(editorValue, word))
    }
    Dialog(
        onDismissRequest = viewModel::closeDdlEditor,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Surface(
            modifier = Modifier
                .fillMaxSize()
                .imePadding()
                .padding(Dimens.spaceL),
            shape = RoundedCornerShape(Dimens.radiusCard),
            color = MaterialTheme.colorScheme.surface,
            tonalElevation = Dimens.spaceM,
        ) {
            Column(
                modifier = Modifier.fillMaxSize().padding(Dimens.spaceM),
                verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                ) {
                    Text("DDL編集", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = viewModel::closeDdlEditor) {
                        Text("閉じる")
                    }
                    TextButton(
                        onClick = {
                            viewModel.closeDdlEditor()
                            viewModel.drawFromDdl()
                        },
                        enabled = !state.isDrawing,
                    ) {
                        Text("描画")
                    }
                }
                DdlSelectedVocabularyHeader(selectedWord)
                DenseTextFieldValueInput(
                    value = editorValue,
                    onValueChange = ::updateEditor,
                    modifier = Modifier.fillMaxWidth().weight(1f),
                    minLines = 20,
                    maxLines = 80,
                    enabled = !state.isDrawing,
                    highlightTokens = vocabularyTokens,
                    selectWords = allVocabularyWords,
                )
                DdlVocabularyBar(
                    open = vocabularyOpen,
                    query = vocabularyQuery,
                    groups = filteredGroups,
                    detectedWords = detectedWords,
                    selectedWord = selectedWord,
                    tokenForWord = { word -> vocabularyTokens.firstOrNull { it.word == word } },
                    onToggle = { vocabularyOpen = !vocabularyOpen },
                    onQueryChange = { vocabularyQuery = it },
                    onInsert = ::insertVocabulary,
                    onSelectDetected = ::selectVocabulary,
                )
            }
        }
    }
}

@Composable
private fun rememberDdlVocabularyTokens(): List<DdlVocabularyToken> {
    return remember {
        saijikiGroups.flatMapIndexed { index, group ->
            group.words.map { word ->
                DdlVocabularyToken(word = word, group = group, color = saijikiGroupColors[index % saijikiGroupColors.size])
            }
        }.distinctBy { it.word }.sortedByDescending { it.word.length }
    }
}

@Composable
private fun DdlSelectedVocabularyHeader(selectedWord: DdlVocabularyToken?) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
    ) {
        Text(
            "選択中",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (selectedWord != null) {
            DdlVocabularyPill(token = selectedWord, selected = true, onClick = {})
            Text(
                "候補タップで置換",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            Text(
                "本文の歳時記語をタップ",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

private fun insertWordAtSelection(value: TextFieldValue, word: String): TextFieldValue {
    val start = minOf(value.selection.start, value.selection.end).coerceIn(0, value.text.length)
    val end = maxOf(value.selection.start, value.selection.end).coerceIn(0, value.text.length)
    val prefix = value.text.substring(0, start)
    val suffix = value.text.substring(end)
    val leading = if (prefix.isBlank() || prefix.endsWith(" ") || prefix.endsWith("\n")) "" else " "
    val trailing = if (suffix.isBlank() || suffix.startsWith(" ") || suffix.startsWith("\n")) "" else " "
    val inserted = leading + word + trailing
    val nextText = prefix + inserted + suffix
    val cursor = (prefix.length + inserted.length).coerceIn(0, nextText.length)
    return TextFieldValue(nextText, selection = TextRange(cursor))
}

private fun selectNextWordOccurrence(value: TextFieldValue, word: String): TextFieldValue {
    if (word.isBlank() || value.text.isBlank()) return value
    val from = maxOf(value.selection.end, 0).coerceAtMost(value.text.length)
    val next = value.text.indexOf(word, startIndex = from).takeIf { it >= 0 }
        ?: value.text.indexOf(word).takeIf { it >= 0 }
        ?: return value
    return value.copy(selection = TextRange(next, next + word.length))
}

private fun selectVocabularyAtOffset(value: TextFieldValue, offset: Int, words: List<String>): TextFieldValue {
    if (value.text.isBlank()) return value
    val caret = offset.coerceIn(0, value.text.length)
    val match = words.firstNotNullOfOrNull { word ->
        if (word.isBlank()) return@firstNotNullOfOrNull null
        var start = value.text.indexOf(word)
        while (start >= 0) {
            val end = start + word.length
            if (caret in start..end) return@firstNotNullOfOrNull start to end
            start = value.text.indexOf(word, startIndex = end)
        }
        null
    } ?: return value
    return value.copy(selection = TextRange(match.first, match.second))
}

private fun selectedVocabularyToken(value: TextFieldValue, tokens: List<DdlVocabularyToken>): DdlVocabularyToken? {
    if (value.selection.collapsed) return null
    val start = minOf(value.selection.start, value.selection.end).coerceIn(0, value.text.length)
    val end = maxOf(value.selection.start, value.selection.end).coerceIn(0, value.text.length)
    val selected = value.text.substring(start, end)
    return tokens.firstOrNull { it.word == selected }
}

@Composable
private fun DdlVocabularyBar(
    open: Boolean,
    query: String,
    groups: List<SaijikiGroup>,
    detectedWords: List<DdlVocabularyToken>,
    selectedWord: DdlVocabularyToken?,
    tokenForWord: (String) -> DdlVocabularyToken?,
    onToggle: () -> Unit,
    onQueryChange: (String) -> Unit,
    onInsert: (String) -> Unit,
    onSelectDetected: (String) -> Unit,
) {
    val alternativeTokens = remember(selectedWord) {
        selectedWord?.let { selected ->
            selected.group.words
                .filter { it != selected.word }
                .mapNotNull(tokenForWord)
        }.orEmpty()
    }
    val prioritizedDetectedWords = remember(detectedWords, selectedWord, alternativeTokens) {
        if (selectedWord == null) {
            detectedWords
        } else {
            (alternativeTokens + detectedWords)
                .distinctBy { it.word }
                .filter { it.word != selectedWord.word }
        }
    }
    val prioritizedGroups = remember(groups, selectedWord) {
        if (selectedWord == null) {
            groups
        } else {
            groups.sortedWith(
                compareByDescending<SaijikiGroup> { it.label == selectedWord.group.label }
                    .thenBy { group -> saijikiGroups.indexOfFirst { it.label == group.label }.let { if (it < 0) Int.MAX_VALUE else it } },
            )
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
        ) {
            MiniPill(if (open) "素材を閉じる" else "素材", selected = open, onClick = onToggle)
            if (selectedWord != null) {
                DdlVocabularyPill(token = selectedWord, selected = true, onClick = { onSelectDetected(selectedWord.word) })
                Text("を置換", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                Text(
                    "本文の語をタップで選択",
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        if (prioritizedDetectedWords.isNotEmpty()) {
            WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
                prioritizedDetectedWords.take(12).forEach { token ->
                    DdlVocabularyPill(token = token, selected = token.word == selectedWord?.word, onClick = { onSelectDetected(token.word) })
                }
            }
        }
        if (open) {
            Surface(
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(Dimens.radiusCard),
                modifier = Modifier.fillMaxWidth().heightIn(max = Dimens.vocabularyBarMaxHeight),
            ) {
                Column(
                    modifier = Modifier.padding(Dimens.spaceM).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                ) {
                    DenseSingleLineInput(
                        value = query,
                        onValueChange = onQueryChange,
                        placeholder = "検索",
                        modifier = Modifier.fillMaxWidth(),
                    )
                    prioritizedGroups.forEach { group ->
                        Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                            Text(
                                if (selectedWord?.group?.label == group.label) "${group.label} / 代替候補" else group.label,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
                                group.words.forEach { word ->
                                    val token = tokenForWord(word)
                                    if (token != null) {
                                        DdlVocabularyPill(token = token, onClick = { onInsert(word) })
                                    } else {
                                        MiniPill(word, onClick = { onInsert(word) })
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DdlVocabularyPill(token: DdlVocabularyToken, selected: Boolean = false, onClick: () -> Unit) {
    val background = if (selected) token.color else token.color.copy(alpha = 0.84f)
    val foreground = if (isLightColor(background)) PillInkOnLight else PillInkOnDark
    Text(
        token.word,
        modifier = Modifier
            .background(background, RoundedCornerShape(100))
            .clickable(onClick = onClick)
            .padding(horizontal = Dimens.spaceXs, vertical = Dimens.spaceXs),
        style = MaterialTheme.typography.labelSmall,
        color = foreground,
        maxLines = 1,
    )
}

private fun isLightColor(color: Color): Boolean {
    val luminance = (0.2126f * color.red) + (0.7152f * color.green) + (0.0722f * color.blue)
    return luminance >= 0.58f
}

@Composable
private fun ModelSelectionDialog(state: InkuUiState, viewModel: InkuViewModel) {
    AlertDialog(
        onDismissRequest = viewModel::cancelModelSelection,
        title = { Text("モデル選択") },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth().heightIn(max = Dimens.modelDialogMaxHeight).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(Dimens.spaceL),
            ) {
                WebStyleModelStageEditor(
                    title = "描画モデル",
                    sub = "Stage 1 / Stage 2 共通",
                    state = state,
                    selectedModelId = state.selectedModelId,
                    onSelectModel = viewModel::setSelectedModel,
                )
                if (state.selectedModelId.contains("qwen3")) {
                    SettingCheckRow(
                        checked = state.includeThinking,
                        text = "思考を表示",
                        onCheckedChange = viewModel::setIncludeThinking,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = viewModel::confirmModelSelection) {
                Text("OK")
            }
        },
        dismissButton = {
            TextButton(onClick = viewModel::cancelModelSelection) {
                Text("キャンセル")
            }
        },
    )
}

@Composable
private fun ColorCatalogSelectionDialog(state: InkuUiState, viewModel: InkuViewModel) {
    val current = ColorCatalogs.get(state.selectedCatalogId)
    AlertDialog(
        onDismissRequest = viewModel::confirmCatalogSelection,
        title = { Text("色カタログ") },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth().height(Dimens.colorCatalogDialogHeight).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
            ) {
                ColorCatalogs.all.forEach { catalog ->
                    val active = catalog.id == state.selectedCatalogId
                    Surface(
                        modifier = Modifier.fillMaxWidth().clickable { viewModel.setCatalog(catalog.id) },
                        shape = RoundedCornerShape(Dimens.radiusCard),
                        color = if (active) ActiveRowTint else MaterialTheme.colorScheme.surface,
                    ) {
                        Row(
                            modifier = Modifier.padding(Dimens.spaceM),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                        ) {
                            SwatchStrip(catalog.swatches.take(8))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(catalog.name, style = MaterialTheme.typography.bodySmall)
                                Text(catalog.sub, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            if (active) Text("✓", color = MaterialTheme.colorScheme.secondary)
                        }
                    }
                }
                SettingsSectionHeader(current.name.uppercase(), "カタログ詳細")
                current.map.forEach { (name, code) ->
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                        Box(
                            modifier = Modifier
                                .size(Dimens.swatchSize)
                                .background(parseColor(code), RoundedCornerShape(100))
                                .border(Dimens.hairline, MaterialTheme.colorScheme.outline, RoundedCornerShape(100)),
                        )
                        Text(name, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                        Text(code, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = viewModel::confirmCatalogSelection) { Text("決定") }
        },
        dismissButton = {
            TextButton(onClick = viewModel::cancelCatalogSelection) { Text("キャンセル") }
        },
    )
}

@Composable
private fun CanvasAspectSelectionDialog(state: InkuUiState, viewModel: InkuViewModel) {
    AlertDialog(
        onDismissRequest = viewModel::closeTransientPanel,
        title = { Text("キャンバス") },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth().height(Dimens.aspectDialogHeight).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
            ) {
                CanvasAspects.all.forEach { aspect ->
                    val active = aspect.id == state.selectedCanvasAspect
                    Surface(
                        modifier = Modifier.fillMaxWidth().clickable {
                            viewModel.setCanvasAspect(aspect.id)
                            viewModel.closeTransientPanel()
                        },
                        shape = RoundedCornerShape(Dimens.radiusCard),
                        color = if (active) ActiveRowTint else MaterialTheme.colorScheme.surface,
                    ) {
                        Row(
                            modifier = Modifier.padding(Dimens.spaceM),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(Dimens.controlSizeSmall)
                                    .border(Dimens.hairline, MaterialTheme.colorScheme.onSurfaceVariant, RoundedCornerShape(100))
                                    .aspectRatio(aspect.ratioW.toFloat() / aspect.ratioH.toFloat()),
                            )
                            Column(modifier = Modifier.weight(1f)) {
                                Text(aspect.label, style = MaterialTheme.typography.bodySmall)
                                Text("${aspect.ratioW}:${aspect.ratioH}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            if (active) Text("✓", color = MaterialTheme.colorScheme.secondary)
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = viewModel::closeTransientPanel) { Text("閉じる") }
        },
    )
}

@Composable
private fun WebStyleModelStageEditor(
    title: String,
    sub: String,
    state: InkuUiState,
    selectedModelId: String,
    onSelectModel: (String) -> Unit,
) {
    val providers = modelProviderGroupsFor(state)
    val selectedProviderId = providerOfModelId(selectedModelId, state)
    val selectedProvider = providers.firstOrNull { it.providerId == selectedProviderId } ?: providers.firstOrNull()
    val models = modelOptionsForProvider(state, selectedProviderId)
    var providerMenuOpen by remember(title, selectedProviderId) { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
        SettingsSectionHeader(title.uppercase(), sub)
        CompactLabel("Provider")
        Box(modifier = Modifier.fillMaxWidth()) {
            Surface(
                modifier = Modifier.fillMaxWidth().clickable { providerMenuOpen = true },
                shape = RoundedCornerShape(Dimens.radiusCard),
                color = MaterialTheme.colorScheme.surface,
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().border(Dimens.hairline, MaterialTheme.colorScheme.outline, RoundedCornerShape(Dimens.radiusCard)).padding(horizontal = Dimens.spaceL, vertical = Dimens.spaceM),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                ) {
                    Text(selectedProvider?.displayName ?: selectedProviderId, style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("▼", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            DropdownMenu(
                expanded = providerMenuOpen,
                onDismissRequest = { providerMenuOpen = false },
                modifier = Modifier.fillMaxWidth(0.84f),
            ) {
                providers.forEach { provider ->
                    DropdownMenuItem(
                        text = {
                            Column {
                                Text(provider.displayName, style = MaterialTheme.typography.bodySmall)
                                Text(provider.providerId, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        },
                        onClick = {
                            providerMenuOpen = false
                            modelOptionsForProvider(state, provider.providerId).firstOrNull()?.let { option ->
                                onSelectModel(option.qualifiedId)
                            }
                        },
                    )
                }
            }
        }
        CompactLabel("Model")
        if (models.isEmpty()) {
            Text("公開モデルは未選択です。接続先設定でモデルを選択してください。", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                models.forEach { option ->
                    Surface(
                        modifier = Modifier.fillMaxWidth().clickable { onSelectModel(option.qualifiedId) },
                        shape = RoundedCornerShape(Dimens.radiusCard),
                        color = if (option.qualifiedId == selectedModelId) ActiveRowTint else MaterialTheme.colorScheme.surface,
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = Dimens.spaceM, vertical = Dimens.spaceM),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                        ) {
                            Text(if (option.qualifiedId == selectedModelId) "✓" else "", modifier = Modifier.width(Dimens.spaceL), color = MaterialTheme.colorScheme.secondary)
                            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                                Text(option.label, style = MaterialTheme.typography.bodySmall)
                                if (option.notes != null) {
                                    Text(option.notes, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SaijikiPanel(viewModel: InkuViewModel) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(Dimens.radiusCard),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(Dimens.spaceL), verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
            Text("歳時記", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Medium)
            Text("語を押すと DDL 編集欄へ挿入します。", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            saijikiGroups.forEach { group ->
                Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                    Text("${group.label} / ${group.en}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
                        group.words.forEach { word ->
                            MiniPill(word, onClick = { viewModel.insertDdlWord(word) })
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun rememberDeviceRotation(enabled: Boolean): DeviceRotation {
    val context = LocalContext.current
    var rotation by remember { mutableStateOf(DeviceRotation.Portrait) }
    DisposableEffect(context, enabled) {
        if (!enabled) {
            rotation = DeviceRotation.Portrait
            return@DisposableEffect onDispose { }
        }
        val listener = object : OrientationEventListener(context.applicationContext) {
            override fun onOrientationChanged(orientation: Int) {
                if (orientation == ORIENTATION_UNKNOWN) return
                rotation = when {
                    orientation >= 315 || orientation < 45 -> DeviceRotation.Portrait
                    orientation < 135 -> DeviceRotation.LandscapeLeft
                    orientation < 225 -> DeviceRotation.ReversePortrait
                    else -> DeviceRotation.LandscapeRight
                }
            }
        }
        if (listener.canDetectOrientation()) {
            listener.enable()
        }
        onDispose { listener.disable() }
    }
    return rotation
}

@Composable
private fun BottomNavigationBar(selected: AppTab, viewModel: InkuViewModel) {
    Surface(
        modifier = Modifier
            .navigationBarsPadding()
            .border(Dimens.hairline, BottomNavDivider),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = Dimens.spaceXs,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(Dimens.bottomNavHeight)
                .padding(horizontal = Dimens.spaceM, vertical = Dimens.spaceM),
            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceXs),
        ) {
            AppTab.entries.forEach { tab ->
                val label = when (tab) {
                    AppTab.Compose -> "記述"
                    AppTab.History -> "履歴"
                    AppTab.Lineage -> "系譜"
                    AppTab.Settings -> "設定"
                }
                val mark = when (tab) {
                    AppTab.Compose -> "✎"
                    AppTab.History -> "◫"
                    AppTab.Lineage -> "⌥"
                    AppTab.Settings -> "⚙"
                }
                NavButton(
                    mark = mark,
                    label = label,
                    selected = selected == tab,
                    onClick = { viewModel.setTab(tab) },
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

@Composable
private fun ComposeModeTabs(selected: ComposeMode, viewModel: InkuViewModel) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(100))
            .padding(Dimens.spaceXs),
        horizontalArrangement = Arrangement.spacedBy(Dimens.spaceXs),
    ) {
        ComposeMode.entries.forEach { tab ->
            val active = selected == tab
            val label = when (tab) {
                ComposeMode.Write -> "記述"
                ComposeMode.Batch -> "バッチ"
            }
            Surface(
                modifier = Modifier
                    .weight(1f)
                    .height(Dimens.buttonHeightSmall)
                    .clickable { viewModel.setComposeMode(tab) },
                shape = RoundedCornerShape(100),
                color = if (active) MaterialTheme.colorScheme.surface else Color.Transparent,
                tonalElevation = if (active) Dimens.spaceXs else 0.dp,
            ) {
                Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxSize()) {
                    Text(
                        label,
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = if (active) FontWeight.SemiBold else FontWeight.Medium,
                        color = if (active) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

private fun canvasLabel(state: InkuUiState): String {
    return canvasLabelFor(state.selectedCanvasAspect)
}

private fun canvasLabelFor(id: String): String {
    return CanvasAspects.all.firstOrNull { it.id == id }?.label ?: id
}

private fun shortCanvasLabel(state: InkuUiState): String {
    val label = canvasLabel(state)
    return when {
        label.length <= 10 -> label
        label.contains(" ") -> label.split(" ").filter { it.isNotBlank() }.joinToString(" ") { it.take(1) }.take(10)
        else -> label.take(9) + "…"
    }
}

/**
 * The compose screen, ordered by what it is about.
 *
 * The work comes first. Under it sits everything that decides the *next*
 * drawing, and nothing else: before this, the canvas was the fourth block down,
 * behind a mascot that ran whether or not anything was running, and the row
 * above the canvas mixed the work's own star and hash with a zoom and a canvas
 * aspect -- three families and two tenses on one line.
 */
@Composable
private fun ComposeScreen(state: InkuUiState, viewModel: InkuViewModel) {
    if (state.canvasPresentationMode) {
        CanvasHeroCard(state, viewModel, modifier = Modifier.fillMaxSize())
        return
    }
    val scrollState = rememberScrollState()
    val focusManager = LocalFocusManager.current
    val keyboardController = LocalSoftwareKeyboardController.current
    // Where the top of the scrolling area is on screen, and where the
    // description is. Both are measured in window coordinates: the field's
    // position inside its own parent says nothing about how far down the scroll
    // it sits, so the two have to be compared in the one frame they share.
    var viewportTop by remember { mutableStateOf(0f) }
    var descriptionTop by remember { mutableStateOf(0f) }
    LaunchedEffect(state.isDrawing, state.selectedHistory?.id) {
        if (!state.isDrawing && state.selectedHistory != null) {
            focusManager.clearFocus(force = true)
            keyboardController?.hide()
            scrollState.animateScrollTo(0)
        }
    }
    // Focus pulls the description to the top of what is left of the screen.
    // Otherwise the keyboard takes the lower half and the field keeps a sliver.
    LaunchedEffect(state.descriptionFocused) {
        if (state.descriptionFocused) {
            val delta = (descriptionTop - viewportTop).toInt()
            scrollState.animateScrollTo((scrollState.value + delta).coerceAtLeast(0))
        }
    }
    Box(
        modifier = Modifier
            .fillMaxSize()
            .onGloballyPositioned { viewportTop = it.positionInWindow().y },
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(scrollState)
                .padding(horizontal = Dimens.spaceL, vertical = Dimens.spaceXs),
            verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
        ) {
            RunStatusRow(state, viewModel)
            CanvasHeroCard(state, viewModel)
            DrawSettingsPanel(state, viewModel)
            if (state.composeMode == ComposeMode.Batch) {
                BatchPanel(state, viewModel)
            } else {
                DrawPanel(
                    state,
                    viewModel,
                    onDescriptionFocusChanged = viewModel::setDescriptionFocused,
                    onDescriptionPositioned = { descriptionTop = it },
                )
            }
            Spacer(Modifier.height(Dimens.scrollTailSpace))
        }
        if (state.descriptionFocused && state.composeMode == ComposeMode.Write) {
            ImeActionBar(state, viewModel, modifier = Modifier.align(Alignment.BottomCenter))
        }
    }
}

/**
 * The main action, pinned above the keyboard.
 *
 * The screen is one vertical scroll and the root carries `imePadding()`, so
 * opening the keyboard lifts the bottom of the scroll without bringing anything
 * with it: measured on the device, the description had ~300px of empty space
 * under it and neither 「描画する」 nor the bottom bar was on screen. This bar is
 * outside the scroll, so it stays where the thumb already is.
 *
 * The IME action key is deliberately left alone. In Japanese input the return
 * key commits the conversion, and a draw bound to it would start drawing when
 * the author meant to accept 「ゆらぎ」.
 */
@Composable
private fun ImeActionBar(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = Dimens.spaceXs,
        shadowElevation = Dimens.spaceM,
    ) {
        Box(modifier = Modifier.padding(horizontal = Dimens.spaceL, vertical = Dimens.spaceM)) {
            DrawingActionButton(
                idleText = "▶  $DRAW_ACTION_LABEL",
                runningText = "■  描画中",
                state = state,
                onClick = viewModel::draw,
                onStop = viewModel::stopDrawing,
            )
        }
    }
}

/**
 * The one "something is running" line, which web keeps in `RunStatus.svelte`.
 *
 * web renders that component from every running operation -- single draw, batch,
 * demo, DDL editor, lineage -- and the mascot lives inside it, so the animation
 * always means the same thing. The port had lifted the mascot out and placed it
 * unconditionally at the top of the compose screen, where it span with nothing
 * around it to say why. Here it is a state display again: mascot, model,
 * elapsed, stop; and when nothing runs, the row is not composed at all.
 */
@Composable
private fun RunStatusRow(state: InkuUiState, viewModel: InkuViewModel) {
    if (!state.isRunning) return
    val startedAt = remember(state.isDrawing, state.refinementBusy) { System.currentTimeMillis() }
    var elapsedMs by remember(startedAt) { mutableStateOf(0L) }
    LaunchedEffect(startedAt) {
        while (true) {
            elapsedMs = System.currentTimeMillis() - startedAt
            delay(RUN_STATUS_TICK_MS)
        }
    }
    val progress = if (state.batchTotal > 1) "${state.batchCurrent} / ${state.batchTotal}   " else ""
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(Dimens.radiusCard),
        color = MaterialTheme.colorScheme.surface,
        border = BorderStroke(Dimens.hairline, MaterialTheme.colorScheme.outline),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = Dimens.spaceM, vertical = Dimens.spaceM),
            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            MascotWidget(mascotKind = state.mascotKind)
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                Text(
                    state.message?.takeIf { it.isNotBlank() } ?: "描画中",
                    style = MaterialTheme.typography.labelMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    selectedModelLabel(state),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    "$progress${formatDuration(elapsedMs)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                )
            }
            MiniPill(
                text = "停止",
                onClick = if (state.refinementBusy) viewModel::abortRefinementCandidates else viewModel::stopDrawing,
            )
        }
    }
}

/**
 * Everything that decides the drawing that has not happened yet.
 *
 * One entry per setting, and one place for all of them. The model used to be
 * openable from three separate rows; the colour catalog from two; the canvas
 * aspect sat beside the star and the hash, which belong to the work already on
 * screen rather than to the next one.
 */
@Composable
private fun DrawSettingsPanel(state: InkuUiState, viewModel: InkuViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
        ComposeModeTabs(state.composeMode, viewModel)
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
        ) {
            CompactLabel("描画設定")
            Spacer(Modifier.weight(1f))
            MiniPill(
                "新規作成",
                onClick = if (state.composeMode == ComposeMode.Batch) viewModel::clearBatchText else viewModel::clearPrompt,
            )
        }
        WrapRow {
            MiniPill(
                text = "◇ ${shortModelLabel(state)}",
                onClick = viewModel::openModelSelection,
                modifier = Modifier.widthIn(max = Dimens.panelWideMaxWidth),
            )
            MiniPill(
                text = "◐ ${shortCatalogLabel(state)}",
                onClick = viewModel::openCatalogSelection,
                modifier = Modifier.widthIn(max = Dimens.panelMinHeight),
            )
            MiniPill(
                text = "⬚ ${shortCanvasLabel(state)}",
                onClick = viewModel::openCanvasSelection,
                modifier = Modifier.widthIn(max = Dimens.panelMinHeight),
            )
        }
        if (state.composeMode == ComposeMode.Write) {
            SketchModeRow(state, viewModel)
        }
    }
}

@Composable
private fun CanvasHeroCard(
    state: InkuUiState,
    viewModel: InkuViewModel,
    modifier: Modifier = Modifier.fillMaxWidth(),
    showControls: Boolean = true,
    maxPreviewHeight: Dp = Dimens.heroPreviewMaxHeight,
    canvasAspectOverride: String? = null,
    deviceRotation: DeviceRotation = DeviceRotation.Portrait,
) {
    val item = state.selectedHistory
    val canvasAspectId = canvasAspectOverride
        ?: if (state.canvasPresentationMode) item?.canvasAspect ?: state.selectedCanvasAspect else state.selectedCanvasAspect
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    val presentationPreferences = remember(context) {
        context.applicationContext.getSharedPreferences(PRESENTATION_PREFS_NAME, Context.MODE_PRIVATE)
    }
    var canvasMessage by remember { mutableStateOf<String?>(null) }
    var exportSheetOpen by remember { mutableStateOf(false) }
    var pngExporting by remember { mutableStateOf(false) }
    var instructionCaptionVisible by remember {
        mutableStateOf(presentationPreferences.getBoolean(PRESENTATION_CAPTION_VISIBLE_KEY, true))
    }
    val presentation = state.canvasPresentationMode
    val historyItems by viewModel.historyItems.collectAsState()
    BoxWithConstraints(modifier = modifier) {
        val screenWidth = maxWidth
        val screenHeight = maxHeight
        val ratio = remember(item?.id, item?.displaySvg, canvasAspectId) {
            item?.displaySvg?.let(::svgAspectRatio) ?: canvasAspectRatio(canvasAspectId)
        }
        val previewHeight = if (presentation) maxHeight else (maxWidth / ratio).coerceAtMost(maxPreviewHeight)
        val presentationArtworkRotation = presentationArtworkRotationDegrees(ratio, deviceRotation, presentation)
        val presentationRatio = if (presentationArtworkRotation.swapsAxes()) 1f / ratio else ratio
        val presentationBoundsRatio = if (maxHeight > 0.dp) maxWidth / maxHeight else 1f
        val presentationCanvasWidth: Dp
        val presentationCanvasHeight: Dp
        if (presentationRatio >= presentationBoundsRatio) {
            presentationCanvasWidth = maxWidth
            presentationCanvasHeight = maxWidth / presentationRatio
        } else {
            presentationCanvasHeight = maxHeight
            presentationCanvasWidth = maxHeight * presentationRatio
        }
        val presentationBackground = remember(item?.id, item?.displaySvg, presentation) {
            if (presentation && item != null) presentationBackgroundForSvg(item.displaySvg) else ServerCanvasAreaColor
        }
        // Where the double tap goes: the work at its own size. The fitted canvas
        // is `presentationCanvasWidth` across, and the work's own width is in its
        // SVG, so the ratio of the two is the 1:1 factor. A work already at or
        // above its size would be *shrunk* by 1:1, so that case magnifies instead
        // -- a double tap that appears to do nothing reads as a broken gesture.
        val fittedWidthPx = with(LocalDensity.current) { presentationCanvasWidth.toPx() }
        val intrinsicWidthPx = remember(item?.id, item?.displaySvg) { item?.displaySvg?.let(::svgIntrinsicWidth) }
        val oneToOneZoom = remember(intrinsicWidthPx, fittedWidthPx) {
            val natural = if (intrinsicWidthPx != null && fittedWidthPx > 0f) intrinsicWidthPx / fittedWidthPx else 0f
            if (natural > CANVAS_FIT_ZOOM + CANVAS_ZOOM_EPSILON) natural else PRESENTATION_FALLBACK_ZOOM
        }
        val instructionCaptionText = item?.originalInput?.trim().orEmpty()
        val canShowInstructionCaption = instructionCaptionText.isNotBlank()
        val historyIndex = item?.let { selected -> historyItems.indexOfFirst { it.id == selected.id } } ?: -1
        val historyTotal = historyItems.size
        val canGoLatest = historyIndex > 0
        val canGoNewer = historyIndex > 0
        val canGoOlder = historyIndex >= 0 && historyIndex < historyItems.lastIndex
        val historyCounter = if (historyIndex >= 0 && historyTotal > 0) "${historyIndex + 1} / $historyTotal" else ""
        Column(modifier = if (presentation) Modifier.fillMaxSize() else Modifier, verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
            // The strip above the canvas says what the work on screen *is*: its
            // star, its hash, where it sits in the lineage, and the way into the
            // full screen. The zoom and the canvas aspect used to be here too --
            // one is a property of the view, the other of the next drawing.
            if (!presentation && showControls) {
                Box(modifier = Modifier.fillMaxWidth()) {
                    Row(
                        modifier = Modifier.align(Alignment.CenterStart),
                        horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        item?.let {
                            MiniPill(text = if (it.starred) "★" else "☆", selected = it.starred, onClick = { viewModel.toggleStar(it) })
                            ProvenanceTooltipTarget(
                                tooltipText = "作品の来歴ハッシュ",
                                contentLabel = "F${it.renderHashShort}",
                                onContentClick = {
                                    clipboard.setText(AnnotatedString(it.renderHashShort))
                                    canvasMessage = "Hash copied."
                                },
                            )
                            MiniPill(text = "系譜", onClick = { viewModel.setTab(AppTab.Lineage) })
                        }
                    }
                    // A double tap enters the full screen too, but a gesture that
                    // nothing on screen mentions is a gesture nobody finds.
                    MiniPill(
                        text = "⛶ 全画面",
                        onClick = viewModel::enterCanvasPresentationMode,
                        modifier = Modifier.align(Alignment.CenterEnd),
                    )
                }
            }
            Surface(
                modifier = (if (presentation) Modifier.fillMaxSize() else Modifier.fillMaxWidth().height(previewHeight))
                    .border(Dimens.hairline, HeroCardHairline),
                color = if (presentation) presentationBackground else ServerCanvasAreaColor,
                shape = RoundedCornerShape(0.dp),
                tonalElevation = Dimens.hairline,
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        // Right goes back through the works in both modes, which
                        // is the direction of Android's own back gesture. The
                        // full screen used to be bound the other way round, so
                        // the same finger movement meant opposite things
                        // depending on which of the two canvases was on screen.
                        .historySwipeNavigation(
                            enabled = presentation && state.canvasZoom <= CANVAS_FIT_ZOOM + CANVAS_ZOOM_EPSILON,
                            gestureKey = item?.id,
                            deviceRotation = deviceRotation,
                            onSwipeRight = viewModel::selectPreviousHistory,
                            onSwipeLeft = viewModel::selectNextHistory,
                        )
                        .pointerInput(item?.id, state.canvasPresentationMode, oneToOneZoom) {
                            detectTapGestures(
                                onDoubleTap = {
                                    if (state.canvasPresentationMode) {
                                        viewModel.toggleCanvasZoom(oneToOneZoom)
                                    } else {
                                        viewModel.enterCanvasPresentationMode()
                                    }
                                },
                            )
                        },
                ) {
                    val canvasModifier = if (presentation) {
                        Modifier
                            .align(Alignment.Center)
                            .width(presentationCanvasWidth)
                            .height(presentationCanvasHeight)
                    } else {
                        Modifier.fillMaxSize()
                    }
                    Box(modifier = canvasModifier) {
                        if (item == null) {
                            CanvasPlaceholderPreview(modifier = Modifier.fillMaxSize())
                        } else {
                            ArtworkPreview(
                                item,
                                presentationMode = presentation,
                                presentationBackground = presentationBackground,
                                rotationDegrees = presentationArtworkRotation,
                                modifier = Modifier
                                    .fillMaxSize()
                                    .historySwipeNavigation(
                                        enabled = !presentation,
                                        gestureKey = item.id,
                                        deviceRotation = DeviceRotation.Portrait,
                                        onSwipeRight = viewModel::selectPreviousHistory,
                                        onSwipeLeft = viewModel::selectNextHistory,
                                    )
                                    // Magnification belongs to the full screen and
                                    // to nothing else (ruling 2026-08-08): the
                                    // small canvas in the middle of a scrolling
                                    // form is not where one looks closely, and a
                                    // pinch there fought the scroll for the
                                    // gesture. Reversed, the pinch is wired where
                                    // the work fills the screen, and the ordinary
                                    // canvas carries no transform at all.
                                    .then(
                                        if (presentation) {
                                            Modifier.pointerInput(item.id) {
                                                detectTransformGestures { _, pan, zoom, _ ->
                                                    if (zoom != 1f) viewModel.scaleCanvasZoom(zoom)
                                                    if (pan != Offset.Zero) viewModel.panCanvas(pan.x, pan.y)
                                                }
                                            }
                                        } else {
                                            Modifier
                                        },
                                    )
                                    .then(
                                        if (presentation) {
                                            Modifier.graphicsLayer(
                                                scaleX = state.canvasZoom,
                                                scaleY = state.canvasZoom,
                                                translationX = state.canvasPanX,
                                                translationY = state.canvasPanY,
                                            )
                                        } else {
                                            Modifier
                                        },
                                    )
                            )
                        }
                    }
                    if (presentation && state.demoWaitingSeconds != null) {
                        Surface(
                            modifier = Modifier
                                .align(Alignment.BottomEnd)
                                .padding(end = Dimens.radiusCard, bottom = Dimens.heroOverlayBottomInset),
                            shape = RoundedCornerShape(100),
                            color = HeroOverlayScrim,
                            border = BorderStroke(Dimens.hairline, HeroOverlayHairline),
                        ) {
                            Text(
                                "残り ${state.demoWaitingSeconds}秒",
                                modifier = Modifier.padding(horizontal = Dimens.spaceL, vertical = Dimens.spaceM),
                                style = MaterialTheme.typography.labelLarge,
                                color = HeroOverlayInk,
                            )
                        }
                    }
                    if (presentation && instructionCaptionVisible && canShowInstructionCaption) {
                        PresentationCaption(
                            text = instructionCaptionText,
                            rotation = deviceRotation,
                            modifier = presentationCaptionPlacement(screenWidth),
                        )
                    }
                    if (presentation) {
                        PresentationControls(
                            modifier = Modifier
                                .align(Alignment.BottomCenter)
                                .padding(start = Dimens.spaceL, end = Dimens.spaceL, bottom = Dimens.spaceL),
                            counter = historyCounter,
                            zoomPercent = (state.canvasZoom * 100).toInt(),
                            onResetZoom = viewModel::resetCanvasZoom,
                            starred = item?.starred == true,
                            canGoOlder = canGoOlder,
                            canGoLatest = canGoLatest,
                            canGoNewer = canGoNewer,
                            canToggleStar = item != null,
                            captionEnabled = canShowInstructionCaption,
                            captionVisible = instructionCaptionVisible,
                            onGoOlder = viewModel::selectNextHistory,
                            onGoLatest = viewModel::selectLatestHistory,
                            onGoNewer = viewModel::selectPreviousHistory,
                            onToggleStar = { item?.let(viewModel::toggleStar) },
                            onToggleCaption = {
                                if (canShowInstructionCaption) {
                                    val nextVisible = !instructionCaptionVisible
                                    instructionCaptionVisible = nextVisible
                                    presentationPreferences.edit()
                                        .putBoolean(PRESENTATION_CAPTION_VISIBLE_KEY, nextVisible)
                                        .apply()
                                }
                            },
                            onClose = viewModel::exitCanvasPresentationMode,
                        )
                    }
                }
            }
            // Under the canvas: on the left the ways of looking at the same work,
            // on the right the one way out of the app. Getting a file used to be
            // two dropdown menus in this row and a third place in the settings.
            if (!presentation && showControls) item?.let {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                ) {
                    RenderTab.entries.forEach { tab ->
                        MiniPill(
                            text = when (tab) {
                                RenderTab.Artwork -> "描画"
                                RenderTab.Prompt -> "Prompt"
                                RenderTab.Json -> "JSON"
                            },
                            selected = state.renderTab == tab,
                            onClick = { viewModel.setRenderTab(tab) },
                        )
                    }
                    Spacer(Modifier.weight(1f))
                    MiniPill(text = "⬆ 書き出し", onClick = { exportSheetOpen = true })
                }
            }
        }
    }
    if (!presentation && showControls && exportSheetOpen) item?.let {
        ExportSheet(
            item = it,
            templates = state.exportTemplates,
            onDismiss = { exportSheetOpen = false },
            onEditTemplates = {
                exportSheetOpen = false
                viewModel.setTab(AppTab.Settings)
                viewModel.setSettingsPane(SettingsPane.Export)
            },
            onExportSvg = { profile ->
                exportSheetOpen = false
                canvasMessage = "SVG export preparing..."
                scope.launch {
                    canvasMessage = runCatching {
                        shareHistorySvg(context, it, profile)
                        "SVG exported F${it.renderHashShort}"
                    }.getOrElse { error -> error.message ?: "SVG export failed." }
                }
            },
            onExportPng = { heightPx ->
                exportSheetOpen = false
                pngExporting = true
                canvasMessage = "PNG export preparing..."
                scope.launch {
                    canvasMessage = runCatching {
                        shareHistoryPng(context, it, heightPx)
                        "PNG exported F${it.renderHashShort}"
                    }.getOrElse { error -> error.message ?: "PNG export failed." }
                    pngExporting = false
                }
            },
        )
    }
    if (!presentation && showControls && pngExporting) {
        Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM), verticalAlignment = Alignment.CenterVertically) {
            CircularProgressIndicator(modifier = Modifier.size(Dimens.spaceL), strokeWidth = Dimens.spaceXs)
            Text(canvasMessage ?: "PNG export preparing...", color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelSmall)
        }
    } else if (!presentation && showControls) {
        canvasMessage?.let { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelSmall) }
    }
    if (!presentation && showControls) item?.let {
        when (state.renderTab) {
            RenderTab.Artwork -> Unit
            RenderTab.Prompt -> RenderTextView(
                renderPromptText(it, state.litertStage1PromptOptimization),
                Modifier.fillMaxWidth().height(Dimens.renderTextViewHeight),
            )
            RenderTab.Json -> RenderTextView(renderJsonText(it), Modifier.fillMaxWidth().height(Dimens.renderTextViewHeight))
        }
    }
}

/**
 * The one way a work leaves the app.
 *
 * Three destinations used to be spread over two dropdown menus hanging off the
 * canvas card and a third pane in the settings, so "get a file out of this"
 * had no single place to look. A bottom sheet is where Android puts a list of
 * destinations, and it has room to say what each one is for -- the SVG profiles
 * needed a help popover to explain themselves inside a dropdown.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ExportSheet(
    item: HistoryItemEntity,
    templates: List<ExportTemplateEntity>,
    onDismiss: () -> Unit,
    onEditTemplates: () -> Unit,
    onExportSvg: (String) -> Unit,
    onExportPng: (Int) -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = Dimens.spaceL)
                .padding(bottom = Dimens.spaceL),
            verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
        ) {
            Text("書き出し  F${item.renderHashShort}", style = MaterialTheme.typography.titleMedium)
            CompactLabel("SVG")
            SvgExportOption(title = "表示用SVG", sub = "Web表示向けの標準SVG", onClick = { onExportSvg("display") })
            SvgExportOption(title = "編集用SVG", sub = "編集用メタデータとIDを含む", onClick = { onExportSvg("editable") })
            SvgExportOption(title = "汎用SVG", sub = "互換性重視のポータブルSVG", onClick = { onExportSvg("compat") })
            CompactLabel("PNG")
            templates.forEach { template ->
                SvgExportOption(
                    title = template.name,
                    sub = exportTemplateDescription(template.description, template.heightPx),
                    onClick = { onExportPng(template.heightPx) },
                )
            }
            SecondarySmallButton(text = "テンプレートを編集", onClick = onEditTemplates)
        }
    }
}

@Composable
private fun SvgExportOption(title: String, sub: String, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape = RoundedCornerShape(Dimens.radiusCard),
        color = MaterialTheme.colorScheme.surfaceVariant,
    ) {
        Column(
            modifier = Modifier.padding(horizontal = Dimens.spaceL, vertical = Dimens.spaceM),
            verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs),
        ) {
            Text(title, style = MaterialTheme.typography.labelMedium)
            Text(sub, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

// `SvgExportHelp` and its row lived here: a popover inside the SVG dropdown
// that explained what the three profiles were for. The bottom sheet says the
// same thing on the destination itself, so the explanation no longer needs a
// place to be opened from.

private fun exportTemplateDescription(description: String, heightPx: Int): String {
    return description.ifBlank { "PNG / Y軸 ${heightPx}px" }
}

/**
 * 写生 (Stage 0.5): one control carrying three states.
 *
 * It sits above the description because that is where the layer sits -- it
 * reads the description before Stage 1 does. `切` is kept, since the layer can
 * still be skipped, but it is marked as the one not to reach for: this row is
 * the only place that says so (`sketchModeNote`, `sketch.ts:51-58`).
 */
@Composable
private fun SketchModeRow(state: InkuUiState, viewModel: InkuViewModel) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
    ) {
        CompactLabel("写生")
        Spacer(Modifier.weight(1f))
        Sketches.MODES.forEach { mode ->
            val note = Sketches.modeNote(mode, isJapanese = true)
            MiniPill(
                text = Sketches.modeLabel(mode, isJapanese = true) + note,
                selected = state.sketchMode == mode,
                onClick = { viewModel.setSketchMode(mode) },
            )
        }
    }
    Text(
        Sketches.modeHint(state.sketchMode, isJapanese = true),
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

/**
 * The description and the action that draws it.
 *
 * The settings that used to head this panel -- the model, the colour catalog,
 * 写生 -- moved to [DrawSettingsPanel] above, which is now the only place any
 * of them is opened from. What is left is the writing itself: the field, the
 * draw, and 解釈 (the DDL) under it.
 */
@Composable
private fun DrawPanel(
    state: InkuUiState,
    viewModel: InkuViewModel,
    modifier: Modifier = Modifier,
    onDescriptionFocusChanged: (Boolean) -> Unit = {},
    onDescriptionPositioned: (Float) -> Unit = {},
) {
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
        CompactLabel("記述")
        DenseMultilineInput(
            value = state.prompt,
            onValueChange = viewModel::setPrompt,
            modifier = Modifier
                .fillMaxWidth()
                .testTag(DESCRIPTION_INPUT_TAG)
                .onGloballyPositioned { onDescriptionPositioned(it.positionInWindow().y) },
            minLines = 5,
            maxLines = 8,
            onFocusChanged = onDescriptionFocusChanged,
        )
        // While the keyboard is up the same button is pinned above it, and two
        // 「描画する」 on one screen is a question about which one draws.
        if (!state.descriptionFocused) {
            DrawingActionButton(
                idleText = "▶  $DRAW_ACTION_LABEL",
                runningText = "■  描画中",
                state = state,
                onClick = viewModel::draw,
                onStop = viewModel::stopDrawing,
            )
        }
        state.message?.takeIf { it.isNotBlank() }?.let { message ->
            Text(message, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelSmall)
        }
        // 解釈 is the half of this screen one reaches for after the drawing, so
        // it is what the simple display mode leaves out. Before this stage the
        // mode's only effect was hiding the mascot and a duplicated chip row,
        // and both of those are gone.
        UiModeContainer(
            uiMode = state.uiMode,
            simpleContent = {},
            fullContent = {
                Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                    ) {
                        CompactLabel("解釈")
                        Spacer(Modifier.weight(1f))
                        DdlActionRow(state, viewModel)
                    }
                    if (state.saijikiOpen) {
                        SaijikiPanel(viewModel)
                    }
                    DdlPreviewBox(
                        value = state.ddl,
                        onClick = viewModel::openDdlEditor,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    DrawingActionButton(
                        idleText = "▶  DDLから描画",
                        runningText = "■  描画中",
                        state = state,
                        onClick = viewModel::drawFromDdl,
                        onStop = viewModel::stopDrawing,
                        tonal = true,
                    )
                }
            },
        )
    }
}

@Composable
private fun BatchPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    val lines = state.batchText.lines()
    val nonEmpty = lines.count { it.trim().isNotBlank() }
    Column(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
    ) {
        CompactLabel("バッチ")
        NumberedBatchTextField(
            value = state.batchText,
            onValueChange = viewModel::setBatchText,
            enabled = !state.isDrawing,
            modifier = Modifier.fillMaxWidth(),
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
        ) {
            Text(
                "${nonEmpty}件/100件",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (!state.isDrawing) {
            if (state.batchPromptHistory.isNotEmpty()) {
                CompactLabel("バッチ指示履歴")
                WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
                    state.batchPromptHistory.forEach { prompt ->
                        MiniPill(
                            text = prompt.lineSequence().firstOrNull()?.take(22) ?: "履歴",
                            onClick = { viewModel.restoreBatchPrompt(prompt) },
                        )
                    }
                }
            }
        }
        if (state.isDrawing && state.batchTotal > 0) {
            BatchProgressPanel(state, viewModel)
        } else {
            DrawingActionButton(
                idleText = "▶  バッチ描画",
                runningText = "■  実行中",
                state = state,
                onClick = viewModel::runBatch,
                onStop = viewModel::stopDrawing,
            )
        }
        if (state.batchFailures.isNotEmpty() && !state.isDrawing) {
            BatchFailureSummary(state)
        }
        state.message?.let { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall) }
        MetaPanel(state)
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun NumberedBatchTextField(
    value: String,
    onValueChange: (String) -> Unit,
    enabled: Boolean,
    modifier: Modifier = Modifier,
) {
    val lines = remember(value) { splitBatchEditorLines(value) }
    val lineCount = maxOf(lines.size, 1)
    val scrollState = rememberScrollState()
    val bringIntoViewRequester = remember { BringIntoViewRequester() }
    val scope = rememberCoroutineScope()
    val textStyle = MaterialTheme.typography.bodySmall.copy(
        color = MaterialTheme.colorScheme.onSurface,
        lineHeight = TypeScale.denseLineHeight,
    )

    Surface(
        modifier = modifier
            .height(Dimens.batchEditorHeight)
            .bringIntoViewRequester(bringIntoViewRequester),
        shape = RoundedCornerShape(Dimens.radiusCard),
        color = InputWellSurface,
        border = BorderStroke(Dimens.hairline, MaterialTheme.colorScheme.outline),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .clipToBounds()
                .verticalScroll(scrollState)
                .padding(horizontal = Dimens.spaceM, vertical = Dimens.spaceM),
            verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs),
        ) {
            lines.forEachIndexed { index, line ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                    verticalAlignment = Alignment.Top,
                ) {
                    Text(
                        (index + 1).toString(),
                        style = textStyle,
                        textAlign = TextAlign.End,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.width(Dimens.batchLineNumberWidth),
                    )
                    BasicTextField(
                        value = line,
                        onValueChange = { edited ->
                            onValueChange(replaceBatchEditorLine(lines, index, edited))
                        },
                        enabled = enabled,
                        textStyle = textStyle,
                        cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                        modifier = Modifier
                            .weight(1f)
                            .heightIn(min = Dimens.batchLineHeight)
                            .onFocusChanged { focusState ->
                                if (focusState.isFocused) {
                                    scope.launchImeBringIntoViewGuard(bringIntoViewRequester)
                                }
                            },
                    )
                }
            }
            if (lineCount < 6) {
                Spacer(Modifier.height(Dimens.batchLineHeight * (6 - lineCount)))
            }
        }
    }
}

private fun splitBatchEditorLines(value: String): List<String> {
    if (value.isEmpty()) return listOf("")
    return value.split('\n')
}

private fun replaceBatchEditorLine(lines: List<String>, index: Int, edited: String): String {
    val replacement = edited.replace("\r\n", "\n").replace('\r', '\n').split('\n')
    val next = lines.toMutableList()
    next.removeAt(index)
    next.addAll(index, replacement)
    return next.joinToString("\n")
}

@Composable
private fun BatchProgressPanel(state: InkuUiState, viewModel: InkuViewModel) {
    Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(Dimens.radiusCard), modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(Dimens.spaceL), verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM), modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                    Text("進捗 ${state.batchCurrent} / ${state.batchTotal}", style = MaterialTheme.typography.titleSmall)
                    Text(
                        "累計 ${formatDuration(state.batchElapsedMs)} / 成功 ${state.batchSuccess} / 失敗 ${state.batchFailures.size}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    state.batchLatestHashShort?.let {
                        Text("最新 F$it", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                    }
                }
                SecondarySmallButton(text = "停止", onClick = viewModel::stopDrawing)
            }
            state.batchActiveLine?.let { line ->
                Text("${line}行目", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.secondary)
            }
            RenderTextView(
                state.batchActiveDdl ?: "解釈を待機中...",
                modifier = Modifier.fillMaxWidth().height(Dimens.batchProgressHeight),
            )
        }
    }
}

@Composable
private fun BatchFailureSummary(state: InkuUiState) {
    Surface(color = FailureSummaryWash, shape = RoundedCornerShape(Dimens.radiusCard), modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(Dimens.spaceL), verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
            Text("成功 ${state.batchSuccess} / 失敗 ${state.batchFailures.size} / 全 ${state.batchTotal}", style = MaterialTheme.typography.titleSmall)
            Text("失敗した行", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            state.batchFailures.forEach { failure ->
                Text(
                    "${failure.line}行目  ${failure.input}  ${failure.message}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun DemoPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
    ) {
        CanvasHeroCard(
            state,
            viewModel,
            showControls = false,
            maxPreviewHeight = Dimens.demoPreviewMaxHeight,
            canvasAspectOverride = DemoCanvasAspectId,
        )

        CompactLabel("生成された指示文")
        Surface(
            color = MaterialTheme.colorScheme.surface,
            shape = RoundedCornerShape(Dimens.radiusCard),
            border = BorderStroke(Dimens.hairline, MaterialTheme.colorScheme.outline),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                state.demoGeneratedPrompt.ifBlank { "—" },
                modifier = Modifier.padding(horizontal = Dimens.spaceL, vertical = Dimens.spaceL),
                style = MaterialTheme.typography.bodyMedium,
                lineHeight = TypeScale.proseLineHeight,
                color = if (state.demoGeneratedPrompt.isBlank()) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface,
            )
        }

        DrawingActionButton(
            idleText = "▶  デモ開始",
            runningText = "■  デモ実行中",
            state = state,
            onClick = viewModel::startDemo,
            onStop = viewModel::stopDrawing,
        )

        if (state.demoGeneratedDdl != null) {
            CompactLabel("生成された解釈")
            RenderTextView(
                state.demoGeneratedDdl,
                modifier = Modifier.fillMaxWidth().height(Dimens.demoPanelHeight),
            )
        }
        MetaPanel(
            state,
            catalogIdOverride = state.demoCurrentCatalogId ?: state.selectedHistory?.colorCatalogId,
            canvasAspectOverride = DemoCanvasAspectId,
        )
    }
}

@Composable
private fun DemoSettingRow(
    label: String,
    value: String? = null,
    sub: String? = null,
    checked: Boolean? = null,
    enabled: Boolean = true,
    onCheckedChange: ((Boolean) -> Unit)? = null,
    action: (@Composable () -> Unit)? = null,
    last: Boolean = false,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .then(
                if (checked != null && onCheckedChange != null && enabled) {
                    Modifier.clickable { onCheckedChange(!checked) }
                } else {
                    Modifier
                },
            )
            .padding(horizontal = Dimens.spaceL, vertical = Dimens.spaceL),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
    ) {
        Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
            Text(label, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
            sub?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        value?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (checked != null && onCheckedChange != null) {
            Checkbox(checked = checked, onCheckedChange = if (enabled) onCheckedChange else null)
        }
        action?.invoke()
    }
    if (!last) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = Dimens.spaceL)
                .height(Dimens.hairline)
                .background(MaterialTheme.colorScheme.outline.copy(alpha = 0.45f)),
        )
    }
}

@Composable
private fun HistoryScreen(
    state: InkuUiState,
    history: List<HistoryListItem>,
    viewModel: InkuViewModel,
) {
    val filteredHistory = remember(history, state.historySearchQuery, state.historyStarredOnly) {
        filterHistoryItems(history, state)
    }
    val header: @Composable () -> Unit = {
        HistoryHeader(
            state = state,
            sourceCount = history.size,
            filteredCount = filteredHistory.size,
            viewModel = viewModel,
        )
    }
    LazyVerticalGrid(
        columns = GridCells.Fixed(3),
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = Dimens.spaceL, vertical = Dimens.spaceM),
        horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
        verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
    ) {
        item(key = "header", span = { GridItemSpan(maxLineSpan) }) { header() }
        gridItems(filteredHistory, key = { it.id }) { item ->
            HistoryGridTile(
                item = item,
                selected = state.selectedHistory?.id == item.id,
                onSelect = { viewModel.selectHistory(item) },
                onToggleStar = { viewModel.toggleStar(item) },
            )
        }
    }
}

@Composable
private fun HistoryHeader(
    state: InkuUiState,
    sourceCount: Int,
    filteredCount: Int,
    viewModel: InkuViewModel,
) {
    Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM), modifier = Modifier.fillMaxWidth()) {
        ImeAwareOutlinedTextField(
            value = state.historySearchQuery,
            onValueChange = viewModel::setHistorySearchQuery,
            label = "プロンプト・ハッシュ・モデルで検索",
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Dimens.spaceL), modifier = Modifier.fillMaxWidth()) {
            ChipButton("★ 星のみ", selected = state.historyStarredOnly, onClick = viewModel::toggleHistoryStarredFilter)
            Text("${filteredCount}/${sourceCount}件", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** So that an instrumented test can count the cards rather than the labels. */
internal const val LINEAGE_NODE_TAG = "lineage_node"

/** Tags for the refinement, so a test counts candidates rather than labels. */
internal const val REFINE_ENTRY_TAG = "refine_entry"
internal const val REFINE_CANDIDATE_TAG = "refine_candidate"
internal const val REFINE_SAVE_TAG = "refine_save"
internal const val REFINE_STOP_TAG = "refine_stop"
internal const val REFINE_GENERATE_TAG = "refine_generate"

/** The two comparison entries on a lineage card, beside 描画要素 (SPEC `:618`). */
internal const val MODEL_ENTRY_TAG = "model_entry"
internal const val LANGUAGE_ENTRY_TAG = "language_entry"

/** Tags for the sub-view chips and the two selection grids. */
internal fun refinementSubviewTag(subview: RefinementSubview): String = "refine_subview_${subview.id}"
internal fun modelCompareModeTag(mode: ModelCompareMode): String = "model_compare_mode_${mode.id}"
internal fun modelChoiceTag(modelId: String): String = "model_choice_$modelId"
internal fun languageComboTag(comboId: String): String = "language_combo_$comboId"

/**
 * 作品の系譜 -- the port of web's `LineagePanel.svelte`, cut to what contract
 * 2/5 asks for: the ancestors and two generations of descendants of the work on
 * screen, each with its thumbnail, its generation and its state, each edge with
 * its Japanese label, and the button that starts a new root.
 *
 * The tools web puts on its cards -- trash, star, note, the colophon, the
 * promotion of a `lineage_only` node, the entry to refinement -- are not here.
 * Some belong to other contracts and some the history screen already has.
 */
@Composable
internal fun LineageScreen(state: InkuUiState, viewModel: InkuViewModel) {
    val graph = state.lineageGraph
    Column(
        modifier = Modifier.fillMaxSize().padding(horizontal = Dimens.spaceL, vertical = Dimens.spaceM),
        verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
        ) {
            Text("作品の系譜", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
            // web puts the same button in the same place, at the right of the
            // panel header (LineagePanel.svelte:788). The wording is web's.
            ChipButton("新しい起点にする", onClick = viewModel::detachLineage)
        }
        when {
            state.refinementOpen -> RefinementPanel(state, viewModel)
            state.lineageLoading && graph == null ->
                Text("系譜を読み込み中…", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            graph == null || graph.nodes.isEmpty() ->
                Text("保存すると、ここに系譜が表示されます。", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            else -> LineageColumns(graph, viewModel)
        }
    }
}

/**
 * 推敲 -- the port of web's 推敲 tab, cut to the one entry SPEC `:618` puts on a
 * lineage card ("描画要素"). The comparison sub-views beside it there belong to
 * other contracts.
 *
 * The radio is the whole of the exclusivity the SPEC asks for: one element at a
 * time, with the amplitude appearing under the variation choice and nowhere else.
 */
@Composable
private fun RefinementPanel(state: InkuUiState, viewModel: InkuViewModel) {
    val parent = state.refinementParent
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
        ) {
            Text(state.refinementSubview.titleJa, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
            ChipButton("閉じる", onClick = viewModel::closeRefinement)
        }

        // 調整・モデル・言語 (SPEC :616, :686). Three faces of one screen.
        WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
            RefinementSubview.entries.forEach { subview ->
                ChipButton(
                    text = subview.labelJa,
                    selected = state.refinementSubview == subview,
                    modifier = Modifier.testTag(refinementSubviewTag(subview)),
                    onClick = { viewModel.setRefinementSubview(subview) },
                )
            }
        }

        Text(
            when (state.refinementSubview) {
                RefinementSubview.Adjust -> "1 回の推敲で変えられるのは 1 種類だけです。"
                RefinementSubview.Model -> "対象作品と同じ Stage 1/2 の組み合わせだけが選べません。"
                RefinementSubview.Language -> "Stage 1 と Stage 2 の言語の組を選びます。"
            } + (parent?.let { " 親: ${it.renderHashShort} / ${ColorCatalogs.get(it.colorCatalogId).name}" } ?: ""),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        when (state.refinementSubview) {
            RefinementSubview.Adjust -> RefinementAdjustControls(state, viewModel)
            RefinementSubview.Model -> ModelInspectionControls(state, viewModel)
            RefinementSubview.Language -> LanguageInspectionControls(state, viewModel)
        }

        WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
            // Both counts stay pressable whichever element is chosen, the way
            // web leaves its own pair alone: the refusal for four touches is
            // stated when the button is pressed, not by hiding the choice.
            if (state.refinementSubview == RefinementSubview.Adjust) {
                listOf(1, 4).forEach { count ->
                    ChipButton(
                        text = "${count}案",
                        selected = state.refinementCount == count,
                        onClick = { viewModel.setRefinementCount(count) },
                    )
                }
            }
            ChipButton(
                text = if (state.refinementBusy) "生成中…" else "候補を作る",
                modifier = Modifier.testTag(REFINE_GENERATE_TAG),
                onClick = { if (!state.refinementBusy) viewModel.generateRefinementCandidates() },
            )
        }

        // 「開始3秒後から共通デザインの停止ボタンでAPI要求を中断できる」.
        if (state.refinementCanAbort) {
            ChipButton("停止", modifier = Modifier.testTag(REFINE_STOP_TAG), onClick = viewModel::abortRefinementCandidates)
        }

        state.refinementStatus?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        }

        // 「2列（1案のみ全幅1列）でダイアログ内に収めて表示」.
        val columns = if (state.refinementCandidates.size <= 1) 1 else 2
        state.refinementCandidates.chunked(columns).forEach { row ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
            ) {
                row.forEach { candidate ->
                    RefinementCandidateCard(
                        candidate = candidate,
                        shownOnCanvas = state.refinementPreviewId == candidate.id,
                        onSave = { viewModel.saveRefinementCandidate(candidate.id) },
                        onPreview = { viewModel.previewRefinementCandidate(candidate.id) },
                        modifier = Modifier.weight(1f),
                    )
                }
                repeat(columns - row.size) { Spacer(modifier = Modifier.weight(1f)) }
            }
        }
    }
}

/** 調整: the five elements, the amplitude under the variation, the touch words. */
@Composable
private fun RefinementAdjustControls(state: InkuUiState, viewModel: InkuViewModel) {
    WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
        RefinementElement.entries.forEach { element ->
            ChipButton(
                text = element.labelJa,
                selected = state.refinementElement == element,
                onClick = { viewModel.setRefinementElement(element) },
            )
        }
    }

    // 「変奏を選択したときだけ強度をラジオ直下に表示」. No section of its own.
    if (state.refinementElement == RefinementElement.Variation) {
        WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
            VariationAmplitude.entries.forEach { amplitude ->
                ChipButton(
                    text = amplitude.labelJa,
                    selected = state.refinementAmplitude == amplitude,
                    onClick = { viewModel.setRefinementAmplitude(amplitude) },
                )
            }
        }
    }

    if (state.refinementElement == RefinementElement.Touch) {
        OutlinedTextField(
            value = state.refinementTouchWords,
            onValueChange = viewModel::setRefinementTouchWords,
            label = { Text("タッチを変える言葉") },
            singleLine = true,
            enabled = !state.refinementBusy,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

/**
 * モデル検分: the three modes, the fixed model when a mode has one, and the
 * models to compare (SPEC `:616`).
 *
 * No judge value is shown -- the SPEC says so twice, and there is nothing on
 * this screen that would carry one.
 */
@Composable
private fun ModelInspectionControls(state: InkuUiState, viewModel: InkuViewModel) {
    val choices = remember(state.modelAssets, state.providerSettings) { modelChoicesFor(state) }
    WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
        ModelCompareMode.entries.forEach { mode ->
            ChipButton(
                text = mode.labelJa,
                selected = state.modelCompareMode == mode,
                modifier = Modifier.testTag(modelCompareModeTag(mode)),
                onClick = { viewModel.setModelCompareMode(mode) },
            )
        }
    }

    if (state.modelCompareMode != ModelCompareMode.Common) {
        Text(
            if (state.modelCompareMode == ModelCompareMode.Stage1Fixed) "固定する Stage 1 モデル" else "固定する Stage 2 モデル",
            style = MaterialTheme.typography.labelMedium,
        )
        WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
            choices.forEach { choice ->
                ChipButton(
                    text = choice.label,
                    selected = state.modelCompareFixedModel == choice.id,
                    onClick = { viewModel.setModelCompareFixedModel(choice.id) },
                )
            }
        }
    }

    Text("比較するモデル (最大 ${MAX_COMPARE_SELECTION})", style = MaterialTheme.typography.labelMedium)
    WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
        choices.forEach { choice ->
            val blocked = ComparisonPlanner.isModelChoiceBlocked(
                mode = state.modelCompareMode,
                fixedModel = state.modelCompareFixedModel,
                model = choice.id,
                targetStage1Model = state.refinementParent?.stage1Model.orEmpty(),
                targetStage2Model = state.refinementParent?.stage2Model.orEmpty(),
            )
            ChipButton(
                text = if (blocked) "${choice.label}（対象と同じ）" else choice.label,
                selected = choice.id in state.modelCompareSelectedModels,
                modifier = Modifier.testTag(modelChoiceTag(choice.id)),
                onClick = { viewModel.toggleModelCompareSelection(choice.id) },
            )
        }
    }
}

/**
 * 言語検分: the four Stage 1 × Stage 2 pairs, chosen with checkboxes.
 *
 * SPEC `:686` describes the same three modes model comparison has; the reference
 * implementation selects pairs instead (`CanvasPanel.svelte:978-988`), and SPEC
 * `:614` makes the reference implementation the one to follow.
 */
@Composable
private fun LanguageInspectionControls(state: InkuUiState, viewModel: InkuViewModel) {
    WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
        LanguageCombo.ALL.forEach { combo ->
            val blocked = ComparisonPlanner.isLanguageComboBlocked(combo, targetInstructionLangOf(state.refinementParent))
            ChipButton(
                text = "${languageLabel(combo.stage1)} / ${languageLabel(combo.stage2)}" + if (blocked) "（対象と同じ）" else "",
                selected = combo.id in state.languageCompareSelectedCombos,
                modifier = Modifier.testTag(languageComboTag(combo.id)),
                onClick = { viewModel.toggleLanguageCombo(combo.id) },
            )
        }
    }
}

/** The target work's language, read the way `languageInspectionTargetLang` reads it. */
private fun targetInstructionLangOf(parent: HistoryItemEntity?): String =
    parent?.instructionLangResolved
        ?.takeIf { it in InstructionLanguages.SUPPORTED }
        ?: InstructionLanguages.DEFAULT_LANG

@Composable
private fun RefinementCandidateCard(
    candidate: RefinementCandidate,
    shownOnCanvas: Boolean,
    onSave: () -> Unit,
    onPreview: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // 「読み取りを含む候補は画像hoverで正規化DDLを表示する」. A phone has no hover, so
    // the DDL opens on a long press instead (contract 段 3 leaves the gesture to
    // the port); everything else about the candidate is the same.
    var ddlOpen by remember(candidate.id) { mutableStateOf(false) }
    val readingCandidate = candidate.plan.element == RefinementElement.Reading
    Card(
        modifier = modifier
            .testTag(REFINE_CANDIDATE_TAG)
            .border(Dimens.spaceXs, if (shownOnCanvas) MaterialTheme.colorScheme.primary else Color.Transparent, RoundedCornerShape(0.dp)),
        shape = RoundedCornerShape(0.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
            RefinementCandidateImage(
                svg = candidate.displaySvg,
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(1f)
                    .combinedClickable(
                        onClick = onPreview,
                        onLongClick = { if (readingCandidate) ddlOpen = !ddlOpen },
                    ),
            )
            Column(modifier = Modifier.padding(horizontal = Dimens.spaceM).padding(bottom = Dimens.spaceM), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                Text(candidate.label, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(candidate.renderHashShort, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (readingCandidate && ddlOpen) {
                    Text(candidate.normalizedDdl, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                // The three states are three different labels, and only the
                // first one is a button that does anything.
                when (candidate.saveState) {
                    RefinementSaveState.Unsaved ->
                        ChipButton("保存", modifier = Modifier.testTag(REFINE_SAVE_TAG), onClick = onSave)
                    RefinementSaveState.Saving -> Text("保存中…", style = MaterialTheme.typography.labelSmall)
                    RefinementSaveState.Saved -> Text("保存済み", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable
private fun RefinementCandidateImage(svg: String, modifier: Modifier = Modifier) {
    val image by produceState<ImageBitmap?>(initialValue = null, svg) {
        value = withContext(Dispatchers.Default) {
            runCatching {
                val parsed = SVG.getFromString(svg)
                val side = 512
                val bitmap = Bitmap.createBitmap(side, side, Bitmap.Config.ARGB_8888)
                val native = AndroidCanvas(bitmap)
                native.drawColor(android.graphics.Color.WHITE)
                renderSvgIntoNativeCanvas(parsed, native, side.toFloat(), side.toFloat(), 0)
                bitmap.asImageBitmap()
            }.getOrNull()
        }
    }
    Surface(color = Color.White, shape = RoundedCornerShape(0.dp), modifier = modifier) {
        val bitmap = image
        if (bitmap != null) {
            Image(bitmap = bitmap, contentDescription = null, modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Fit)
        } else {
            Canvas(modifier = Modifier.fillMaxSize()) { drawRect(Color.White) }
        }
    }
}

@Composable
private fun LineageColumns(graph: LineageGraphResult, viewModel: InkuViewModel) {
    // Grouped by the distance from the topmost node of *this* graph, the way
    // web's `depthByNode` does. The heading names the generation instead, which
    // is counted from the root of the whole lineage and so keeps its number
    // when a graph starts halfway down the tree.
    val parentOf = remember(graph) { graph.edges.associate { it.childNodeId to it.parentNodeId } }
    val depthOf = remember(graph) {
        val shown = graph.nodes.map { it.id }.toSet()
        graph.nodes.associate { node ->
            var depth = 0
            var cursor = node.id
            val seen = mutableSetOf(cursor)
            while (true) {
                val parent = parentOf[cursor] ?: break
                if (parent !in shown || !seen.add(parent)) break
                depth += 1
                cursor = parent
            }
            node.id to depth
        }
    }
    val kindOf = remember(graph) { graph.edges.associate { it.childNodeId to it.derivationKind } }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(Dimens.spaceL),
    ) {
        // One row per generation, oldest first. web labels each of its columns
        // 第N世代 (LineagePanel.svelte); here the number is on the cards instead,
        // where a tombstone -- which the server gives no generation -- can say
        // so for itself rather than sit under a heading that answers for it.
        graph.nodes.groupBy { depthOf[it.id] ?: 0 }.toSortedMap().forEach { (_, nodes) ->
            WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
                nodes.forEach { node ->
                    LineageNodeCard(
                        node = node,
                        focused = node.id == graph.focusNodeId,
                        derivationKind = kindOf[node.id],
                        onSelect = { viewModel.selectLineageNode(node) },
                        onRefine = { item, subview -> viewModel.openRefinement(item, subview) },
                    )
                }
            }
        }
    }
}

@Composable
private fun LineageNodeCard(
    node: LineageGraphNode,
    focused: Boolean,
    derivationKind: String?,
    onSelect: () -> Unit,
    onRefine: (HistoryItemEntity, RefinementSubview) -> Unit,
) {
    val work = node as? LineageGraphNode.Work
    val history = work?.history
    Card(
        modifier = Modifier
            .width(Dimens.chipWidth)
            .testTag(LINEAGE_NODE_TAG)
            .clickable(enabled = history != null, onClick = onSelect)
            .border(Dimens.spaceXs, if (focused) MaterialTheme.colorScheme.primary else Color.Transparent, RoundedCornerShape(0.dp)),
        shape = RoundedCornerShape(0.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
            if (history != null) {
                ArtworkThumbnail(
                    id = history.item.id,
                    renderHash = history.item.renderHash,
                    thumbnailPath = history.item.thumbnailPath,
                    modifier = Modifier.fillMaxWidth().aspectRatio(1f),
                )
            } else {
                Box(modifier = Modifier.fillMaxWidth().aspectRatio(1f).background(LineagePlaceholderSurface))
            }
            Column(modifier = Modifier.padding(horizontal = Dimens.spaceM).padding(bottom = Dimens.spaceM), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                // The label of the edge that produced this work. `labelJa` with
                // no kind is 起点, which is the answer for a node no edge points
                // at; the wording is the registry's, never this screen's.
                Text(
                    DerivationKindRegistry.labelJa(derivationKind),
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    history?.lineageGeneration?.let { "第${it}世代" } ?: "—",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                // The server's own value, not a rendering of it.
                Text(
                    node.state,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                // 「作品を編集する」 in SPEC :618 lists seven items in one order --
                // 描画要素・記述・DDL・モデル・言語・AI に自律推敲させる・ゴミ箱.
                // Three of them are here, in that order; 記述 and DDL sit
                // between them in the SPEC and belong to another contract, so
                // モデル and 言語 follow 描画要素 directly. Each opens the matching
                // sub-view of the same 推敲 screen rather than a screen of its own
                // (SPEC :688). A tombstone has no work to refine, which is why
                // this hangs off `history`.
                if (history != null) {
                    ChipButton("描画要素", modifier = Modifier.testTag(REFINE_ENTRY_TAG), onClick = { onRefine(history.item, RefinementSubview.Adjust) })
                    ChipButton("モデル", modifier = Modifier.testTag(MODEL_ENTRY_TAG), onClick = { onRefine(history.item, RefinementSubview.Model) })
                    ChipButton("言語", modifier = Modifier.testTag(LANGUAGE_ENTRY_TAG), onClick = { onRefine(history.item, RefinementSubview.Language) })
                }
            }
        }
    }
}

@Composable
private fun SettingsPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    when (state.settingsPane) {
        SettingsPane.Home -> SettingsHomePanel(state, viewModel, modifier)
        SettingsPane.ModelSelection -> ModelSelectionPanel(state, viewModel, modifier)
        SettingsPane.Models -> ModelSettingsPanel(state, viewModel, modifier)
        SettingsPane.Demo -> DemoSettingsPanel(state, viewModel, modifier)
        SettingsPane.Export -> ExportSettingsPanel(state, viewModel, modifier)
        SettingsPane.Misc -> MiscSettingsPanel(state, viewModel, modifier)
        SettingsPane.Version -> VersionInfoPanel(viewModel, modifier)
    }
}

@Composable
private fun SettingsHomePanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(horizontal = Dimens.spaceXs),
        verticalArrangement = Arrangement.spacedBy(Dimens.spaceL),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(top = Dimens.spaceXs),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
        ) {
            Text("設定", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Medium)
        }
        SettingsListItem(mark = "◇", title = "モデル設定", sub = "OpenAI / Claude / Gemini / NVIDIA", onClick = { viewModel.setSettingsPane(SettingsPane.Models) })
        SettingsListItem(mark = "◉", title = "デモ", sub = "実行とシードフレーズ", onClick = { viewModel.setSettingsPane(SettingsPane.Demo) })
        SettingsListItem(mark = "⬚", title = "エクスポート", sub = "PNG 1080 / 2160 / 4320", onClick = { viewModel.setSettingsPane(SettingsPane.Export) })
        SettingsListItem(mark = "◐", title = "その他", sub = "言語・テーマ・密度", onClick = { viewModel.setSettingsPane(SettingsPane.Misc) })
        SettingsListItem(
            mark = "#",
            title = "バージョン情報",
            sub = "Android ${BuildConfig.VERSION_NAME} · build ${BuildConfig.BUILD_NUMBER}",
            onClick = { viewModel.setSettingsPane(SettingsPane.Version) },
        )
    }
}

@Composable
private fun SettingsHeader(selectedPane: SettingsPane, viewModel: InkuViewModel) {
    val title = settingsPaneTitle(selectedPane)
    val subtitle = settingsPaneSubtitle(selectedPane)
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = Dimens.spaceXs),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
    ) {
        MiniPill("‹", onClick = { viewModel.setSettingsPane(SettingsPane.Home) })
        Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
            Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Medium)
            Text(subtitle, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun ModelSelectionPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    val modelChoices = remember(state.modelAssets, state.providerSettings) { modelChoicesFor(state) }
    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(horizontal = Dimens.spaceXs),
        verticalArrangement = Arrangement.spacedBy(Dimens.spaceL),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(top = Dimens.spaceXs),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
        ) {
            Text("モデル選択", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
            SecondarySmallButton(text = "取消", onClick = viewModel::cancelModelSelection)
            PrimarySmallButton(text = "決定", onClick = viewModel::confirmModelSelection)
        }
        SettingsCard("描画モデル", "Stage 1 / Stage 2 共通", selectedModelLabel(state)) {
            ModelChoiceRow(
                choices = modelChoices,
                selectedValue = state.selectedModelId,
                onSelect = viewModel::setSelectedModel,
            )
        }
        Text(
            "内部保存と履歴メタデータはserver互換のstage1_model / stage2_modelを維持し、Android UIでは同じモデルを両Stageへ適用します。",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        SecondaryActionButton(text = "接続先設定を開く", onClick = { viewModel.setSettingsPane(SettingsPane.Models) })
    }
}

@Composable
private fun DemoSettingsPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.verticalScroll(rememberScrollState()).padding(horizontal = Dimens.spaceXs),
        verticalArrangement = Arrangement.spacedBy(Dimens.spaceL),
    ) {
        SettingsHeader(state.settingsPane, viewModel)
        // The demo was the fifth bottom tab until 2026-08-08. M3 keeps that bar
        // for the places one returns to, and the demo is started now and then,
        // so the running of it sits here with the settings it runs under.
        DemoPanel(state, viewModel)
        SettingsCard("シードフレーズ", "デモ指示文生成", "保存済み") {
            ImeAwareOutlinedTextField(
                value = state.demoSeed,
                onValueChange = viewModel::setDemoSeed,
                modifier = Modifier.fillMaxWidth(),
                minLines = 5,
                maxLines = 8,
            )
            SecondarySmallButton(text = "デフォルト値に戻す", onClick = viewModel::resetDemoSeed)
        }
        SettingsCard("表示間隔", "デモ表示", "${state.demoIntervalSeconds}秒") {
            Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM), verticalAlignment = Alignment.CenterVertically) {
                SecondarySmallButton(
                    text = "−",
                    onClick = { viewModel.setDemoIntervalSeconds(state.demoIntervalSeconds - 5) },
                    enabled = state.demoIntervalSeconds > 1,
                )
                Text("${state.demoIntervalSeconds}秒", style = MaterialTheme.typography.labelMedium)
                SecondarySmallButton(
                    text = "+",
                    onClick = { viewModel.setDemoIntervalSeconds(state.demoIntervalSeconds + 5) },
                    enabled = state.demoIntervalSeconds < 999,
                )
            }
        }
        SettingsCard("描画表現", "脱・規則化", if (state.renderWild) "ON (Wild)" else "OFF (Standard)") {
            SettingCheckRow(
                checked = state.renderWild,
                text = "暴れる（演奏上限の解除） / Wild (unleashed performance)",
                onCheckedChange = viewModel::setRenderWild,
            )
        }
    }
}

@Composable
private fun ExportSettingsPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.verticalScroll(rememberScrollState()).padding(horizontal = Dimens.spaceXs),
        verticalArrangement = Arrangement.spacedBy(Dimens.spaceL),
    ) {
        SettingsHeader(state.settingsPane, viewModel)
        SettingsCard("PNG / SVG", "Web版の出力設定", "保存済み") {
            SettingCheckRow(
                checked = state.pngAlphaWhite,
                text = "PNG透過時の白背景",
                onCheckedChange = viewModel::setPngAlphaWhite,
            )
            Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                state.exportTemplates.forEach { template ->
                    ExportTemplateRow(template, viewModel)
                }
                SecondarySmallButton(text = "テンプレート追加", onClick = viewModel::addExportTemplate)
            }
        }
    }
}

@Composable
private fun MiscSettingsPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.verticalScroll(rememberScrollState()).padding(horizontal = Dimens.spaceXs),
        verticalArrangement = Arrangement.spacedBy(Dimens.spaceL),
    ) {
        SettingsHeader(state.settingsPane, viewModel)
        SettingsCard("表示モード", "UIの表示密度・構成", state.uiMode) {
            Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                ChipButton("フルモード", selected = state.uiMode == "full", onClick = { viewModel.setUiMode("full") })
                ChipButton("シンプルモード", selected = state.uiMode == "simple", onClick = { viewModel.setUiMode("simple") })
            }
        }
        SettingsCard("マスコット選択", "Incu (立方体) または Yuragi (蟹)", state.mascotKind) {
            Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                ChipButton("Incu (立方体)", selected = state.mascotKind == "incu", onClick = { viewModel.setMascotKind("incu") })
                ChipButton("Yuragi (蟹)", selected = state.mascotKind == "yuragi", onClick = { viewModel.setMascotKind("yuragi") })
            }
        }
        SettingsCard("履歴選択", "Web版の履歴反映設定", "保存済み") {
            SettingChoiceRow(
                title = "キャンバス",
                selected = state.historySelectionCanvas,
                onSelect = viewModel::setHistorySelectionCanvas,
            )
            SettingChoiceRow(
                title = "色カタログ",
                selected = state.historySelectionCatalog,
                onSelect = viewModel::setHistorySelectionCatalog,
            )
            SettingCheckRow(state.saveReplayAsNewVersion, "DDL再描画を新しい履歴として保存", viewModel::setSaveReplayAsNewVersion)
        }
    }
}

@Composable
internal fun VersionInfoPanel(viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(horizontal = Dimens.spaceXs),
        verticalArrangement = Arrangement.spacedBy(Dimens.spaceL),
    ) {
        SettingsHeader(SettingsPane.Version, viewModel)
        SettingsCard("inku Android", "アプリケーション", BuildConfig.VERSION_NAME) {
            VersionInfoRow("versionName", BuildConfig.VERSION_NAME)
            VersionInfoRow("versionCode", BuildConfig.VERSION_CODE.toString())
            VersionInfoRow("build number", BuildConfig.BUILD_NUMBER.toString())
            VersionInfoRow("build type", BuildConfig.BUILD_TYPE)
            VersionInfoRow("applicationId", BuildConfig.APPLICATION_ID)
            VersionInfoRow("source spec", "inku v1.48")
            VersionInfoRow("render engine", "${CompatibilityConstants.renderEngineId} ${CompatibilityConstants.renderEngineVersion}")
        }
    }
}

@Composable
private fun VersionInfoRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Top,
    ) {
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            value,
            modifier = Modifier.padding(start = Dimens.spaceL).weight(1f),
            style = MaterialTheme.typography.bodySmall,
            textAlign = TextAlign.End,
        )
    }
}

@Composable
private fun ModelSettingsPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(horizontal = Dimens.spaceXs),
        verticalArrangement = Arrangement.spacedBy(Dimens.spaceL),
    ) {
        SettingsHeader(state.settingsPane, viewModel)

        Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
            state.providerSettings.forEach { provider ->
                ProviderConnectionCard(
                    provider = provider,
                    candidateModelIds = state.providerModelCandidates[provider.providerId].orEmpty(),
                    modelAssets = state.modelAssets,
                    onSave = viewModel::saveProviderSetting,
                    onClearApiKey = { viewModel.clearProviderApiKey(provider.providerId) },
                    onDelete = { viewModel.deleteProvider(provider.providerId) },
                    onFetchModels = { viewModel.fetchProviderModels(provider.providerId) },
                    onAcceptModelLicense = viewModel::acceptModelLicense,
                    onDownloadModel = viewModel::downloadModel,
                    onRedownloadModel = viewModel::redownloadModel,
                    litertStage1PromptOptimization = state.litertStage1PromptOptimization,
                    onLiteRtStage1PromptOptimizationChange = viewModel::setLiteRtStage1PromptOptimization,
                    statusMessage = state.message,
                )
            }
            AddProviderCard(onAdd = viewModel::saveProviderSetting)
        }
    }
}

@Composable
private fun ProviderConnectionCard(
    provider: app.inku.mobile.data.db.ProviderSettingEntity,
    candidateModelIds: List<String>,
    modelAssets: List<app.inku.mobile.data.db.ModelAssetEntity>,
    onSave: (String, String, String, String, String, String) -> Unit,
    onClearApiKey: () -> Unit,
    onDelete: () -> Unit,
    onFetchModels: () -> Unit,
    onAcceptModelLicense: (String) -> Unit,
    onDownloadModel: (String) -> Unit,
    onRedownloadModel: (String) -> Unit,
    litertStage1PromptOptimization: Boolean,
    onLiteRtStage1PromptOptimizationChange: (Boolean) -> Unit,
    statusMessage: String?,
) {
    val requiresKey = provider.providerId in setOf("openai", "nvidia", "anthropic", "gemini")
    val keySet = !provider.encryptedApiKey.isNullOrBlank()
    var displayName by remember(provider.providerId, provider.displayName) { mutableStateOf(provider.displayName) }
    val kind = provider.kind
    var baseUrl by remember(provider.providerId, provider.baseUrl) { mutableStateOf(provider.baseUrl.orEmpty()) }
    var apiKey by remember(provider.providerId, provider.encryptedApiKey) { mutableStateOf("") }
    var editNameOpen by remember(provider.providerId) { mutableStateOf(false) }
    var editBaseUrlOpen by remember(provider.providerId) { mutableStateOf(false) }
    var editApiKeyOpen by remember(provider.providerId) { mutableStateOf(false) }
    var modelPickerOpen by remember(provider.providerId) { mutableStateOf(false) }
    var confirmClearKey by remember(provider.providerId) { mutableStateOf(false) }
    var confirmDeleteService by remember(provider.providerId) { mutableStateOf(false) }
    val publishedModels = remember(provider.providerId, provider.publishedModelsJson) {
        parsePublishedModelIds(provider.publishedModelsJson).joinToString("\n")
    }
    val publishedModelIds = remember(provider.providerId, provider.publishedModelsJson) {
        parsePublishedModelIds(provider.publishedModelsJson)
    }
    val apiKeyState = if (keySet) "APIキー設定済み" else "APIキー未設定"
    SettingsCard(
        provider.displayName,
        "Service ID: ${provider.providerId}",
        "",
        titleAction = {
            SecondarySmallButton(text = "変更", onClick = { editNameOpen = true })
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
            ModelSettingValueRow(
                label = "Base URL",
                value = baseUrl.ifBlank { provider.baseUrl ?: "-" },
                action = "編集",
                onAction = { editBaseUrlOpen = true },
            )
            if (provider.isDefaultLocal) {
                SettingCheckRow(
                    checked = litertStage1PromptOptimization,
                    text = "プロンプト最適化",
                    onCheckedChange = onLiteRtStage1PromptOptimizationChange,
                )
                Text(
                    "ONの場合、LiteRT-LMのStage 1だけ圧縮版system promptを使用します。server互換モデルには影響しません。",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("APIキー", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM), verticalAlignment = Alignment.CenterVertically) {
                            Text(apiKeyState, style = MaterialTheme.typography.bodySmall)
                            if (!keySet) Text("ローカルLLMの場合、APIキー無しで利用可能な場合があります。", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    }
                    SecondarySmallButton(
                        text = if (keySet) "削除" else "追加",
                        onClick = {
                            if (keySet) confirmClearKey = true else editApiKeyOpen = true
                        },
                    )
                }
            }
            Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("ユーザーに公開するモデル", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    SecondarySmallButton(text = "モデル選択", onClick = { modelPickerOpen = true })
                }
                if (publishedModelIds.isEmpty()) {
                    Text("公開モデルは未選択です。", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
                        publishedModelIds.forEach { modelId ->
                            PublishedModelChip(modelDisplayName(modelId))
                        }
                    }
                }
            }
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                OutlinedButton(
                    onClick = { confirmDeleteService = true },
                    enabled = !provider.isDefaultLocal,
                    modifier = Modifier.height(Dimens.controlSizeSmall),
                    shape = RoundedCornerShape(Dimens.radiusCard),
                    contentPadding = PaddingValues(horizontal = Dimens.spaceM, vertical = 0.dp),
                ) {
                    Text("サービス削除", style = MaterialTheme.typography.labelSmall, maxLines = 1)
                }
            }
        }
    }
    if (editNameOpen) {
        TextEditDialog(
            title = "サービス名を変更",
            label = "サービス名",
            initialValue = displayName,
            onDismiss = { editNameOpen = false },
            onSave = { value ->
                displayName = value
                editNameOpen = false
                onSave(provider.providerId, value, kind, baseUrl, "", publishedModels)
            },
        )
    }
    if (editBaseUrlOpen) {
        TextEditDialog(
            title = "Base URLを変更",
            label = "Base URL",
            initialValue = baseUrl,
            onDismiss = { editBaseUrlOpen = false },
            onSave = { value ->
                baseUrl = value
                editBaseUrlOpen = false
                onSave(provider.providerId, displayName, kind, value, "", publishedModels)
            },
        )
    }
    if (editApiKeyOpen) {
        TextEditDialog(
            title = "APIキーを設定",
            label = "新しいAPIキー",
            initialValue = apiKey,
            onDismiss = { editApiKeyOpen = false },
            onSave = { value ->
                apiKey = value
                editApiKeyOpen = false
                if (apiKey.isNotBlank()) {
                    onSave(provider.providerId, displayName, kind, baseUrl, apiKey, publishedModels)
                    apiKey = ""
                }
            },
        )
    }
    if (modelPickerOpen) {
        if (provider.isDefaultLocal) {
            LocalModelManagementDialog(
                provider = provider,
                modelAssets = modelAssets,
                selectedModels = publishedModelIds,
                onDismiss = { modelPickerOpen = false },
                onAcceptModelLicense = onAcceptModelLicense,
                onDownloadModel = onDownloadModel,
                onRedownloadModel = onRedownloadModel,
                statusMessage = statusMessage,
                onSave = { selected ->
                    modelPickerOpen = false
                    onSave(provider.providerId, displayName, kind, baseUrl, "", selected.joinToString("\n"))
                },
            )
        } else {
            ProviderModelPickerDialog(
                provider = provider,
                candidateModelIds = candidateModelIds,
                selectedModels = publishedModelIds,
                onDismiss = { modelPickerOpen = false },
                onFetchModels = onFetchModels,
                statusMessage = statusMessage,
                onSave = { selected ->
                    modelPickerOpen = false
                    onSave(provider.providerId, displayName, kind, baseUrl, "", selected.joinToString("\n"))
                },
            )
        }
    }
    if (confirmClearKey) {
        AlertDialog(
            onDismissRequest = { confirmClearKey = false },
            title = { Text("APIキーを削除") },
            text = { Text("${provider.displayName} の保存済みAPIキーを削除します。") },
            confirmButton = {
                TextButton(onClick = {
                    confirmClearKey = false
                    onClearApiKey()
                }) { Text("削除") }
            },
            dismissButton = { TextButton(onClick = { confirmClearKey = false }) { Text("キャンセル") } },
        )
    }
    if (confirmDeleteService) {
        AlertDialog(
            onDismissRequest = { confirmDeleteService = false },
            title = { Text("サービスを削除") },
            text = { Text("${provider.displayName} をモデル接続先から削除します。") },
            confirmButton = {
                TextButton(onClick = {
                    confirmDeleteService = false
                    onDelete()
                }) { Text("削除") }
            },
            dismissButton = { TextButton(onClick = { confirmDeleteService = false }) { Text("キャンセル") } },
        )
    }
}

@Composable
private fun ModelSettingValueRow(label: String, value: String, action: String, onAction: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value.ifBlank { "-" }, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        SecondarySmallButton(text = action, onClick = onAction)
    }
}

@Composable
private fun PublishedModelChip(label: String) {
    Surface(
        color = ChipSurface,
        shape = RoundedCornerShape(100),
        border = BorderStroke(Dimens.hairline, CardHairline),
        modifier = Modifier.widthIn(max = Dimens.publishedChipMaxWidth),
    ) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = Dimens.spaceM, vertical = Dimens.spaceM),
            style = MaterialTheme.typography.labelSmall,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun TextEditDialog(
    title: String,
    label: String,
    initialValue: String,
    onDismiss: () -> Unit,
    onSave: (String) -> Unit,
) {
    var value by remember(title, initialValue) { mutableStateOf(initialValue) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            ImeAwareOutlinedTextField(
                value = value,
                onValueChange = { value = it },
                label = label,
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
        },
        confirmButton = {
            TextButton(onClick = { onSave(value.trim()) }) { Text("保存") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("キャンセル") }
        },
    )
}

@Composable
private fun ProviderModelPickerDialog(
    provider: app.inku.mobile.data.db.ProviderSettingEntity,
    candidateModelIds: List<String>,
    selectedModels: List<String>,
    onDismiss: () -> Unit,
    onFetchModels: () -> Unit,
    statusMessage: String?,
    onSave: (List<String>) -> Unit,
) {
    var search by remember(provider.providerId) { mutableStateOf("") }
    var selected by remember(provider.providerId) { mutableStateOf(selectedModels.toSet()) }
    val candidateModels = remember(provider.providerId, provider.publishedModelsJson, candidateModelIds) {
        providerModelCandidates(provider, candidateModelIds)
    }
    val candidateIds = candidateModels.map { it.id }.toSet()
    val filtered = candidateModels.filter { model ->
        val query = search.trim().lowercase()
        query.isBlank() || model.id.lowercase().contains(query) || model.label.lowercase().contains(query) || (model.notes?.lowercase()?.contains(query) == true)
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(provider.displayName) },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth().height(Dimens.providerModelDialogHeight),
                verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM), modifier = Modifier.fillMaxWidth()) {
                    ModelPickerActionButton(text = "モデルリスト取得", onClick = onFetchModels, modifier = Modifier.weight(1.5f))
                    ModelPickerActionButton(text = "全選択", onClick = { selected = filtered.map { it.id }.toSet() }, modifier = Modifier.weight(1f))
                    ModelPickerActionButton(text = "全解除", onClick = { selected = emptySet() }, modifier = Modifier.weight(1f))
                }
                ImeAwareOutlinedTextField(
                    value = search,
                    onValueChange = { search = it },
                    label = "モデル検索",
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii),
                )
                Column(
                    modifier = Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs),
                ) {
                    filtered.forEach { model ->
                        val checked = selected.contains(model.id)
                        Row(
                            modifier = Modifier.fillMaxWidth().clickable {
                                selected = if (checked) selected - model.id else selected + model.id
                            }.padding(vertical = Dimens.spaceXs),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                        ) {
                            Checkbox(checked = checked, onCheckedChange = { enabled ->
                                selected = if (enabled) selected + model.id else selected - model.id
                            })
                            Column(modifier = Modifier.weight(1f)) {
                                Text(model.label, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text(model.notes ?: model.id, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            }
                        }
                    }
                }
                statusMessage?.takeIf { it.contains("モデル") || it.contains(provider.providerId) }?.let {
                    Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onSave(selected.filter { it in candidateIds }) }) { Text("保存") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("キャンセル") }
        },
    )
}

@Composable
private fun LocalModelManagementDialog(
    provider: app.inku.mobile.data.db.ProviderSettingEntity,
    modelAssets: List<app.inku.mobile.data.db.ModelAssetEntity>,
    selectedModels: List<String>,
    onDismiss: () -> Unit,
    onAcceptModelLicense: (String) -> Unit,
    onDownloadModel: (String) -> Unit,
    onRedownloadModel: (String) -> Unit,
    statusMessage: String?,
    onSave: (List<String>) -> Unit,
) {
    var selected by remember(provider.providerId, selectedModels) { mutableStateOf(selectedModels.toSet()) }
    val assetIds = modelAssets.map { it.modelId }.toSet()
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth(0.94f)
                .heightIn(max = Dimens.localModelDialogMaxHeight),
            shape = RoundedCornerShape(Dimens.radiusCard),
            color = MaterialTheme.colorScheme.surface,
            tonalElevation = Dimens.spaceM,
        ) {
            Column(
                modifier = Modifier.padding(Dimens.spaceL),
                verticalArrangement = Arrangement.spacedBy(Dimens.spaceL),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("LiteRT-LM", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Medium)
                        Text("ローカルモデル", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                        ModelPickerActionButton(text = "全選択", onClick = { selected = assetIds }, modifier = Modifier.width(Dimens.modelActionWidth))
                        ModelPickerActionButton(text = "全解除", onClick = { selected = emptySet() }, modifier = Modifier.width(Dimens.modelActionWidth))
                    }
                }

                Column(
                    modifier = Modifier.fillMaxWidth().weight(1f, fill = false).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                ) {
                    modelAssets.forEach { asset ->
                        LocalModelAssetRow(
                            asset = asset,
                            checked = selected.contains(asset.modelId),
                            onCheckedChange = { checked ->
                                selected = if (checked) selected + asset.modelId else selected - asset.modelId
                            },
                            onAcceptModelLicense = { onAcceptModelLicense(asset.modelId) },
                            onDownloadModel = { onDownloadModel(asset.modelId) },
                            onRedownloadModel = { onRedownloadModel(asset.modelId) },
                        )
                    }
                }

                statusMessage?.takeIf { it.contains("モデル") || it.contains("Gemma") || it.contains("LiteRT") }?.let {
                    Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    TextButton(onClick = onDismiss) { Text("キャンセル") }
                    TextButton(onClick = { onSave(selected.filter { it in assetIds }) }) { Text("保存") }
                }
            }
        }
    }
}

@Composable
private fun LocalModelAssetRow(
    asset: app.inku.mobile.data.db.ModelAssetEntity,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    onAcceptModelLicense: () -> Unit,
    onDownloadModel: () -> Unit,
    onRedownloadModel: () -> Unit,
) {
    val isReady = asset.downloadState == "ready"
    val isBusy = asset.downloadState in setOf("queued", "connecting", "downloading", "verifying")
    val progressValue = if (asset.bytesTotal != null && asset.bytesTotal > 0L) {
        (asset.bytesDownloaded.toFloat() / asset.bytesTotal.toFloat()).coerceIn(0f, 1f)
    } else {
        null
    }
    val progress = if (asset.bytesTotal != null && asset.bytesTotal > 0L) {
        val percent = (asset.bytesDownloaded * 100.0 / asset.bytesTotal).coerceIn(0.0, 100.0)
        " ${"%.1f".format(percent)}%"
    } else {
        ""
    }
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(Dimens.radiusCard),
        color = InkSurface,
        border = BorderStroke(Dimens.hairline, CardHairline),
    ) {
        Column(
            modifier = Modifier.padding(Dimens.spaceM),
            verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
            ) {
                Checkbox(checked = checked, onCheckedChange = onCheckedChange)
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                    Text(asset.displayName, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(asset.qualityTier, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                }
                StatusPill(modelStatusLabel(asset.downloadState), modelStatusColor(asset.downloadState))
            }
            progressValue?.let {
                LinearProgressIndicator(
                    progress = { it },
                    modifier = Modifier.fillMaxWidth().height(Dimens.spaceXs),
                    color = if (isReady) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.primary,
                    trackColor = ProgressTrack,
                )
            }
            Text(
                "状態: ${modelStatusLabel(asset.downloadState)}$progress",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                when {
                    asset.licenseAcceptedAt == null -> {
                        SecondarySmallButton(text = "ライセンス同意", onClick = onAcceptModelLicense)
                    }
                    isReady -> {
                        SecondarySmallButton(text = "再取得", onClick = onRedownloadModel, enabled = !isBusy)
                    }
                    else -> {
                        SecondarySmallButton(text = "再取得", onClick = onRedownloadModel, enabled = !isBusy)
                        Spacer(modifier = Modifier.width(Dimens.spaceM))
                        PrimarySmallButton(text = if (isBusy) "取得中" else "ダウンロード", onClick = onDownloadModel, enabled = !isBusy)
                    }
                }
            }
        }
    }
}

@Composable
private fun ModelPickerActionButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    OutlinedButton(
        onClick = onClick,
        modifier = modifier.height(Dimens.buttonHeightSmall),
        shape = RoundedCornerShape(Dimens.radiusCard),
        contentPadding = PaddingValues(horizontal = Dimens.spaceXs, vertical = 0.dp),
    ) {
        Text(text, maxLines = 1, overflow = TextOverflow.Clip, fontSize = TypeScale.labelTiny)
    }
}

@Composable
private fun AddProviderCard(
    onAdd: (String, String, String, String, String, String) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    var providerId by remember { mutableStateOf("") }
    var displayName by remember { mutableStateOf("") }
    var kind by remember { mutableStateOf("openai-compatible") }
    var baseUrl by remember { mutableStateOf("") }
    var apiKey by remember { mutableStateOf("") }
    SecondaryActionButton(text = "AIサービスを追加", onClick = { open = true })
    if (open) {
        AlertDialog(
            onDismissRequest = { open = false },
            title = { Text("AIサービスを追加") },
            text = {
                Column(
                    modifier = Modifier.fillMaxWidth().height(Dimens.addProviderCardHeight).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                ) {
                    ImeAwareOutlinedTextField(value = providerId, onValueChange = { providerId = it }, label = "サービスID", modifier = Modifier.fillMaxWidth(), singleLine = true)
                    ImeAwareOutlinedTextField(value = displayName, onValueChange = { displayName = it }, label = "サービス名", modifier = Modifier.fillMaxWidth(), singleLine = true)
                    CompactLabel("接続形式")
                    WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
                        listOf("openai-compatible" to "OpenAI compatible", "anthropic" to "Claude API", "gemini" to "Gemini API").forEach { (value, label) ->
                            MiniPill(label, selected = kind == value, onClick = { kind = value })
                        }
                    }
                    ImeAwareOutlinedTextField(value = baseUrl, onValueChange = { baseUrl = it }, label = "Base URL", modifier = Modifier.fillMaxWidth(), singleLine = true)
                    ImeAwareOutlinedTextField(value = apiKey, onValueChange = { apiKey = it }, label = "APIキー", modifier = Modifier.fillMaxWidth(), singleLine = true)
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        onAdd(providerId, displayName, kind, baseUrl, apiKey, "")
                        open = false
                    },
                    enabled = providerId.isNotBlank(),
                ) { Text("追加") }
            },
            dismissButton = {
                TextButton(onClick = { open = false }) { Text("キャンセル") }
            },
        )
    }
}

@Composable
private fun SettingsListItem(mark: String, title: String, sub: String, onClick: () -> Unit, active: Boolean = false) {
    Surface(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape = RoundedCornerShape(Dimens.radiusCard),
        color = if (active) ActiveSettingsRowTint else Color.Transparent,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = Dimens.spaceL, vertical = Dimens.spaceL),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceL),
        ) {
            Box(
                modifier = Modifier.size(Dimens.iconTileSize).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(Dimens.radiusCard)),
                contentAlignment = Alignment.Center,
            ) {
                Text(mark, style = MaterialTheme.typography.titleMedium)
            }
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Medium)
                Text(sub, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Text("›", style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private fun settingsPaneTitle(pane: SettingsPane): String = when (pane) {
    SettingsPane.Home -> "設定"
    SettingsPane.ModelSelection -> "モデル選択"
    SettingsPane.Models -> "モデル設定"
    SettingsPane.Demo -> "デモ"
    SettingsPane.Export -> "エクスポート"
    SettingsPane.Misc -> "その他"
    SettingsPane.Version -> "バージョン情報"
}

private fun settingsPaneSubtitle(pane: SettingsPane): String = when (pane) {
    SettingsPane.Home -> "List + Detail"
    SettingsPane.ModelSelection -> "Stage 1 / Stage 2 共通"
    SettingsPane.Models -> "OpenAI / Claude / Gemini / NVIDIA"
    SettingsPane.Demo -> "実行 / seed phrase / interval"
    SettingsPane.Export -> "PNG / SVG templates"
    SettingsPane.Misc -> "言語・テーマ・密度"
    SettingsPane.Version -> "version / build"
}

@Composable
private fun SettingCheckRow(checked: Boolean, text: String, onCheckedChange: (Boolean) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().clickable { onCheckedChange(!checked) },
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
    ) {
        Checkbox(checked = checked, onCheckedChange = onCheckedChange)
        Text(text, style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
    }
}

@Composable
private fun SettingChoiceRow(
    title: String,
    selected: HistorySelectionBehavior,
    onSelect: (HistorySelectionBehavior) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
        CompactLabel(title)
        Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM), modifier = Modifier.fillMaxWidth()) {
            if (selected == HistorySelectionBehavior.History) {
                PrimarySmallButton("履歴の値", onClick = { onSelect(HistorySelectionBehavior.History) }, modifier = Modifier.weight(1f))
                SecondarySmallButton("現在値を維持", onClick = { onSelect(HistorySelectionBehavior.Current) }, modifier = Modifier.weight(1f))
            } else {
                SecondarySmallButton("履歴の値", onClick = { onSelect(HistorySelectionBehavior.History) }, modifier = Modifier.weight(1f))
                PrimarySmallButton("現在値を維持", onClick = { onSelect(HistorySelectionBehavior.Current) }, modifier = Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun ExportTemplateRow(template: app.inku.mobile.data.db.ExportTemplateEntity, viewModel: InkuViewModel) {
    var name by remember(template.id, template.name) { mutableStateOf(template.name) }
    var description by remember(template.id, template.description) { mutableStateOf(template.description) }
    var height by remember(template.id, template.heightPx) { mutableStateOf(template.heightPx.toString()) }
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(Dimens.radiusCard),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(Dimens.spaceM), verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
            ImeAwareOutlinedTextField(name, { name = it }, label = "名前", modifier = Modifier.fillMaxWidth(), singleLine = true)
            ImeAwareOutlinedTextField(description, { description = it }, label = "説明", modifier = Modifier.fillMaxWidth(), singleLine = true)
            ImeAwareOutlinedTextField(height, { height = it.filter(Char::isDigit) }, label = "Y軸px", modifier = Modifier.fillMaxWidth(), singleLine = true)
            Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM), modifier = Modifier.fillMaxWidth()) {
                SecondarySmallButton(
                    text = "削除",
                    onClick = { viewModel.removeExportTemplate(template.id) },
                    modifier = Modifier.weight(1f),
                )
                PrimarySmallButton(
                    text = "保存",
                    onClick = { viewModel.updateExportTemplate(template, name, description, height.toIntOrNull() ?: template.heightPx) },
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

@Composable
private fun ModelChoiceRow(
    choices: List<ModelChoice>,
    selectedValue: String,
    onSelect: (String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
        WrapRow {
            choices.forEach { choice ->
                val rec = app.inku.mobile.data.model.ModelRecommendations.items.find { it.modelId == choice.id }
                val badgeText = if (rec != null) " (推奨: S${rec.recommendedStage})" else ""
                MiniPill(
                    text = "${choice.providerName.take(10)} / ${choice.label.take(18)}$badgeText",
                    selected = choice.id == selectedValue,
                    onClick = { onSelect(choice.id) },
                )
            }
        }
    }
}

private fun parsePublishedModelIds(value: String): List<String> {
    synchronized(PublishedModelIdCache) {
        PublishedModelIdCache[value]?.let { return it }
    }
    val parsed = runCatching {
        val array = JSONArray(value)
        (0 until array.length()).mapNotNull { array.optString(it).takeIf { id -> id.isNotBlank() } }
    }.getOrElse {
        value.lines().map { it.trim() }.filter { it.isNotBlank() }
    }
    synchronized(PublishedModelIdCache) {
        PublishedModelIdCache[value] = parsed
    }
    return parsed
}

private val PublishedModelIdCache = object : LinkedHashMap<String, List<String>>(64, 0.75f, true) {
    override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, List<String>>?): Boolean = size > 64
}

private fun connectionKindOptions(): List<Pair<String, String>> {
    return listOf(
        "openai_compatible" to "OpenAI compatible",
        "anthropic" to "Anthropic",
        "gemini" to "Gemini",
        "litert-lm" to "LiteRT-LM",
    )
}

private fun connectionKindLabel(value: String): String {
    return when (value) {
        "openai_compatible", "openai-compatible" -> "OpenAI compatible"
        "anthropic" -> "Anthropic"
        "gemini" -> "Gemini"
        "litert-lm" -> "LiteRT-LM"
        else -> value.ifBlank { "OpenAI compatible" }
    }
}

private fun providerModelCandidates(provider: app.inku.mobile.data.db.ProviderSettingEntity, fetchedModelIds: List<String>): List<ProviderModelCandidate> {
    val defaults = when (provider.providerId) {
        "local-litert-lm" -> listOf(
            ProviderModelCandidate("local-litert-lm:gemma-4-e2b", "Gemma 4 E2B", "LiteRT-LM"),
            ProviderModelCandidate("local-litert-lm:gemma-4-e4b", "Gemma 4 E4B", "LiteRT-LM"),
        )
        "openai" -> listOf(
            ProviderModelCandidate("openai:gpt-5.1", "GPT-5.1"),
            ProviderModelCandidate("openai:gpt-5.1-mini", "GPT-5.1 mini"),
            ProviderModelCandidate("openai:gpt-4.1", "GPT-4.1"),
            ProviderModelCandidate("openai:gpt-4.1-mini", "GPT-4.1 mini"),
        )
        "nvidia" -> listOf(
            ProviderModelCandidate("google/gemma-4-31b-it", "Google Gemma 4 31B Instruct"),
            ProviderModelCandidate("meta/llama-3.3-70b-instruct", "Meta Llama 3.3 70B Instruct"),
            ProviderModelCandidate("mistralai/mistral-large-2-instruct", "Mistral AI Mistral Large 2 Instruct"),
        )
        "anthropic" -> listOf(
            ProviderModelCandidate("anthropic:claude-opus-4-7", "Claude Opus 4.7"),
            ProviderModelCandidate("anthropic:claude-sonnet-4-6", "Claude Sonnet 4.6"),
            ProviderModelCandidate("anthropic:claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
        )
        "gemini" -> listOf(
            ProviderModelCandidate("gemini:gemini-2.5-pro", "Gemini 2.5 Pro"),
            ProviderModelCandidate("gemini:gemini-2.5-flash", "Gemini 2.5 Flash"),
            ProviderModelCandidate("gemini:gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite"),
        )
        "ollama" -> listOf(
            ProviderModelCandidate("ollama:llama3.2", "Llama 3.2"),
            ProviderModelCandidate("ollama:gpt-oss:20b", "gpt-oss 20B"),
            ProviderModelCandidate("ollama:qwen3:8b", "Qwen3 8B"),
        )
        "ovms" -> listOf(
            ProviderModelCandidate("qwen3-api", "Qwen3 8B Instruct", "thinking"),
            ProviderModelCandidate("qwen-api", "Qwen2.5 7B Instruct"),
            ProviderModelCandidate("gemma3-12b-api", "Google Gemma 3 12B Instruct"),
            ProviderModelCandidate("gemma3-4b-api", "Google Gemma 3 4B Instruct"),
        )
        else -> emptyList()
    }
    val fetched = fetchedModelIds.map { id ->
        ProviderModelCandidate(id, modelDisplayName(id), id)
    }
    val stored = parsePublishedModelIds(provider.publishedModelsJson).map { id ->
        ProviderModelCandidate(id, modelDisplayName(id), id)
    }
    return (defaults + fetched + stored).distinctBy { it.id }
}

private fun modelChoicesFor(state: InkuUiState): List<ModelChoice> {
    val choices = mutableListOf<ModelChoice>()
    state.modelAssets.forEach { asset ->
        choices += ModelChoice(asset.modelId, "${asset.displayName} ${asset.qualityTier}", "LiteRT-LM")
    }
    state.providerSettings
        .filter { it.isEnabled && !it.isDefaultLocal }
        .forEach { provider ->
            parsePublishedModelIds(provider.publishedModelsJson).forEach { modelId ->
                val qualified = qualifyModelId(provider.providerId, modelId)
                choices += ModelChoice(qualified, modelDisplayName(modelId), provider.displayName)
            }
        }
    return choices.distinctBy { it.id }
}

private fun modelProviderGroupsFor(state: InkuUiState): List<app.inku.mobile.data.db.ProviderSettingEntity> {
    val local = state.providerSettings.filter { it.isDefaultLocal }
    val remote = state.providerSettings.filter { it.isEnabled && !it.isDefaultLocal }
    return (local + remote).distinctBy { it.providerId }
}

private fun modelOptionsForProvider(state: InkuUiState, providerId: String): List<ModelOptionChoice> {
    if (providerId == "local-litert-lm") {
        return state.modelAssets.map { asset ->
            ModelOptionChoice(
                rawId = asset.modelId,
                qualifiedId = asset.modelId,
                label = "${asset.displayName} ${asset.qualityTier}",
                notes = modelChoiceStatusLabel(asset.downloadState),
            )
        }
    }
    val provider = state.providerSettings.firstOrNull { it.providerId == providerId } ?: return emptyList()
    return parsePublishedModelIds(provider.publishedModelsJson).map { id ->
        ModelOptionChoice(
            rawId = id,
            qualifiedId = qualifyModelId(provider.providerId, id),
            label = modelDisplayName(id),
            notes = id,
        )
    }
}

private fun providerOfModelId(modelId: String, state: InkuUiState): String {
    state.providerSettings.firstOrNull { modelId.startsWith("${it.providerId}:") }?.let { return it.providerId }
    state.providerSettings.firstOrNull { provider ->
        parsePublishedModelIds(provider.publishedModelsJson).contains(modelId)
    }?.let { return it.providerId }
    return "local-litert-lm"
}

private fun modelChoiceStatusLabel(downloadState: String): String {
    return when (downloadState) {
        "ready" -> "ready"
        "ready_to_download" -> "取得可能"
        "license_required" -> "ライセンス同意が必要"
        else -> downloadState
    }
}

private fun qualifyModelId(providerId: String, modelId: String): String {
    return if (modelId.startsWith("$providerId:")) modelId else "$providerId:$modelId"
}

private fun modelDisplayName(modelId: String): String {
    return when (modelId.removePrefix("nvidia:")) {
        "google/gemma-4-31b-it" -> "Gemma 4 31B Instruct"
        "meta/llama-3.3-70b-instruct" -> "Llama 3.3 70B Instruct"
        "mistralai/mistral-large-2-instruct" -> "Mistral Large 2 Instruct"
        else -> modelId.substringAfterLast(":")
    }
}

private fun formatDuration(ms: Long): String {
    return "${"%.1f".format(ms / 1000.0)}s"
}

@Composable
private fun SettingsCard(title: String, sub: String, status: String, titleAction: (@Composable () -> Unit)? = null, actions: @Composable () -> Unit) {
    Card(
        shape = RoundedCornerShape(Dimens.radiusCard),
        colors = CardDefaults.cardColors(containerColor = SettingsCardSurface),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier
                .border(Dimens.hairline, CardHairline, RoundedCornerShape(Dimens.radiusCard))
                .padding(Dimens.spaceL),
            verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(title, style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                titleAction?.invoke()
            }
            Text(sub, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (status.isNotBlank()) {
                Text(status, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
            }
            actions()
        }
    }
}

@Composable
private fun ModelAssetControls(
    asset: app.inku.mobile.data.db.ModelAssetEntity,
    onOpenLicenseDownload: () -> Unit,
) {
    val isReady = asset.downloadState == "ready"
    val isBusy = asset.downloadState in setOf("queued", "connecting", "downloading", "verifying")
    val progressValue = if (asset.bytesTotal != null && asset.bytesTotal > 0L) {
        (asset.bytesDownloaded.toFloat() / asset.bytesTotal.toFloat()).coerceIn(0f, 1f)
    } else {
        null
    }
    val progress = if (asset.bytesTotal != null && asset.bytesTotal > 0L) {
        val percent = (asset.bytesDownloaded * 100.0 / asset.bytesTotal).coerceIn(0.0, 100.0)
        " ${"%.1f".format(percent)}%"
    } else {
        ""
    }
    val path = asset.localPath?.substringAfterLast("/") ?: "not stored"
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(Dimens.radiusCard),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier
                .border(Dimens.hairline, CardHairline, RoundedCornerShape(Dimens.radiusCard))
                .padding(Dimens.spaceL),
            verticalArrangement = Arrangement.spacedBy(Dimens.spaceM),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Dimens.spaceL)) {
                Box(
                    modifier = Modifier.size(Dimens.iconTileSize).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(Dimens.radiusCard)),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(if (asset.qualityTier.contains("high", ignoreCase = true)) "E4" else "E2", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
                }
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
                    Text(asset.displayName, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(asset.qualityTier, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                }
                StatusPill(modelStatusLabel(asset.downloadState), modelStatusColor(asset.downloadState))
            }

            progressValue?.let {
                LinearProgressIndicator(
                    progress = { it },
                    modifier = Modifier.fillMaxWidth().height(Dimens.spaceXs),
                    color = if (isReady) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.primary,
                    trackColor = ProgressTrack,
                )
            }
            Text(
                "${asset.downloadState}$progress · $path",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            PrimarySmallButton(
                text = when {
                    isReady -> "ライセンス/取得済み"
                    isBusy -> "取得状況"
                    asset.licenseAcceptedAt != null -> "ダウンロード"
                    else -> "ライセンス/ダウンロード"
                },
                onClick = onOpenLicenseDownload,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun ModelAssetLicenseDownloadDialog(
    asset: app.inku.mobile.data.db.ModelAssetEntity,
    onDismiss: () -> Unit,
    onAccept: () -> Unit,
    onDownload: () -> Unit,
    onRedownload: () -> Unit,
) {
    val isReady = asset.downloadState == "ready"
    val isBusy = asset.downloadState in setOf("queued", "connecting", "downloading", "verifying")
    val progress = if (asset.bytesTotal != null && asset.bytesTotal > 0L) {
        val percent = (asset.bytesDownloaded * 100.0 / asset.bytesTotal).coerceIn(0.0, 100.0)
        " ${"%.1f".format(percent)}%"
    } else {
        ""
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("${asset.displayName} の取得") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                Text("LiteRT-LM でローカル実行する Gemma モデルです。")
                Text("品質: ${asset.qualityTier}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("状態: ${modelStatusLabel(asset.downloadState)}$progress", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(
                    if (asset.licenseAcceptedAt != null) {
                        "ライセンスは同意済みです。"
                    } else {
                        "ダウンロード前に Gemma のライセンス同意が必要です。"
                    },
                    style = MaterialTheme.typography.bodySmall,
                )
                asset.licenseUrl?.let {
                    Text("License: $it", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        },
        confirmButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                TextButton(
                    onClick = onRedownload,
                    enabled = asset.licenseAcceptedAt != null && !isBusy,
                ) {
                    Text("再取得")
                }
                TextButton(
                    onClick = onDownload,
                    enabled = asset.licenseAcceptedAt != null && !isReady && !isBusy,
                ) {
                    Text(
                        when {
                            isReady -> "取得済み"
                            isBusy -> "取得中"
                            else -> "ダウンロード"
                        },
                    )
                }
            }
        },
        dismissButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                TextButton(onClick = onDismiss) { Text("閉じる") }
                TextButton(onClick = onAccept, enabled = asset.licenseAcceptedAt == null) {
                    Text(if (asset.licenseAcceptedAt != null) "同意済み" else "ライセンス同意")
                }
            }
        },
    )
}

@Composable
private fun SettingsSectionHeader(label: String, title: String) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = Dimens.spaceXs),
        verticalAlignment = Alignment.Bottom,
        horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
    ) {
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun StatusPill(text: String, color: Color) {
    Text(
        text,
        modifier = Modifier
            .background(color.copy(alpha = 0.18f), RoundedCornerShape(100))
            .border(Dimens.hairline, color.copy(alpha = 0.42f), RoundedCornerShape(100))
            .padding(horizontal = Dimens.spaceM, vertical = Dimens.spaceXs),
        style = MaterialTheme.typography.labelSmall,
        color = color,
        maxLines = 1,
    )
}

private fun modelStatusLabel(state: String?): String = when (state) {
    "ready" -> "READY"
    "queued" -> "QUEUED"
    "connecting" -> "CONNECT"
    "downloading" -> "GETTING"
    "verifying" -> "VERIFY"
    "failed" -> "FAILED"
    "cancelled" -> "STOPPED"
    "ready_to_download" -> "LICENSED"
    else -> "LOCAL"
}

@Composable
private fun modelStatusColor(state: String?): Color = when (state) {
    "ready" -> MaterialTheme.colorScheme.secondary
    "queued", "connecting", "downloading", "verifying" -> MaterialTheme.colorScheme.primary
    "failed", "cancelled" -> StatusFailed
    "ready_to_download" -> StatusReady
    else -> MaterialTheme.colorScheme.onSurfaceVariant
}

@Composable
private fun HorizontalChoiceRow(
    values: List<Pair<String, String>>,
    selectedValue: String,
    onSelect: (String) -> Unit,
) {
    WrapRow {
        values.forEach { (value, label) ->
            if (value == selectedValue) {
                PrimarySmallButton(text = label, onClick = { onSelect(value) })
            } else {
                SecondarySmallButton(text = label, onClick = { onSelect(value) })
            }
        }
    }
}

@Composable
private fun ColorCatalogButtonRow(selectedValue: String, onSelect: (String) -> Unit) {
    WrapRow {
        ColorCatalogs.all.forEach { catalog ->
            val selected = catalog.id == selectedValue
            OutlinedButton(
                onClick = { onSelect(catalog.id) },
                modifier = Modifier.height(Dimens.buttonHeightLarge).fillMaxWidth(),
                shape = RoundedCornerShape(Dimens.radiusCard),
                colors = if (selected) {
                    ButtonDefaults.outlinedButtonColors(
                        containerColor = MaterialTheme.colorScheme.secondary,
                        contentColor = InkOnSecondary,
                    )
                } else {
                    ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.onSurfaceVariant)
                },
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                    SwatchStrip(catalog.swatches.take(4))
                    Text(catalog.name, maxLines = 1)
                }
            }
        }
    }
}

@Composable
private fun SwatchStrip(colors: List<String>) {
    Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
        colors.forEach { hex ->
            Box(
                modifier = Modifier
                    .size(Dimens.spaceL)
                    .background(parseColor(hex), RoundedCornerShape(Dimens.radiusCard))
                    .border(Dimens.hairline, SwatchHairline, RoundedCornerShape(Dimens.radiusCard)),
            )
        }
    }
}

private fun selectedModelLabel(state: InkuUiState): String {
    modelChoicesFor(state).firstOrNull { it.id == state.selectedModelId }?.let { return it.label }
    return state.modelAssets.firstOrNull { it.modelId == state.selectedModelId }?.displayName
        ?: state.selectedModelId.substringAfterLast(":")
}

private fun shortCatalogLabel(state: InkuUiState): String {
    return ColorCatalogs.get(state.selectedCatalogId).name.compactLabel(12)
}

private fun shortModelLabel(state: InkuUiState): String {
    return selectedModelLabel(state).compactLabel(14)
}

private fun String.compactLabel(maxChars: Int): String {
    val clean = trim().replace(Regex("\\s+"), " ")
    if (clean.length <= maxChars) return clean
    return clean.take(maxChars - 1).trimEnd() + "…"
}

private fun selectedStage2ModelLabel(state: InkuUiState): String {
    modelChoicesFor(state).firstOrNull { it.id == state.selectedStage2ModelId }?.let { return it.label }
    return state.modelAssets.firstOrNull { it.modelId == state.selectedStage2ModelId }?.displayName
        ?: state.selectedStage2ModelId.substringAfterLast(":")
}

@Composable
private fun CanvasPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    val item = state.selectedHistory
    Surface(
        modifier = modifier.border(Dimens.hairline, CanvasPanelHairline, RoundedCornerShape(Dimens.radiusCard)),
        color = CanvasPanelSurface,
        shape = RoundedCornerShape(Dimens.radiusCard),
    ) {
        Column(modifier = Modifier.fillMaxSize().padding(Dimens.spaceM), verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Dimens.spaceL)) {
                RenderTab.entries.forEach { tab ->
                    Text(
                        when (tab) {
                            RenderTab.Artwork -> "描画"
                            RenderTab.Prompt -> "プロンプト"
                            RenderTab.Json -> "JSON"
                        },
                        modifier = Modifier.clickable { viewModel.setRenderTab(tab) },
                        style = MaterialTheme.typography.labelLarge,
                        color = if (state.renderTab == tab) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Spacer(Modifier.weight(1f))
                item?.let { Text("F${it.renderHashShort}  ${it.canvasAspect}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.secondary) }
            }
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .background(ChipSurface, RoundedCornerShape(Dimens.radiusCard))
                    .padding(Dimens.spaceM),
                contentAlignment = Alignment.Center,
            ) {
                if (item == null) {
                    Text("No render yet", color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    when (state.renderTab) {
                        RenderTab.Artwork -> ArtworkPreview(item, modifier = Modifier.fillMaxSize())
                        RenderTab.Prompt -> RenderTextView(renderPromptText(item, state.litertStage1PromptOptimization), Modifier.fillMaxSize())
                        RenderTab.Json -> RenderTextView(renderJsonText(item), Modifier.fillMaxSize())
                    }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    state.message ?: "LLM ${selectedModelLabel(state)} · 指示文生成/Stage1/2共通",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun RenderTextView(text: String, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .background(RenderTextPaper, RoundedCornerShape(Dimens.radiusCard))
            .padding(Dimens.spaceM)
            .verticalScroll(rememberScrollState()),
    ) {
        Text(text, color = RenderTextInk, style = MaterialTheme.typography.bodySmall)
    }
}

private fun renderPromptText(item: HistoryItemEntity, litertStage1PromptOptimization: Boolean): String {
    val usesLiteRt = item.stage1Model.isLiteRtModelId() || item.stage2Model.isLiteRtModelId()
    val stage1System = if (usesLiteRt && litertStage1PromptOptimization) {
        WebDdlSpec.buildStage1LiteRtSystemPrompt(item.originalInput)
    } else {
        WebDdlSpec.stage1SystemPromptForDisplay()
    }
    val stage2System = if (usesLiteRt) {
        WebDdlSpec.stage2LiteRtSystemPromptForDisplay()
    } else {
        WebDdlSpec.stage2SystemPromptForDisplay()
    }
    return buildString {
        appendLine("Stage 1 input:")
        appendLine(item.originalInput)
        appendLine()
        appendLine("Stage 1 system:")
        appendLine(stage1System)
        appendLine()
        appendLine("Stage 2 input:")
        appendLine(item.normalizedDdl)
        appendLine()
        appendLine("Stage 2 system:")
        appendLine(stage2System)
    }
}

private fun String?.isLiteRtModelId(): Boolean {
    return this?.startsWith("local-litert-lm:") == true
}

private fun renderJsonText(item: HistoryItemEntity): String {
    val metadata = runCatching { JSONObject(item.renderMetadataJson) }.getOrElse { JSONObject() }
    val payload = JSONObject()
    payload.putIfNotBlank("stage1_model", item.stage1Model)
    payload.putIfNotBlank("stage2_model", item.stage2Model)
    payload.putFrom(metadata, "render_build_number")
    payload.putFrom(metadata, "render_color_profile")
    payload.putFrom(metadata, "render_engine_id")
    payload.putFrom(metadata, "render_engine_version")
    payload.putFrom(metadata, "render_canvas_aspect", item.canvasAspect)
    payload.putFrom(metadata, "render_canvas_aspect_id", item.canvasAspect)
    payload.putFrom(metadata, "render_canvas_aspect_ratio", CanvasAspects.ratioFor(item.canvasAspect))
    payload.put("render_hash", item.renderHash)
    payload.put("render_hash_short", item.renderHashShort)
    payload.putFrom(metadata, "render_color_catalog_id", item.colorCatalogId)
    payload.putFrom(metadata, "render_color_catalog_name")
    payload.putFrom(metadata, "render_color_catalog_sub")
    payload.putFrom(metadata, "render_color_map")
    payload.put("score", runCatching { JSONObject(item.scoreJson) }.getOrElse { JSONObject().put("raw", item.scoreJson) })
    return payload.toString(2)
}

private fun JSONObject.putIfNotBlank(key: String, value: String?) {
    if (!value.isNullOrBlank()) put(key, value)
}

private fun JSONObject.putFrom(source: JSONObject, key: String, fallback: Any? = null) {
    if (source.has(key) && !source.isNull(key)) {
        put(key, source.get(key))
    } else if (fallback != null && fallback != "") {
        put(key, fallback)
    }
}

private data class SharePayload(
    val uri: Uri,
    val mimeType: String,
    val subject: String,
    val clipLabel: String,
    val chooserTitle: String,
)

private suspend fun shareHistoryJson(context: Context, item: HistoryItemEntity) {
    val payload = withContext(Dispatchers.IO) { buildHistoryJsonPayload(context, item) }
    launchShareIntent(context, payload)
}

private suspend fun shareHistorySvg(context: Context, item: HistoryItemEntity, profile: String = "display") {
    val payload = withContext(Dispatchers.IO) { buildHistorySvgPayload(context, item, profile) }
    launchShareIntent(context, payload)
}

private suspend fun shareHistoryPng(context: Context, item: HistoryItemEntity, targetHeight: Int) {
    val payload = withContext(Dispatchers.IO) { buildHistoryPngPayload(context, item, targetHeight) }
    launchShareIntent(context, payload)
}

private fun buildHistoryJsonPayload(context: Context, item: HistoryItemEntity): SharePayload {
    val exportDir = File(context.cacheDir, "exports")
    exportDir.mkdirs()
    val file = File(exportDir, "inku-${item.renderHashShort}.json")
    file.writeText(historyExportJson(item).toString(2), Charsets.UTF_8)
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    return SharePayload(uri, "application/json", "inku ${item.renderHashShort}", file.name, "Export inku JSON")
}

private fun buildHistorySvgPayload(context: Context, item: HistoryItemEntity, profile: String): SharePayload {
    val normalizedProfile = profile.takeIf { it in setOf("display", "editable", "compat") } ?: "display"
    val exportDir = File(context.cacheDir, "exports")
    exportDir.mkdirs()
    val ext = if (normalizedProfile == "display") "svg" else "$normalizedProfile.svg"
    val file = File(exportDir, "inku-${item.renderHashShort}.$ext")
    file.writeText(svgForExport(item, normalizedProfile), Charsets.UTF_8)
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    return SharePayload(uri, "image/svg+xml", "inku ${item.renderHashShort}", file.name, "Export inku SVG")
}

private fun buildHistoryPngPayload(context: Context, item: HistoryItemEntity, targetHeight: Int): SharePayload {
    val svg = SVG.getFromString(item.displaySvg)
    val documentWidth = svg.documentWidth.takeIf { it > 0f } ?: 1000f
    val documentHeight = svg.documentHeight.takeIf { it > 0f } ?: 1000f
    val height = targetHeight.coerceIn(64, MaxPngExportHeightPx)
    val width = (height * documentWidth / documentHeight).toInt().coerceAtLeast(64)
    val estimatedBytes = width.toLong() * height.toLong() * 4L
    require(estimatedBytes <= MaxPngExportBitmapBytes) {
        "PNG出力サイズが大きすぎます。キャンバス比率または出力サイズを下げてください。"
    }
    val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
    val canvas = AndroidCanvas(bitmap)
    svg.setDocumentWidth(width.toFloat())
    svg.setDocumentHeight(height.toFloat())
    svg.renderToCanvas(canvas)
    val exportDir = File(context.cacheDir, "exports")
    exportDir.mkdirs()
    val file = File(exportDir, "inku-${item.renderHashShort}-${height}.png")
    FileOutputStream(file).use { out ->
        bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)
    }
    bitmap.recycle()
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    return SharePayload(uri, "image/png", "inku ${item.renderHashShort}", file.name, "Export inku PNG")
}

private const val MaxPngExportHeightPx = 4320
private const val MaxPngExportBitmapBytes = 128L * 1024L * 1024L

private fun launchShareIntent(context: Context, payload: SharePayload) {
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = payload.mimeType
        putExtra(Intent.EXTRA_SUBJECT, payload.subject)
        putExtra(Intent.EXTRA_STREAM, payload.uri)
        clipData = ClipData.newUri(context.contentResolver, payload.clipLabel, payload.uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(intent, payload.chooserTitle))
}

private fun svgForExport(item: HistoryItemEntity, profile: String): String {
    val metadata = JSONObject()
        .put("generator", "inku")
        .put("svg_profile", profile)
        .put("source", "android")
    val title = "inku render ($profile SVG)"
    val desc = when (profile) {
        "editable" -> "Generated by inku. Groups and IDs are included for vector editing."
        else -> item.originalInput.ifBlank { "Generated by inku. Portable SVG output." }
    }
    val documentMetadata = "<title>${escapeXml(title)}</title>" +
        "<desc>${escapeXml(desc)}</desc>" +
        "<metadata id=\"inku_metadata\">${escapeXml(metadata.toString())}</metadata>"
    val match = Regex("(<svg\\b[^>]*>)").find(item.displaySvg) ?: return item.displaySvg
    return item.displaySvg.replaceRange(match.range.last + 1, match.range.last + 1, documentMetadata)
}

private fun escapeXml(value: String): String {
    return value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\"", "&quot;")
}

private fun historyExportJson(item: HistoryItemEntity): JSONObject {
    return JSONObject().apply {
        put("schema", "inku.history_item")
        put("schema_version", "0.1.0")
        put("id", item.id)
        put("created_at", item.createdAt)
        put("updated_at", item.updatedAt)
        put("original_input", item.originalInput)
        put("normalized_ddl", item.normalizedDdl)
        put("expanded_ddl", item.expandedDdl)
        put("score_json", JSONObject(item.scoreJson))
        put("display_svg", item.displaySvg)
        put("stage1_model", item.stage1Model)
        put("stage2_model", item.stage2Model)
        put("render_metadata", JSONObject(item.renderMetadataJson))
        put("render_hash", item.renderHash)
        put("render_hash_short", item.renderHashShort)
        put("color_catalog_id", item.colorCatalogId)
        put("canvas_aspect", item.canvasAspect)
        put("starred", item.starred)
        put("trashed", item.trashed)
        put("elapsed_ms", item.elapsedMs)
        put("token_metadata", item.tokenMetadataJson?.let { JSONObject(it) })
    }
}

private fun filterHistoryItems(history: List<HistoryListItem>, state: InkuUiState): List<HistoryListItem> {
    val query = state.historySearchQuery.trim().lowercase()
    return history.filter { item ->
        (!state.historyStarredOnly || item.starred) &&
            (query.isBlank() || item.searchText.contains(query))
    }
}

@Composable
private fun HistoryGridTile(
    item: HistoryListItem,
    selected: Boolean,
    onSelect: () -> Unit,
    onToggleStar: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier
            .combinedClickable(
                onClick = onSelect,
                onLongClick = onToggleStar,
            )
            .border(Dimens.spaceXs, if (selected) MaterialTheme.colorScheme.primary else Color.Transparent, RoundedCornerShape(0.dp))
            .border(Dimens.selectionRingWidth, if (selected) SelectionRing else Color.Transparent, RoundedCornerShape(0.dp)),
        shape = RoundedCornerShape(0.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
            Box {
                HistoryArtworkPreview(item, modifier = Modifier.fillMaxWidth().aspectRatio(1f))
                if (selected) {
                    Box(
                        modifier = Modifier
                            .width(Dimens.radiusCard)
                            .height(Dimens.radiusCard)
                            .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(bottomEnd = Dimens.radiusCard)),
                    )
                }
                if (item.starred) {
                    HistoryBadge(text = "★", selected = true, modifier = Modifier.align(Alignment.TopEnd).padding(Dimens.spaceM))
                }
            }
            Row(modifier = Modifier.padding(horizontal = Dimens.spaceM, vertical = Dimens.spaceM), verticalAlignment = Alignment.CenterVertically) {
                Text(historyTitle(item), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.fillMaxWidth())
            }
        }
    }
}

@Composable
private fun HistoryBadge(text: String, selected: Boolean = false, onClick: (() -> Unit)? = null, modifier: Modifier = Modifier) {
    val base = modifier
        .size(Dimens.badgeSize)
        .background(
            if (selected) MaterialTheme.colorScheme.secondary else HistoryBadgeSurface,
            RoundedCornerShape(100),
        )
    Box(
        modifier = onClick?.let { base.clickable(onClick = it) } ?: base,
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelSmall,
            color = if (selected) InkOnPrimary else MaterialTheme.colorScheme.onSurface,
            maxLines = 1,
        )
    }
}

private fun historyTitle(item: HistoryListItem): String {
    val original = item.originalInput.trim()
    if (original.isNotBlank() && !original.startsWith("{") && !original.startsWith("[")) {
        return original
    }
    val normalized = item.normalizedDdl.trim()
    if (normalized.isNotBlank() && !normalized.startsWith("{") && !normalized.startsWith("[")) {
        return normalized
    }
    return "DDLから描画"
}

@Composable
private fun CompactLabel(text: String) {
    Text(text, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@OptIn(ExperimentalFoundationApi::class)
private fun kotlinx.coroutines.CoroutineScope.launchImeBringIntoViewGuard(requester: BringIntoViewRequester) {
    launch {
        listOf(80L, 220L, 420L, 700L, 1000L).forEach { waitMs ->
            delay(waitMs)
            requester.bringIntoView()
        }
    }
}

@Composable
private fun DdlActionRow(state: InkuUiState, viewModel: InkuViewModel) {
    WrapRow(horizontal = Dimens.spaceM, vertical = Dimens.spaceM) {
        MiniPill("歳時記", selected = state.saijikiOpen, onClick = viewModel::toggleSaijiki)
        MiniPill("補正", selected = state.ddlAutoRepairEnabled, onClick = viewModel::toggleDdlAutoRepair)
    }
}

@Composable
private fun DdlPreviewBox(value: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val vocabularyTokens = rememberDdlVocabularyTokens()
    val visualTransformation = remember(vocabularyTokens) {
        DdlKeywordHighlightTransformation(vocabularyTokens)
    }
    var textLayoutResult by remember { mutableStateOf<TextLayoutResult?>(null) }
    Box(
        modifier = modifier
            .background(InputWellSurface, RoundedCornerShape(Dimens.radiusCard))
            .border(Dimens.hairline, MaterialTheme.colorScheme.outline, RoundedCornerShape(Dimens.radiusCard))
            .padding(horizontal = Dimens.spaceM, vertical = Dimens.spaceM)
            .clickable(onClick = onClick),
    ) {
        BasicTextField(
            value = value,
            onValueChange = {},
            readOnly = true,
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = Dimens.panelMinHeight)
                .pointerInput(value) {
                    detectTapGestures(onTap = { onClick() })
                }
                .drawBehind {
                    val layout = textLayoutResult ?: return@drawBehind
                    drawDdlKeywordHighlights(layout, value, vocabularyTokens)
                },
            textStyle = MaterialTheme.typography.bodySmall.copy(
                color = MaterialTheme.colorScheme.onSurface,
                lineHeight = TypeScale.denseLineHeight,
            ),
            cursorBrush = SolidColor(Color.Transparent),
            visualTransformation = visualTransformation,
            onTextLayout = { textLayoutResult = it },
            minLines = 6,
            maxLines = 10,
            decorationBox = { innerTextField ->
                if (value.isBlank()) {
                    Text(
                        "解釈を待機中...",
                        style = MaterialTheme.typography.bodySmall.copy(lineHeight = TypeScale.denseLineHeight),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    innerTextField()
                }
            },
        )
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun DenseMultilineInput(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    minLines: Int,
    maxLines: Int,
    enabled: Boolean = true,
    // The screen, not the field, decides what follows the keyboard, so the
    // focus has to leave the field.
    onFocusChanged: (Boolean) -> Unit = {},
) {
    val bringIntoViewRequester = remember { BringIntoViewRequester() }
    val scope = rememberCoroutineScope()
    BasicTextField(
        value = value,
        onValueChange = onValueChange,
        enabled = enabled,
        modifier = modifier
            .bringIntoViewRequester(bringIntoViewRequester)
            .onFocusChanged { focusState ->
                onFocusChanged(focusState.isFocused)
                if (focusState.isFocused) {
                    scope.launchImeBringIntoViewGuard(bringIntoViewRequester)
                }
            }
            .background(InputWellSurface, RoundedCornerShape(Dimens.radiusCard))
            .border(Dimens.hairline, MaterialTheme.colorScheme.outline, RoundedCornerShape(Dimens.radiusCard))
            .padding(horizontal = Dimens.spaceM, vertical = Dimens.spaceM),
        textStyle = MaterialTheme.typography.bodySmall.copy(
            color = MaterialTheme.colorScheme.onSurface,
            lineHeight = TypeScale.denseLineHeight,
        ),
        cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
        minLines = minLines,
        maxLines = maxLines,
    )
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun DenseTextFieldValueInput(
    value: TextFieldValue,
    onValueChange: (TextFieldValue) -> Unit,
    modifier: Modifier = Modifier,
    minLines: Int,
    maxLines: Int,
    enabled: Boolean = true,
    highlightTokens: List<DdlVocabularyToken> = emptyList(),
    selectWords: List<String> = emptyList(),
) {
    val bringIntoViewRequester = remember { BringIntoViewRequester() }
    val scope = rememberCoroutineScope()
    var textLayoutResult by remember { mutableStateOf<TextLayoutResult?>(null) }
    val visualTransformation = remember(highlightTokens) {
        DdlKeywordHighlightTransformation(highlightTokens)
    }
    val normalizedOnValueChange: (TextFieldValue) -> Unit = { nextValue ->
        val shouldSelectVocabulary =
            nextValue.text == value.text &&
                nextValue.selection.collapsed &&
                selectWords.isNotEmpty()
        if (shouldSelectVocabulary) {
            val selected = selectVocabularyAtOffset(nextValue, nextValue.selection.start, selectWords)
            onValueChange(selected)
        } else {
            onValueChange(nextValue)
        }
    }
    Box(
        modifier = modifier
            .bringIntoViewRequester(bringIntoViewRequester)
            .background(InputWellSurface, RoundedCornerShape(Dimens.radiusCard))
            .border(Dimens.hairline, MaterialTheme.colorScheme.outline, RoundedCornerShape(Dimens.radiusCard))
            .padding(horizontal = Dimens.spaceM, vertical = Dimens.spaceXs),
    ) {
        BasicTextField(
            value = value,
            onValueChange = normalizedOnValueChange,
            enabled = enabled,
            modifier = Modifier
                .fillMaxSize()
                .onFocusChanged { focusState ->
                    if (focusState.isFocused) {
                        scope.launchImeBringIntoViewGuard(bringIntoViewRequester)
                    }
                }
                .drawBehind {
                    val layout = textLayoutResult ?: return@drawBehind
                    drawDdlKeywordHighlights(layout, value.text, highlightTokens)
                },
            textStyle = MaterialTheme.typography.bodySmall.copy(
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = TypeScale.editorBody,
                lineHeight = TypeScale.editorLineHeight,
            ),
            cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
            visualTransformation = visualTransformation,
            onTextLayout = { textLayoutResult = it },
            minLines = minLines,
            maxLines = maxLines,
        )
    }
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawDdlKeywordHighlights(
    layout: TextLayoutResult,
    text: String,
    tokens: List<DdlVocabularyToken>,
) {
    if (text.isBlank() || tokens.isEmpty()) return
    val occupied = BooleanArray(text.length)
    val horizontalPad = Dimens.hairline.toPx()
    val verticalPad = Dimens.hairline.toPx()
    val radius = Dimens.highlightCorner.toPx()
    tokens.forEach { token ->
        val word = token.word
        if (word.isBlank()) return@forEach
        var start = text.indexOf(word)
        while (start >= 0) {
            val end = start + word.length
            val overlaps = (start until end).any { occupied[it] }
            if (!overlaps) {
                var segmentStart = start
                while (segmentStart < end) {
                    val line = layout.getLineForOffset(segmentStart)
                    val segmentEnd = minOf(end, layout.getLineEnd(line, visibleEnd = false))
                    val firstBox = layout.getBoundingBox(segmentStart)
                    val lastBox = layout.getBoundingBox(segmentEnd - 1)
                    val top = minOf(firstBox.top, lastBox.top) + verticalPad
                    val bottom = maxOf(firstBox.bottom, lastBox.bottom) - verticalPad
                    drawRoundRect(
                        color = token.color.copy(alpha = 0.92f),
                        topLeft = Offset(firstBox.left - horizontalPad, top),
                        size = Size((lastBox.right - firstBox.left) + horizontalPad * 2f, bottom - top),
                        cornerRadius = CornerRadius(radius, radius),
                    )
                    segmentStart = segmentEnd
                }
                for (i in start until end) occupied[i] = true
            }
            start = text.indexOf(word, startIndex = end)
        }
    }
}

private class DdlKeywordHighlightTransformation(
    private val tokens: List<DdlVocabularyToken>,
) : VisualTransformation {
    override fun filter(text: AnnotatedString): TransformedText {
        if (tokens.isEmpty() || text.text.isBlank()) {
            return TransformedText(text, OffsetMapping.Identity)
        }
        val builder = AnnotatedString.Builder(text)
        val occupied = BooleanArray(text.text.length)
        tokens.forEach { token ->
            val word = token.word
            if (word.isBlank()) return@forEach
            var start = text.text.indexOf(word)
            while (start >= 0) {
                val end = start + word.length
                val overlaps = (start until end).any { occupied[it] }
                if (!overlaps) {
                    builder.addStyle(
                        SpanStyle(
                            color = if (isLightColor(token.color)) PillInkOnLight else PillInkOnDark,
                        ),
                        start,
                        end,
                    )
                    for (i in start until end) occupied[i] = true
                }
                start = text.text.indexOf(word, startIndex = end)
            }
        }
        return TransformedText(builder.toAnnotatedString(), OffsetMapping.Identity)
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun DenseSingleLineInput(
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
) {
    val bringIntoViewRequester = remember { BringIntoViewRequester() }
    val scope = rememberCoroutineScope()
    BasicTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier
            .bringIntoViewRequester(bringIntoViewRequester)
            .onFocusChanged { focusState ->
                if (focusState.isFocused) {
                    scope.launchImeBringIntoViewGuard(bringIntoViewRequester)
                }
            }
            .background(InputWellSurface, RoundedCornerShape(Dimens.radiusCard))
            .border(Dimens.hairline, MaterialTheme.colorScheme.outline, RoundedCornerShape(Dimens.radiusCard))
            .padding(horizontal = Dimens.spaceM, vertical = Dimens.spaceM),
        textStyle = MaterialTheme.typography.bodySmall.copy(color = MaterialTheme.colorScheme.onSurface),
        cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
        singleLine = true,
        decorationBox = { innerTextField ->
            Box {
                if (value.isBlank()) {
                    Text(placeholder, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                innerTextField()
            }
        },
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun WrapRow(
    modifier: Modifier = Modifier,
    horizontal: androidx.compose.ui.unit.Dp = Dimens.spaceM,
    vertical: androidx.compose.ui.unit.Dp = Dimens.spaceM,
    content: @Composable () -> Unit,
) {
    FlowRow(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(horizontal),
        verticalArrangement = Arrangement.spacedBy(vertical),
    ) {
        content()
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun ImeAwareOutlinedTextField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    label: String? = null,
    minLines: Int = 1,
    maxLines: Int = Int.MAX_VALUE,
    singleLine: Boolean = false,
    enabled: Boolean = true,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
) {
    val bringIntoViewRequester = remember { BringIntoViewRequester() }
    val scope = rememberCoroutineScope()
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = label?.let { { Text(it) } },
        modifier = modifier
            .bringIntoViewRequester(bringIntoViewRequester)
            .onFocusChanged { focusState ->
                if (focusState.isFocused) {
                    scope.launchImeBringIntoViewGuard(bringIntoViewRequester)
                }
            },
        minLines = minLines,
        maxLines = maxLines,
        singleLine = singleLine,
        enabled = enabled,
        keyboardOptions = keyboardOptions,
        shape = RoundedCornerShape(Dimens.radiusCard),
    )
}

@Composable
private fun MetaPanel(
    state: InkuUiState,
    catalogIdOverride: String? = null,
    canvasAspectOverride: String? = null,
) {
    val catalogName = ColorCatalogs.get(catalogIdOverride ?: state.selectedCatalogId).name
    val canvasAspect = canvasLabelFor(canvasAspectOverride ?: state.selectedCanvasAspect)
    Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(Dimens.radiusCard), modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(Dimens.spaceL), verticalArrangement = Arrangement.spacedBy(Dimens.spaceXs)) {
            Text("LLM · ${selectedModelLabel(state)} · 指示文生成/Stage1/2共通", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("Color · $catalogName   Canvas · $canvasAspect", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            state.message?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

@Composable
private fun MiniPill(text: String, selected: Boolean = false, onClick: (() -> Unit)? = null, modifier: Modifier = Modifier) {
    // The pill is the app's densest control and it draws at about 26dp tall.
    // `minimumInteractiveComponentSize` keeps that drawing and gives the touch
    // the 48dp Android asks for; a pill with no `onClick` is a label and gets
    // neither, since reserving a touch slot for something untouchable only
    // spreads the row out.
    val base = modifier
        .then(if (onClick != null) Modifier.minimumInteractiveComponentSize() else Modifier)
        .background(
            if (selected) MaterialTheme.colorScheme.primary else MiniPillSurface,
            RoundedCornerShape(100),
        )
    Text(
        text,
        modifier = (onClick?.let { base.clickable(onClick = it) } ?: base).padding(horizontal = Dimens.spaceM, vertical = Dimens.spaceXs),
        style = MaterialTheme.typography.labelSmall,
        color = if (selected) InkOnPrimary else MaterialTheme.colorScheme.onSurface,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
    )
}

private fun BoxScope.presentationCaptionPlacement(screenWidth: Dp): Modifier =
    Modifier.align(Alignment.BottomCenter)
        .width(screenWidth * 0.92f)
        .padding(bottom = Dimens.presentationCaptionBottomInset)

@Composable
private fun PresentationCaption(text: String, rotation: DeviceRotation, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(Dimens.radiusCard),
        color = PresentationCaptionScrim,
        tonalElevation = 0.dp,
    ) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = Dimens.spaceL, vertical = Dimens.spaceL),
            color = PresentationCaptionInk,
            style = MaterialTheme.typography.bodyMedium,
            textAlign = TextAlign.Center,
            maxLines = 3,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun PresentationControls(
    counter: String,
    // The magnification reads here, where the magnifying is done. It used to be
    // three pills over the small canvas on the compose screen, which was the one
    // place zoom was not wanted.
    zoomPercent: Int,
    onResetZoom: () -> Unit,
    starred: Boolean,
    canGoOlder: Boolean,
    canGoLatest: Boolean,
    canGoNewer: Boolean,
    canToggleStar: Boolean,
    captionEnabled: Boolean,
    captionVisible: Boolean,
    onGoOlder: () -> Unit,
    onGoLatest: () -> Unit,
    onGoNewer: () -> Unit,
    onToggleStar: () -> Unit,
    onToggleCaption: () -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(100),
        color = PresentationControlsSurface,
        border = BorderStroke(Dimens.hairline, PresentationControlOutline),
        tonalElevation = 0.dp,
        shadowElevation = Dimens.spaceM,
    ) {
        Row(
            modifier = Modifier.padding(Dimens.spaceM),
            horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            PresentationControlButton("‹", enabled = canGoOlder, onClick = onGoOlder)
            PresentationControlButton("最新", enabled = canGoLatest, wide = true, onClick = onGoLatest)
            PresentationControlButton("›", enabled = canGoNewer, onClick = onGoNewer)
            Text(
                counter,
                modifier = Modifier.widthIn(min = Dimens.presentationControlMinWidth).padding(horizontal = Dimens.spaceXs),
                color = PresentationControlLabelMuted,
                style = MaterialTheme.typography.labelSmall,
                textAlign = TextAlign.Center,
                maxLines = 1,
            )
            PresentationControlButton(
                "${zoomPercent}%",
                wide = true,
                enabled = zoomPercent != (CANVAS_FIT_ZOOM * 100).toInt(),
                onClick = onResetZoom,
            )
            PresentationControlButton("★", selected = starred, enabled = canToggleStar, onClick = onToggleStar)
            PresentationControlButton("▭", selected = captionVisible, enabled = captionEnabled, onClick = onToggleCaption)
            PresentationControlButton("×", onClick = onClose)
        }
    }
}

@Composable
private fun PresentationControlButton(
    text: String,
    enabled: Boolean = true,
    selected: Boolean = false,
    wide: Boolean = false,
    onClick: () -> Unit,
) {
    val shape = if (wide) RoundedCornerShape(100) else RoundedCornerShape(100)
    val background = when {
        selected -> PresentationControlFillSelected
        else -> PresentationControlFillIdle
    }
    val border = when {
        selected && text == "★" -> PresentationStarOutline
        else -> PresentationControlOutline
    }
    Box(
        modifier = Modifier
            .minimumInteractiveComponentSize()
            .then(if (wide) Modifier.widthIn(min = Dimens.buttonHeightLarge) else Modifier.size(Dimens.controlSizeSmall))
            .height(Dimens.controlSizeSmall)
            .background(background, shape)
            .border(Dimens.hairline, border, shape)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = if (wide) Dimens.spaceL else 0.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text,
            color = when {
                !enabled -> PresentationControlLabelDisabled
                selected && text == "★" -> PresentationStarInk
                else -> PresentationControlLabel
            },
            style = if (wide) MaterialTheme.typography.labelSmall else MaterialTheme.typography.titleMedium,
            textAlign = TextAlign.Center,
            maxLines = 1,
        )
    }
}

@Composable
private fun ChipButton(text: String, selected: Boolean = false, modifier: Modifier = Modifier, onClick: () -> Unit) {
    // The modifier goes on the button itself. A `testTag` on a Box around one of
    // these is not in the merged semantics tree at all -- the button merges its
    // descendants and the bare wrapper is dropped, so the tag can never be found.
    if (selected) {
        Button(
            onClick = onClick,
            modifier = modifier,
            shape = RoundedCornerShape(100),
            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary, contentColor = InkOnSecondary),
        ) { Text(text, maxLines = 1) }
    } else {
        OutlinedButton(
            onClick = onClick,
            modifier = modifier,
            shape = RoundedCornerShape(100),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.onSurfaceVariant),
        ) { Text(text, maxLines = 1) }
    }
}

@Composable
private fun NavButton(mark: String, label: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier
            .fillMaxHeight()
            .clickable(onClick = onClick),
        color = Color.Transparent,
    ) {
        Column(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Box(
                modifier = Modifier
                    .width(Dimens.navButtonWidth)
                    .height(Dimens.controlSizeSmall)
                    .background(
                        if (selected) SelectionRing else Color.Transparent,
                        RoundedCornerShape(Dimens.radiusCard),
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    mark,
                    style = MaterialTheme.typography.titleMedium,
                    color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                )
            }
            Text(
                label,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                color = if (selected) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun DrawingActionButton(
    idleText: String,
    runningText: String,
    state: InkuUiState,
    onClick: () -> Unit,
    onStop: () -> Unit,
    tonal: Boolean = false,
    modifier: Modifier = Modifier,
) {
    if (state.isDrawing) {
        Row(modifier = modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
            Surface(
                modifier = Modifier.weight(1f).height(Dimens.buttonHeightLarge),
                shape = RoundedCornerShape(Dimens.radiusCard),
                color = if (tonal) MaterialTheme.colorScheme.surfaceVariant else DrawingActionSurface,
                tonalElevation = Dimens.hairline,
            ) {
                Box(modifier = Modifier.fillMaxSize()) {
                    LinearProgressIndicator(
                        modifier = Modifier
                            .align(Alignment.BottomStart)
                            .fillMaxWidth()
                            .height(Dimens.spaceXs),
                        color = MaterialTheme.colorScheme.secondary,
                        trackColor = ProgressTrack,
                    )
                    Row(
                        modifier = Modifier.fillMaxSize().padding(horizontal = Dimens.spaceL),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM),
                    ) {
                        Text(runningText, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.weight(1f))
                        Text(
                            state.message ?: "LLM working",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
            SecondaryActionButton(text = "停止", onClick = onStop, modifier = Modifier.width(Dimens.chipWidth))
        }
    } else if (tonal) {
        SecondaryActionButton(text = idleText, onClick = onClick, modifier = modifier)
    } else {
        PrimaryActionButton(text = idleText, onClick = onClick, modifier = modifier)
    }
}

@Composable
private fun PrimaryActionButton(text: String, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().height(Dimens.buttonHeightLarge),
        shape = RoundedCornerShape(Dimens.radiusPill),
        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary, contentColor = InkOnPrimary),
    ) { Text(text, maxLines = 1) }
}

@Composable
private fun SecondaryActionButton(text: String, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().height(Dimens.buttonHeightLarge),
        shape = RoundedCornerShape(Dimens.radiusPill),
    ) { Text(text, maxLines = 1) }
}

@Composable
private fun PrimarySmallButton(text: String, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.height(Dimens.buttonHeightSmall),
        shape = RoundedCornerShape(Dimens.radiusCard),
        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary, contentColor = InkOnPrimary),
    ) { Text(text, maxLines = 1) }
}

@Composable
private fun SecondarySmallButton(text: String, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.height(Dimens.buttonHeightSmall),
        shape = RoundedCornerShape(Dimens.radiusCard),
    ) { Text(text, maxLines = 1) }
}

private fun Modifier.historySwipeNavigation(
    enabled: Boolean,
    gestureKey: Any?,
    deviceRotation: DeviceRotation,
    onSwipeRight: () -> Unit,
    onSwipeLeft: () -> Unit,
): Modifier {
    if (!enabled) return this
    return pointerInput(gestureKey, enabled) {
        awaitPointerEventScope {
            while (true) {
                var pressed = emptyList<PointerInputChange>()
                while (pressed.size != 1) {
                    val downEvent = awaitPointerEvent(PointerEventPass.Initial)
                    pressed = downEvent.changes.filter { it.pressed }
                    if (pressed.size > 1) {
                        while (true) {
                            val event = awaitPointerEvent(PointerEventPass.Initial)
                            if (event.changes.none { it.pressed }) break
                        }
                        pressed = emptyList()
                    }
                }

                val pointerId = pressed.first().id
                var total = Offset.Zero
                var triggered = false
                var released = false

                while (!triggered && !released) {
                    val event = awaitPointerEvent(PointerEventPass.Initial)
                    val active = event.changes.filter { it.pressed }
                    if (active.isEmpty()) {
                        released = true
                        break
                    }
                    if (active.size != 1) {
                        break
                    }

                    val change = active.firstOrNull { it.id == pointerId } ?: break
                    total += (change.position - change.previousPosition).asDeviceRelativeOffset(deviceRotation)

                    val horizontal = abs(total.x) >= HISTORY_SWIPE_MIN_DISTANCE_PX &&
                        abs(total.x) >= abs(total.y) * HISTORY_SWIPE_AXIS_LOCK
                    val vertical = abs(total.y) >= HISTORY_SWIPE_MIN_DISTANCE_PX &&
                        abs(total.y) > abs(total.x)

                    if (vertical) {
                        break
                    }
                    if (horizontal) {
                        if (total.x > 0f) onSwipeRight() else onSwipeLeft()
                        change.consume()
                        triggered = true
                    }
                }

                if (!released) {
                    do {
                        val event = awaitPointerEvent(PointerEventPass.Initial)
                        if (triggered) {
                            event.changes.forEach { change ->
                                if (change.pressed) change.consume()
                            }
                        }
                    } while (event.changes.any { it.pressed })
                }
            }
        }
    }
}

private fun Offset.asDeviceRelativeOffset(rotation: DeviceRotation): Offset {
    return when (rotation) {
        DeviceRotation.Portrait -> this
        DeviceRotation.LandscapeLeft -> Offset(y, -x)
        DeviceRotation.ReversePortrait -> Offset(-x, -y)
        DeviceRotation.LandscapeRight -> Offset(-y, x)
    }
}

private fun presentationArtworkRotationDegrees(aspectRatio: Float, deviceRotation: DeviceRotation, presentation: Boolean): Int {
    if (!presentation) return 0
    val screenIsPortrait = true
    val artworkIsLandscape = aspectRatio > 1f
    val mustSwapAxes = artworkIsLandscape == screenIsPortrait
    return if (mustSwapAxes) {
        when (deviceRotation) {
            DeviceRotation.ReversePortrait,
            DeviceRotation.LandscapeRight -> 270
            else -> 90
        }
    } else {
        when (deviceRotation) {
            DeviceRotation.ReversePortrait -> 180
            else -> 0
        }
    }
}

private fun Int.floorMod360(): Int = ((this % 360) + 360) % 360

private fun Int.swapsAxes(): Boolean = floorMod360() == 90 || floorMod360() == 270

@Composable
private fun ArtworkPreview(
    item: HistoryItemEntity,
    modifier: Modifier = Modifier,
    presentationMode: Boolean = false,
    presentationBackground: Color = Color.White,
    rotationDegrees: Int = 0,
) {
    var pixelSize by remember { mutableStateOf(IntSize.Zero) }
    val bitmap by produceState<ImageBitmap?>(initialValue = null, item.id, item.renderHash, pixelSize, rotationDegrees) {
        value = ArtworkBitmapCache.get(item, pixelSize, rotationDegrees)
    }
    Surface(color = ServerCanvasBoxColor, shape = RoundedCornerShape(0.dp), modifier = modifier) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .onSizeChanged { pixelSize = it },
        ) {
            Canvas(modifier = Modifier.fillMaxSize()) {
                drawRect(if (presentationMode) presentationBackground else ServerCanvasBoxColor)
            }
            bitmap?.let { image ->
                Image(
                    bitmap = image,
                    contentDescription = null,
                    modifier = Modifier.fillMaxSize(),
                    contentScale = ContentScale.FillBounds,
                )
            }
        }
    }
}

private fun renderSvgIntoNativeCanvas(parsed: SVG, native: AndroidCanvas, width: Float, height: Float, rotationDegrees: Int) {
    val documentWidth = parsed.documentWidth.takeIf { it > 0f } ?: 1000f
    val documentHeight = parsed.documentHeight.takeIf { it > 0f } ?: 1000f
    val rotation = rotationDegrees.floorMod360()
    val swapsAxes = rotation.swapsAxes()
    val documentAspect = if (swapsAxes) documentHeight / documentWidth else documentWidth / documentHeight
    val boxAspect = width / height
    val drawWidth: Float
    val drawHeight: Float
    if (documentAspect >= boxAspect) {
        drawWidth = width
        drawHeight = width / documentAspect
    } else {
        drawHeight = height
        drawWidth = height * documentAspect
    }
    val left = (width - drawWidth) / 2f
    val top = (height - drawHeight) / 2f
    val contentWidth = if (swapsAxes) drawHeight else drawWidth
    val contentHeight = if (swapsAxes) drawWidth else drawHeight
    native.save()
    if (rotation == 0) {
        native.translate(left, top)
    } else {
        native.translate(width / 2f, height / 2f)
        native.rotate(rotation.toFloat())
        native.translate(-contentWidth / 2f, -contentHeight / 2f)
    }
    parsed.setDocumentWidth(contentWidth)
    parsed.setDocumentHeight(contentHeight)
    parsed.renderToCanvas(native)
    native.restore()
}

@Composable
private fun CanvasPlaceholderPreview(modifier: Modifier = Modifier) {
    Canvas(modifier = modifier.background(ServerCanvasBoxColor)) {
        drawRect(ServerCanvasPaperColor)
        val w = size.width
        val h = size.height
        val unit = minOf(w, h)
        val lineA = Path().apply {
            moveTo(w * 0.16f, h * 0.67f)
            cubicTo(w * 0.26f, h * 0.52f, w * 0.35f, h * 0.78f, w * 0.46f, h * 0.61f)
            cubicTo(w * 0.57f, h * 0.44f, w * 0.65f, h * 0.40f, w * 0.83f, h * 0.58f)
        }
        drawPath(
            path = lineA,
            color = CanvasSketchInkLight.copy(alpha = 0.72f),
            style = Stroke(width = unit * 0.007f, cap = StrokeCap.Round),
        )
        val lineB = Path().apply {
            moveTo(w * 0.17f, h * 0.38f)
            cubicTo(w * 0.26f, h * 0.32f, w * 0.33f, h * 0.42f, w * 0.41f, h * 0.37f)
            cubicTo(w * 0.49f, h * 0.32f, w * 0.56f, h * 0.22f, w * 0.66f, h * 0.28f)
            cubicTo(w * 0.73f, h * 0.32f, w * 0.78f, h * 0.39f, w * 0.85f, h * 0.36f)
        }
        drawPath(
            path = lineB,
            color = CanvasSketchInkMid.copy(alpha = 0.72f),
            style = Stroke(
                width = unit * 0.004f,
                cap = StrokeCap.Round,
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(unit * 0.018f, unit * 0.018f)),
            ),
        )
        val shapeStroke = Stroke(width = unit * 0.006f, cap = StrokeCap.Round, join = StrokeJoin.Round)
        drawCircle(
            color = CanvasSketchInkStrong.copy(alpha = 0.72f),
            radius = unit * 0.055f,
            center = Offset(w * 0.33f, h * 0.53f),
            style = shapeStroke,
        )
        drawRect(
            color = CanvasSketchInkStrong.copy(alpha = 0.72f),
            topLeft = Offset(w * 0.63f, h * 0.48f),
            size = Size(w * 0.09f, h * 0.11f),
            style = shapeStroke,
        )
        val triangle = Path().apply {
            moveTo(w * 0.49f, h * 0.40f)
            lineTo(w * 0.54f, h * 0.57f)
            lineTo(w * 0.44f, h * 0.57f)
            close()
        }
        drawPath(
            path = triangle,
            color = CanvasSketchInkStrong.copy(alpha = 0.72f),
            style = shapeStroke,
        )
    }
}

@Composable
private fun HistoryArtworkPreview(item: HistoryListItem, modifier: Modifier = Modifier) {
    ArtworkThumbnail(item.id, item.renderHash, item.thumbnailPath, modifier)
}

/** The saved thumbnail of one work, by the three values the cache needs. */
@Composable
private fun ArtworkThumbnail(
    id: String,
    renderHash: String,
    thumbnailPath: String?,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val thumbnail by produceState<ImageBitmap?>(initialValue = null, id, renderHash, thumbnailPath) {
        value = HistoryThumbnailCache.get(context, renderHash, thumbnailPath)
    }
    Surface(color = Color.White, shape = RoundedCornerShape(0.dp), modifier = modifier) {
        val image = thumbnail
        if (image != null) {
            Image(
                bitmap = image,
                contentDescription = null,
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Fit,
            )
        } else {
            Canvas(modifier = Modifier.fillMaxSize()) {
                drawRect(Color.White)
            }
        }
    }
}

private fun resolvePreviewColor(name: String, colors: Map<String, String>, fallback: Color): Color {
    val value = colors[name] ?: name.takeIf { it.startsWith("#") } ?: return fallback
    return runCatching { parseColor(value) }.getOrDefault(fallback)
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawPreviewLine(mark: JSONObject, color: Color, strokeWidth: Float, offsetX: Float, offsetY: Float, side: Float) {
    val from = mark.optJSONArray("from")
    val to = mark.optJSONArray("to")
    drawLine(
        color = color,
        start = Offset(offsetX + ratio(from?.optDouble(0, 0.1) ?: 0.1) * side, offsetY + ratio(from?.optDouble(1, 0.5) ?: 0.5) * side),
        end = Offset(offsetX + ratio(to?.optDouble(0, 0.9) ?: 0.9) * side, offsetY + ratio(to?.optDouble(1, 0.5) ?: 0.5) * side),
        strokeWidth = strokeWidth,
    )
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawPreviewSquare(mark: JSONObject, color: Color, stroke: Stroke, offsetX: Float, offsetY: Float, side: Float) {
    val position = mark.optJSONArray("position")
    val markSize = mark.optJSONArray("size")
    drawRect(
        color = color,
        topLeft = Offset(offsetX + ratio(position?.optDouble(0, 0.38) ?: 0.38) * side, offsetY + ratio(position?.optDouble(1, 0.38) ?: 0.38) * side),
        size = Size(
            ratio(markSize?.optDouble(0, 0.22) ?: 0.22) * side,
            ratio(markSize?.optDouble(1, 0.22) ?: 0.22) * side,
        ),
        style = stroke,
    )
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawPreviewCircle(mark: JSONObject, color: Color, stroke: Stroke, offsetX: Float, offsetY: Float, side: Float) {
    val center = mark.optJSONArray("center")
    drawCircle(
        color = color,
        radius = ratio(mark.optDouble("radius", 0.12)) * side,
        center = Offset(offsetX + ratio(center?.optDouble(0, 0.5) ?: 0.5) * side, offsetY + ratio(center?.optDouble(1, 0.5) ?: 0.5) * side),
        style = stroke,
    )
}

private fun expandPreview(instruction: JSONObject): List<JSONObject> {
    val arrangement = instruction.optJSONObject("arrangement") ?: return listOf(instruction)
    val count = arrangement.optInt("count", 1).coerceIn(1, 120)
    val layout = arrangement.optString("layout", "horizontal")
    val base = JSONObject(instruction.toString()).also { it.remove("arrangement") }
    return (0 until count).map { index ->
        val t = if (count == 1) 0.5 else index.toDouble() / (count - 1).toDouble()
        val x: Double
        val y: Double
        when (layout) {
            "vertical" -> {
                x = 0.5
                y = 0.12 + t * 0.76
            }
            "scatter" -> {
                x = 0.12 + hash01(index, instruction.toString()) * 0.76
                y = 0.12 + hash01(index + 1000, instruction.toString()) * 0.76
            }
            else -> {
                x = 0.12 + t * 0.76
                y = 0.5
            }
        }
        shiftPreview(base, x, y)
    }
}

private fun shiftPreview(base: JSONObject, x: Double, y: Double): JSONObject {
    val copy = JSONObject(base.toString())
    when (copy.optString("primitive", "line")) {
        "square", "triangle" -> {
            val markSize = copy.optJSONArray("size")
            val w = markSize?.optDouble(0, 0.18) ?: 0.18
            val h = markSize?.optDouble(1, 0.18) ?: 0.18
            copy.put("position", org.json.JSONArray(listOf(x - w / 2.0, y - h / 2.0)))
        }
        "line" -> {
            copy.put("from", org.json.JSONArray(listOf(x - 0.08, y - 0.18)))
            copy.put("to", org.json.JSONArray(listOf(x + 0.08, y + 0.18)))
        }
        else -> copy.put("center", org.json.JSONArray(listOf(x, y)))
    }
    return copy
}

private fun parseColor(value: String): Color {
    return Color(android.graphics.Color.parseColor(value))
}

private fun presentationBackgroundForSvg(svgText: String): Color {
    val imageBackground = firstSvgFillColor(svgText) ?: return PresentationDarkBackground
    val red = imageBackground.red
    val green = imageBackground.green
    val blue = imageBackground.blue
    val luminance = (0.2126f * red) + (0.7152f * green) + (0.0722f * blue)
    val spread = maxOf(red, green, blue) - minOf(red, green, blue)
    return when {
        luminance >= 0.92f && spread <= 0.08f -> PresentationDarkBackground
        luminance <= 0.08f && spread <= 0.08f -> PresentationLightBackground
        luminance >= 0.5f -> PresentationDarkBackground
        else -> PresentationLightBackground
    }
}

private fun firstSvgFillColor(svgText: String): Color? {
    val fill = Regex("""<rect\b[^>]*\bfill=["']([^"']+)["']""")
        .find(svgText)
        ?.groupValues
        ?.getOrNull(1)
        ?.trim()
        ?: return null
    if (fill.equals("none", ignoreCase = true) || fill.startsWith("url(", ignoreCase = true)) return null
    return runCatching { parseColor(fill) }.getOrNull()
}

private fun strokeWidthPx(weight: String): Float = when (weight) {
    "brush_thick" -> 8f
    "crayon" -> 4f
    "chalk", "brush_thin" -> 3f
    "pencil" -> 1.5f
    else -> 2f
}

private fun ratio(value: Double): Float = value.coerceIn(0.0, 1.0).toFloat()

private fun canvasAspectRatio(id: String): Float {
    return CanvasAspects.ratioFor(id).toFloat().takeIf { it > 0f } ?: 1f
}

private fun svgAspectRatio(svgText: String): Float? {
    SvgViewBoxRegex.find(svgText)?.let { match ->
        val width = match.groupValues.getOrNull(1)?.toFloatOrNull()
        val height = match.groupValues.getOrNull(2)?.toFloatOrNull()
        if (width != null && height != null && width > 0f && height > 0f) {
            return width / height
        }
    }
    val width = SvgWidthRegex.find(svgText)?.groupValues?.getOrNull(1)?.toFloatOrNull()
    val height = SvgHeightRegex.find(svgText)?.groupValues?.getOrNull(1)?.toFloatOrNull()
    return if (width != null && height != null && width > 0f && height > 0f) width / height else null
}

/**
 * The width the work asks to be drawn at, in its own units.
 *
 * The same two regexes [svgAspectRatio] reads, in the same order: the viewBox
 * is authoritative, and a bare `width=` is the fallback for anything that has
 * no viewBox.
 */
private fun svgIntrinsicWidth(svgText: String): Float? {
    SvgViewBoxRegex.find(svgText)?.groupValues?.getOrNull(1)?.toFloatOrNull()?.let { width ->
        if (width > 0f) return width
    }
    return SvgWidthRegex.find(svgText)?.groupValues?.getOrNull(1)?.toFloatOrNull()?.takeIf { it > 0f }
}

private fun hash01(index: Int, seed: String): Double {
    val digest = MessageDigest.getInstance("SHA-256").digest("$seed:$index".toByteArray())
    val raw = ((digest[0].toInt() and 0xff) shl 24) or ((digest[1].toInt() and 0xff) shl 16) or ((digest[2].toInt() and 0xff) shl 8) or (digest[3].toInt() and 0xff)
    return (raw.toLong() and 0xffffffffL).toDouble() / 0xffffffffL.toDouble()
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun ProvenanceTooltipTarget(
    tooltipText: String,
    contentLabel: String,
    onContentClick: () -> Unit = {},
) {
    val state = rememberTooltipState()
    TooltipBox(
        positionProvider = TooltipDefaults.rememberPlainTooltipPositionProvider(),
        tooltip = {
            PlainTooltip {
                Text(tooltipText)
            }
        },
        state = state,
    ) {
        MiniPill(text = contentLabel, onClick = onContentClick)
    }
}

@Composable
internal fun UiModeContainer(
    uiMode: String,
    modifier: Modifier = Modifier,
    fullContent: @Composable () -> Unit = { Text("フルモード表示") },
    simpleContent: @Composable () -> Unit = { Text("シンプルモード表示") },
) {
    Box(modifier = modifier) {
        if (uiMode == "simple") {
            simpleContent()
        } else {
            fullContent()
        }
    }
}

@Composable
internal fun MascotWidget(
    mascotKind: String,
    modifier: Modifier = Modifier,
) {
    Box(modifier = modifier.padding(Dimens.spaceXs)) {
        if (mascotKind == "yuragi") {
            YuragiMascotView()
        } else {
            IncuMascotView()
        }
    }
}

@Composable
internal fun IncuMascotView(modifier: Modifier = Modifier) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val isAnimated = remember {
        try {
            android.provider.Settings.Global.getFloat(
                context.contentResolver,
                android.provider.Settings.Global.ANIMATOR_DURATION_SCALE,
                1.0f
            ) != 0.0f
        } catch (_: Throwable) {
            true
        }
    }

    val transition = rememberInfiniteTransition(label = "incu_anim")
    val timeMs by if (isAnimated) {
        transition.animateFloat(
            initialValue = 0f,
            targetValue = 420000f, // 420s LCM of periods
            animationSpec = infiniteRepeatable(
                animation = tween(durationMillis = 420000, easing = LinearEasing)
            ),
            label = "time_ms"
        )
    } else {
        remember { mutableStateOf(0f) }
    }

    Box(
        modifier = modifier
            .testTag("mascot_incu")
            .size(Dimens.controlSizeSmall)
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(Dimens.radiusCard)),
        contentAlignment = Alignment.Center
    ) {
        Canvas(modifier = Modifier.size(Dimens.controlSizeSmall)) {
            val scaleFactor = size.width / 92f
            val timeSec = timeMs / 1000.0

            val spinAngle = if (isAnimated) ((timeSec % MascotArt.INCU_SPIN_PERIOD_SEC) / MascotArt.INCU_SPIN_PERIOD_SEC * 360.0).toFloat() else 0f

            withTransform({
                scale(scaleFactor, scaleFactor, pivot = Offset.Zero)
                rotate(spinAngle, pivot = Offset(46f, 46f))
            }) {
                for (cell in MascotArt.INCU_GRID) {
                    if (cell.face == MascotArt.IncuFace.NONE) continue

                    val hexColor = when (cell.face) {
                        MascotArt.IncuFace.TOP -> {
                            if (cell.isIncubator) {
                                val phase = ((timeSec % MascotArt.INCU_INCUBATE_TOP_PERIOD_SEC) / MascotArt.INCU_INCUBATE_TOP_PERIOD_SEC)
                                if (isAnimated && phase >= 0.5) MascotArt.COLOR_INCUBATE_TOP else MascotArt.COLOR_TOP
                            } else MascotArt.COLOR_TOP
                        }
                        MascotArt.IncuFace.LEFT -> {
                            if (cell.isIncubator) {
                                val phase = ((timeSec % MascotArt.INCU_INCUBATE_LEFT_PERIOD_SEC) / MascotArt.INCU_INCUBATE_LEFT_PERIOD_SEC)
                                if (isAnimated && phase >= 0.5) MascotArt.COLOR_INCUBATE_LEFT else MascotArt.COLOR_LEFT
                            } else MascotArt.COLOR_LEFT
                        }
                        MascotArt.IncuFace.RIGHT -> {
                            if (cell.isIncubator) {
                                val phase = ((timeSec % MascotArt.INCU_INCUBATE_RIGHT_PERIOD_SEC) / MascotArt.INCU_INCUBATE_RIGHT_PERIOD_SEC)
                                if (isAnimated && phase >= 0.5) MascotArt.COLOR_INCUBATE_RIGHT else MascotArt.COLOR_RIGHT
                            } else MascotArt.COLOR_RIGHT
                        }
                        else -> MascotArt.COLOR_TOP
                    }
                    val color = Color(android.graphics.Color.parseColor(hexColor))

                    val (cellScale, cellAngle, cornerRadius) = if (isAnimated) {
                        val rawT = (timeSec - cell.delaySeconds) % MascotArt.INCU_BREATHE_PERIOD_SEC
                        val t = if (rawT < 0) rawT + MascotArt.INCU_BREATHE_PERIOD_SEC else rawT
                        val normT = t / MascotArt.INCU_BREATHE_PERIOD_SEC
                        when {
                            normT < 0.10 -> Triple(1.0f, 0.0f, 0.0f)
                            normT < 0.40 -> {
                                val p = ((normT - 0.10) / 0.30).toFloat()
                                Triple(1.0f - p * 0.67f, p * 180f, p * 8.0f)
                            }
                            normT < 0.60 -> Triple(0.33f, 180.0f, 8.0f)
                            normT < 0.90 -> {
                                val p = ((normT - 0.60) / 0.30).toFloat()
                                Triple(0.33f + p * 0.67f, 180f + p * 180f, 8.0f * (1.0f - p))
                            }
                            else -> Triple(1.0f, 360.0f, 0.0f)
                        }
                    } else Triple(1.0f, 0.0f, 0.0f)

                    val col = cell.x + 2
                    val row = cell.y + 2
                    val baseLeft = col * 19.0f
                    val baseTop = row * 19.0f
                    val cellCenterX = baseLeft + 8.0f
                    val cellCenterY = baseTop + 8.0f

                    withTransform({
                        rotate(cellAngle, pivot = Offset(46f, 46f))
                        scale(cellScale, cellScale, pivot = Offset(cellCenterX, cellCenterY))
                    }) {
                        if (cornerRadius > 0f) {
                            drawRoundRect(
                                color = color,
                                topLeft = Offset(baseLeft, baseTop),
                                size = Size(16.0f, 16.0f),
                                cornerRadius = CornerRadius(cornerRadius, cornerRadius)
                            )
                        } else {
                            drawRect(
                                color = color,
                                topLeft = Offset(baseLeft, baseTop),
                                size = Size(16.0f, 16.0f)
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
internal fun YuragiMascotView(modifier: Modifier = Modifier) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val isAnimated = remember {
        try {
            android.provider.Settings.Global.getFloat(
                context.contentResolver,
                android.provider.Settings.Global.ANIMATOR_DURATION_SCALE,
                1.0f
            ) != 0.0f
        } catch (_: Throwable) {
            true
        }
    }

    val transition = rememberInfiniteTransition(label = "yuragi_anim")
    val timeMs by if (isAnimated) {
        transition.animateFloat(
            initialValue = 0f,
            targetValue = 370440f, // LCM of periods
            animationSpec = infiniteRepeatable(
                animation = tween(durationMillis = 370440, easing = LinearEasing)
            ),
            label = "time_ms"
        )
    } else {
        remember { mutableStateOf(0f) }
    }

    Box(
        modifier = modifier
            .testTag("mascot_yuragi")
            .size(Dimens.controlSizeSmall)
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(Dimens.radiusCard)),
        contentAlignment = Alignment.Center
    ) {
        Canvas(modifier = Modifier.size(Dimens.controlSizeSmall)) {
            val scaleFactor = size.width / 92f
            val timeSec = timeMs / 1000.0

            val (stepTx, stepRotate) = if (isAnimated) {
                val stepPhase = (timeSec % MascotArt.YURAGI_CRAB_STEP_PERIOD_SEC) / MascotArt.YURAGI_CRAB_STEP_PERIOD_SEC
                val p = kotlin.math.sin(2.0 * kotlin.math.PI * stepPhase).toFloat()
                Pair(p * 4.0f, p * 3.0f)
            } else Pair(0f, 0f)

            withTransform({
                scale(scaleFactor, scaleFactor, pivot = Offset.Zero)
            }) {
                // Render Bubbles first (background)
                if (isAnimated) {
                    for (b in MascotArt.YURAGI_BUBBLES) {
                        val rawT = (timeSec - b.delaySeconds) % MascotArt.YURAGI_BUBBLE_PERIOD_SEC
                        val t = if (rawT < 0) rawT + MascotArt.YURAGI_BUBBLE_PERIOD_SEC else rawT
                        val phase = t / MascotArt.YURAGI_BUBBLE_PERIOD_SEC
                        if (phase >= 0.85) {
                            val relP = ((phase - 0.85) / 0.15).toFloat()
                            val (bTx, bTy, bScale, bAlpha, bRadius) = when {
                                relP < 0.133f -> {
                                    val subP = relP / 0.133f
                                    Tuple5(b.txPx * 0.2f * subP, -5.0f * subP, 0.2f + 0.2f * subP, 0.9f * subP, 3.2f)
                                }
                                relP < 0.467f -> {
                                    val subP = (relP - 0.133f) / 0.334f
                                    Tuple5(
                                        b.txPx * (0.2f + 0.5f * subP),
                                        -5.0f - 25.0f * subP,
                                        0.4f + (b.scale - 0.4f) * subP,
                                        0.9f - 0.3f * subP,
                                        3.2f + 4.8f * subP
                                    )
                                }
                                else -> {
                                    val subP = (relP - 0.467f) / 0.533f
                                    Tuple5(
                                        b.txPx * (0.7f + 0.3f * subP),
                                        -30.0f - 60.0f * subP,
                                        b.scale * (1.0f + 0.5f * subP),
                                        0.6f * (1.0f - subP),
                                        8.0f
                                    )
                                }
                            }

                            val bubbleBaseLeft = 38.0f + bTx
                            val bubbleBaseTop = 34.0f + bTy
                            val color = Color(android.graphics.Color.parseColor(MascotArt.COLOR_BUBBLE)).copy(alpha = bAlpha)

                            withTransform({
                                scale(bScale, bScale, pivot = Offset(bubbleBaseLeft + 8f, bubbleBaseTop + 8f))
                            }) {
                                drawRoundRect(
                                    color = color,
                                    topLeft = Offset(bubbleBaseLeft, bubbleBaseTop),
                                    size = Size(16f, 16f),
                                    cornerRadius = CornerRadius(bRadius, bRadius)
                                )
                            }
                        }
                    }
                }

                // Render Crab Body Grid
                withTransform({
                    translate(stepTx, 0f)
                    rotate(stepRotate, pivot = Offset(46f, 46f))
                }) {
                    for (cell in MascotArt.YURAGI_GRID) {
                        if (cell.type == MascotArt.YuragiCellType.NONE) continue

                        val col = cell.x + 2
                        val row = cell.y + 2
                        val baseLeft = col * 19.0f
                        val baseTop = row * 19.0f

                        val hexColor = when (cell.type) {
                            MascotArt.YuragiCellType.RED -> {
                                if (cell.isIncubator) {
                                    val phase = (timeSec % MascotArt.YURAGI_INCUBATE_PERIOD_SEC) / MascotArt.YURAGI_INCUBATE_PERIOD_SEC
                                    if (isAnimated && phase >= 0.5) MascotArt.COLOR_INCUBATE_INK else MascotArt.COLOR_RED
                                } else MascotArt.COLOR_RED
                            }
                            MascotArt.YuragiCellType.EYE -> {
                                val isBlinking = if (cell.isEyeLeft) MascotArt.isLeftEyeBlinking(timeSec) else MascotArt.isRightEyeBlinking(timeSec)
                                if (isAnimated && isBlinking) MascotArt.COLOR_EYE_BLACK else MascotArt.COLOR_EYE_WHITE
                            }
                            else -> MascotArt.COLOR_RED
                        }
                        val color = Color(android.graphics.Color.parseColor(hexColor))

                        val legTy = if (isAnimated && cell.isLeg) {
                            val tLeg = (timeSec - cell.legDelaySeconds) % MascotArt.YURAGI_LEG_TREMBLE_PERIOD_SEC
                            val normT = if (tLeg < 0) tLeg + MascotArt.YURAGI_LEG_TREMBLE_PERIOD_SEC else tLeg
                            val p = kotlin.math.sin(2.0 * kotlin.math.PI * normT / MascotArt.YURAGI_LEG_TREMBLE_PERIOD_SEC).toFloat()
                            -kotlin.math.abs(p) * 3.0f
                        } else 0f

                        // Claw animation
                        var clawScale = 1.0f
                        var clawRotate = 0.0f
                        var clawTy = 0.0f
                        var clawRadius = 0.0f
                        var pivotX = baseLeft + 8f
                        var pivotY = baseTop + 8f

                        if (isAnimated && cell.isClawLeft) {
                            pivotX = baseLeft + 16f
                            pivotY = baseTop + 16f
                            val phase = (timeSec % MascotArt.YURAGI_CLAW_LEFT_PERIOD_SEC) / MascotArt.YURAGI_CLAW_LEFT_PERIOD_SEC
                            if (phase in 0.85..0.95) {
                                val subP = ((phase - 0.85) / 0.10).toFloat()
                                clawScale = 1.3f
                                clawTy = -4.0f
                                clawRadius = 8.0f
                                clawRotate = when {
                                    subP < 0.2f -> -45.0f * (subP / 0.2f)
                                    subP < 0.4f -> -45.0f + 60.0f * ((subP - 0.2f) / 0.2f)
                                    subP < 0.6f -> 15.0f - 60.0f * ((subP - 0.4f) / 0.2f)
                                    subP < 0.8f -> -45.0f + 60.0f * ((subP - 0.6f) / 0.2f)
                                    else -> 15.0f - 15.0f * ((subP - 0.8f) / 0.2f)
                                }
                            }
                        } else if (isAnimated && cell.isClawRight) {
                            pivotX = baseLeft
                            pivotY = baseTop + 16f
                            val phase = (timeSec % MascotArt.YURAGI_CLAW_RIGHT_PERIOD_SEC) / MascotArt.YURAGI_CLAW_RIGHT_PERIOD_SEC
                            if (phase in 0.80..0.92) {
                                val subP = ((phase - 0.80) / 0.12).toFloat()
                                clawScale = 1.3f
                                clawTy = -4.0f
                                clawRadius = 8.0f
                                clawRotate = when {
                                    subP < 0.166f -> 45.0f * (subP / 0.166f)
                                    subP < 0.333f -> 45.0f - 60.0f * ((subP - 0.166f) / 0.167f)
                                    subP < 0.500f -> -15.0f + 60.0f * ((subP - 0.333f) / 0.167f)
                                    subP < 0.666f -> 45.0f - 60.0f * ((subP - 0.500f) / 0.166f)
                                    subP < 0.833f -> -15.0f + 60.0f * ((subP - 0.666f) / 0.167f)
                                    else -> 45.0f - 45.0f * ((subP - 0.833f) / 0.167f)
                                }
                            }
                        }

                        withTransform({
                            translate(0f, legTy + clawTy)
                            if (clawRotate != 0f || clawScale != 1.0f) {
                                rotate(clawRotate, pivot = Offset(pivotX, pivotY))
                                scale(clawScale, clawScale, pivot = Offset(pivotX, pivotY))
                            }
                        }) {
                            if (clawRadius > 0f) {
                                drawRoundRect(
                                    color = color,
                                    topLeft = Offset(baseLeft, baseTop),
                                    size = Size(16.0f, 16.0f),
                                    cornerRadius = CornerRadius(clawRadius, clawRadius)
                                )
                            } else {
                                drawRect(
                                    color = color,
                                    topLeft = Offset(baseLeft, baseTop),
                                    size = Size(16.0f, 16.0f)
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

private data class Tuple5<A, B, C, D, E>(val a: A, val b: B, val c: C, val d: D, val e: E)

