package app.inku.mobile.ui

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
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
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
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
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
import androidx.core.content.FileProvider
import app.inku.mobile.BuildConfig
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.HistoryListItem
import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.model.CompatibilityConstants
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

private val InkuColors = darkColorScheme(
    background = Color(0xFF11100F),
    surface = Color(0xFF181715),
    surfaceVariant = Color(0xFF24211E),
    primary = Color(0xFF7FA6D8),
    secondary = Color(0xFFEAD7A3),
    outline = Color(0xFF514A43),
    onBackground = Color(0xFFEDE7DE),
    onSurface = Color(0xFFEDE7DE),
    onSurfaceVariant = Color(0xFFCFC6BA),
)

private val ServerCanvasAreaColor = Color(0xFF20201F)
private val ServerCanvasBoxColor = Color(0xFF242321)
private val ServerCanvasPaperColor = Color(0xFFF5F1E9)
private val PresentationDarkBackground = Color(0xFF11100F)
private val PresentationLightBackground = Color(0xFFF8F8F6)
private const val HISTORY_SWIPE_MIN_DISTANCE_PX = 96f
private const val HISTORY_SWIPE_AXIS_LOCK = 1.6f
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

    suspend fun get(context: Context, item: HistoryListItem): ImageBitmap? {
        val key = "${item.renderHash}:$THUMBNAIL_PX"
        synchronized(cache) {
            cache.get(key)?.let { return it }
        }
        return withContext(Dispatchers.Default) {
            val rendered = item.thumbnailPath
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
    Color(0xFFEAD7A3),
    Color(0xFF9CC6E8),
    Color(0xFFB8D58A),
    Color(0xFFE08A7A),
    Color(0xFFD2B7F0),
    Color(0xFF8FD8C1),
    Color(0xFFF2B66D),
    Color(0xFFAEB7D8),
    Color(0xFFE7A9C1),
)

@Composable
fun InkuApp() {
    val viewModel: InkuViewModel = androidx.lifecycle.viewmodel.compose.viewModel()
    val state by viewModel.state.collectAsState()
    val deviceRotation = rememberDeviceRotation(enabled = state.canvasPresentationMode)

    MaterialTheme(colorScheme = InkuColors) {
        Scaffold(
            bottomBar = {
                if (!state.canvasPresentationMode) {
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
                        AppTab.Demo -> DemoPanel(state, viewModel, modifier = Modifier.fillMaxSize().padding(12.dp))
                        AppTab.Settings -> SettingsPanel(state, viewModel, modifier = Modifier.fillMaxSize().padding(12.dp))
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
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
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
                .padding(12.dp),
            shape = RoundedCornerShape(6.dp),
            color = MaterialTheme.colorScheme.surface,
            tonalElevation = 6.dp,
        ) {
            Column(
                modifier = Modifier.fillMaxSize().padding(10.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
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
        horizontalArrangement = Arrangement.spacedBy(6.dp),
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
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
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
            WrapRow(horizontal = 6.dp, vertical = 6.dp) {
                prioritizedDetectedWords.take(12).forEach { token ->
                    DdlVocabularyPill(token = token, selected = token.word == selectedWord?.word, onClick = { onSelectDetected(token.word) })
                }
            }
        }
        if (open) {
            Surface(
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(6.dp),
                modifier = Modifier.fillMaxWidth().heightIn(max = 248.dp),
            ) {
                Column(
                    modifier = Modifier.padding(8.dp).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    DenseSingleLineInput(
                        value = query,
                        onValueChange = onQueryChange,
                        placeholder = "検索",
                        modifier = Modifier.fillMaxWidth(),
                    )
                    prioritizedGroups.forEach { group ->
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(
                                if (selectedWord?.group?.label == group.label) "${group.label} / 代替候補" else group.label,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            WrapRow(horizontal = 6.dp, vertical = 6.dp) {
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
    val foreground = if (isLightColor(background)) Color(0xFF12110F) else Color(0xFFF8F8F6)
    Text(
        token.word,
        modifier = Modifier
            .background(background, RoundedCornerShape(3.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 5.dp, vertical = 2.dp),
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
                modifier = Modifier.fillMaxWidth().heightIn(max = 430.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
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
                modifier = Modifier.fillMaxWidth().height(560.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                ColorCatalogs.all.forEach { catalog ->
                    val active = catalog.id == state.selectedCatalogId
                    Surface(
                        modifier = Modifier.fillMaxWidth().clickable { viewModel.setCatalog(catalog.id) },
                        shape = RoundedCornerShape(8.dp),
                        color = if (active) Color(0x1AEAD7A3) else MaterialTheme.colorScheme.surface,
                    ) {
                        Row(
                            modifier = Modifier.padding(10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
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
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Box(
                            modifier = Modifier
                                .size(28.dp)
                                .background(parseColor(code), RoundedCornerShape(3.dp))
                                .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(3.dp)),
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
                modifier = Modifier.fillMaxWidth().height(460.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                CanvasAspects.all.forEach { aspect ->
                    val active = aspect.id == state.selectedCanvasAspect
                    Surface(
                        modifier = Modifier.fillMaxWidth().clickable {
                            viewModel.setCanvasAspect(aspect.id)
                            viewModel.closeTransientPanel()
                        },
                        shape = RoundedCornerShape(8.dp),
                        color = if (active) Color(0x1AEAD7A3) else MaterialTheme.colorScheme.surface,
                    ) {
                        Row(
                            modifier = Modifier.padding(10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(34.dp)
                                    .border(1.dp, MaterialTheme.colorScheme.onSurfaceVariant, RoundedCornerShape(3.dp))
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
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        SettingsSectionHeader(title.uppercase(), sub)
        CompactLabel("Provider")
        Box(modifier = Modifier.fillMaxWidth()) {
            Surface(
                modifier = Modifier.fillMaxWidth().clickable { providerMenuOpen = true },
                shape = RoundedCornerShape(8.dp),
                color = MaterialTheme.colorScheme.surface,
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(8.dp)).padding(horizontal = 12.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
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
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                models.forEach { option ->
                    Surface(
                        modifier = Modifier.fillMaxWidth().clickable { onSelectModel(option.qualifiedId) },
                        shape = RoundedCornerShape(8.dp),
                        color = if (option.qualifiedId == selectedModelId) Color(0x1AEAD7A3) else MaterialTheme.colorScheme.surface,
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 9.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Text(if (option.qualifiedId == selectedModelId) "✓" else "", modifier = Modifier.width(18.dp), color = MaterialTheme.colorScheme.secondary)
                            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
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
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("歳時記", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Medium)
            Text("語を押すと DDL 編集欄へ挿入します。", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            saijikiGroups.forEach { group ->
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("${group.label} / ${group.en}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    WrapRow(horizontal = 6.dp, vertical = 6.dp) {
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
            .border(1.dp, Color(0xFF26221E)),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 2.dp,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(80.dp)
                .padding(horizontal = 8.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            AppTab.entries.forEach { tab ->
                val label = when (tab) {
                    AppTab.Compose -> "記述"
                    AppTab.History -> "履歴"
                    AppTab.Demo -> "デモ"
                    AppTab.Settings -> "設定"
                }
                val mark = when (tab) {
                    AppTab.Compose -> "✎"
                    AppTab.History -> "◫"
                    AppTab.Demo -> "◉"
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
            .padding(4.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
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
                    .height(40.dp)
                    .clickable { viewModel.setComposeMode(tab) },
                shape = RoundedCornerShape(100),
                color = if (active) MaterialTheme.colorScheme.surface else Color.Transparent,
                tonalElevation = if (active) 2.dp else 0.dp,
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

@Composable
private fun ComposeScreen(state: InkuUiState, viewModel: InkuViewModel) {
    if (state.canvasPresentationMode) {
        CanvasHeroCard(state, viewModel, modifier = Modifier.fillMaxSize())
        return
    }
    val scrollState = rememberScrollState()
    val focusManager = LocalFocusManager.current
    val keyboardController = LocalSoftwareKeyboardController.current
    LaunchedEffect(state.isDrawing, state.selectedHistory?.id) {
        if (!state.isDrawing && state.selectedHistory != null) {
            focusManager.clearFocus(force = true)
            keyboardController?.hide()
            scrollState.animateScrollTo(0)
        }
    }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scrollState)
            .padding(horizontal = 20.dp, vertical = 4.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        ComposeModeTabs(state.composeMode, viewModel)
        if (state.composeMode == ComposeMode.Batch) {
            ConditionChips(state, viewModel)
            BatchPanel(state, viewModel)
            CanvasHeroCard(state, viewModel)
        } else {
            CanvasHeroCard(state, viewModel)
            DrawPanel(state, viewModel)
        }
        Spacer(Modifier.height(96.dp))
    }
}

@Composable
private fun CanvasHeroCard(
    state: InkuUiState,
    viewModel: InkuViewModel,
    modifier: Modifier = Modifier.fillMaxWidth(),
    showControls: Boolean = true,
    maxPreviewHeight: Dp = 330.dp,
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
    var svgMenuOpen by remember { mutableStateOf(false) }
    var svgHelpOpen by remember { mutableStateOf(false) }
    var pngMenuOpen by remember { mutableStateOf(false) }
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
        val instructionCaptionText = item?.originalInput?.trim().orEmpty()
        val canShowInstructionCaption = instructionCaptionText.isNotBlank()
        val historyIndex = item?.let { selected -> historyItems.indexOfFirst { it.id == selected.id } } ?: -1
        val historyTotal = historyItems.size
        val canGoLatest = historyIndex > 0
        val canGoNewer = historyIndex > 0
        val canGoOlder = historyIndex >= 0 && historyIndex < historyItems.lastIndex
        val historyCounter = if (historyIndex >= 0 && historyTotal > 0) "${historyIndex + 1} / $historyTotal" else ""
        Column(modifier = if (presentation) Modifier.fillMaxSize() else Modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (!presentation && showControls) {
                Box(modifier = Modifier.fillMaxWidth()) {
                    Row(
                        modifier = Modifier.align(Alignment.CenterStart),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        item?.let {
                            MiniPill(text = if (it.starred) "★" else "☆", selected = it.starred, onClick = { viewModel.toggleStar(it) })
                            MiniPill(
                                text = "F${it.renderHashShort}",
                                onClick = {
                                    clipboard.setText(AnnotatedString(it.renderHashShort))
                                    canvasMessage = "Hash copied."
                                },
                            )
                        }
                    }
                    Row(
                        modifier = Modifier.align(Alignment.Center),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        MiniPill("-", onClick = { viewModel.setCanvasZoom(state.canvasZoom - 0.25f) })
                        MiniPill("${(state.canvasZoom * 100).toInt()}%", onClick = viewModel::resetCanvasZoom)
                        MiniPill("+", onClick = { viewModel.setCanvasZoom(state.canvasZoom + 0.25f) })
                    }
                    MiniPill(
                        shortCanvasLabel(state),
                        onClick = viewModel::openCanvasSelection,
                        modifier = Modifier.align(Alignment.CenterEnd).widthIn(max = 72.dp),
                    )
                }
            }
            Surface(
                modifier = (if (presentation) Modifier.fillMaxSize() else Modifier.fillMaxWidth().height(previewHeight))
                    .border(1.dp, Color(0x1A000000)),
                color = if (presentation) presentationBackground else ServerCanvasAreaColor,
                shape = RoundedCornerShape(0.dp),
                tonalElevation = 1.dp,
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .historySwipeNavigation(
                            enabled = presentation,
                            gestureKey = item?.id,
                            deviceRotation = deviceRotation,
                            onSwipeRight = viewModel::selectNextHistory,
                            onSwipeLeft = viewModel::selectPreviousHistory,
                        )
                        .pointerInput(item?.id, state.canvasPresentationMode) {
                            detectTapGestures(
                                onDoubleTap = {
                                    if (state.canvasPresentationMode) {
                                        viewModel.resetCanvasZoom()
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
                                        enabled = !presentation && state.canvasZoom <= 1.05f,
                                        gestureKey = item.id,
                                        deviceRotation = DeviceRotation.Portrait,
                                        onSwipeRight = viewModel::selectPreviousHistory,
                                        onSwipeLeft = viewModel::selectNextHistory,
                                    )
                                    .then(
                                        if (presentation) {
                                            Modifier
                                        } else {
                                            Modifier.pointerInput(Unit) {
                                                detectTransformGestures { _, pan, zoom, _ ->
                                                    if (zoom != 1f) viewModel.scaleCanvasZoom(zoom)
                                                    if (pan != Offset.Zero) viewModel.panCanvas(pan.x, pan.y)
                                                }
                                            }
                                        },
                                    )
                                    .graphicsLayer(
                                        scaleX = if (presentation) 1f else state.canvasZoom,
                                        scaleY = if (presentation) 1f else state.canvasZoom,
                                        translationX = if (presentation) 0f else state.canvasPanX,
                                        translationY = if (presentation) 0f else state.canvasPanY,
                                    )
                            )
                        }
                    }
                    if (presentation && state.demoWaitingSeconds != null) {
                        Surface(
                            modifier = Modifier
                                .align(Alignment.BottomEnd)
                                .padding(end = 16.dp, bottom = 78.dp),
                            shape = RoundedCornerShape(100),
                            color = Color(0xCC11100F),
                            border = BorderStroke(1.dp, Color(0x55EDE7DE)),
                        ) {
                            Text(
                                "残り ${state.demoWaitingSeconds}秒",
                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
                                style = MaterialTheme.typography.labelLarge,
                                color = Color(0xFFEDE7DE),
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
                                .padding(start = 12.dp, end = 12.dp, bottom = 14.dp),
                            counter = historyCounter,
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
                            onClose = viewModel::resetCanvasZoom,
                        )
                    }
                }
            }
            if (!presentation && showControls) item?.let {
                WrapRow {
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
                    Box {
                        MiniPill(text = "SVG ▾", onClick = { svgMenuOpen = true })
                        DropdownMenu(
                            expanded = svgMenuOpen,
                            onDismissRequest = {
                                svgMenuOpen = false
                                svgHelpOpen = false
                            },
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                Text(
                                    "SVG export",
                                    modifier = Modifier.weight(1f),
                                    style = MaterialTheme.typography.labelMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                TextButton(onClick = { svgHelpOpen = !svgHelpOpen }) {
                                    Text("?")
                                }
                            }
                            if (svgHelpOpen) {
                                SvgExportHelp()
                            }
                            SvgExportOption(
                                title = "表示用SVG",
                                sub = "Web表示向けの標準SVG",
                                onClick = {
                                    svgMenuOpen = false
                                    svgHelpOpen = false
                                    canvasMessage = "SVG export preparing..."
                                    scope.launch {
                                        canvasMessage = runCatching {
                                            shareHistorySvg(context, it, "display")
                                            "SVG exported F${it.renderHashShort}"
                                        }.getOrElse { error -> error.message ?: "SVG export failed." }
                                    }
                                },
                            )
                            SvgExportOption(
                                title = "編集用SVG",
                                sub = "編集用メタデータとIDを含む",
                                onClick = {
                                    svgMenuOpen = false
                                    svgHelpOpen = false
                                    canvasMessage = "SVG export preparing..."
                                    scope.launch {
                                        canvasMessage = runCatching {
                                            shareHistorySvg(context, it, "editable")
                                            "SVG exported F${it.renderHashShort}"
                                        }.getOrElse { error -> error.message ?: "SVG export failed." }
                                    }
                                },
                            )
                            SvgExportOption(
                                title = "汎用SVG",
                                sub = "互換性重視のポータブルSVG",
                                onClick = {
                                    svgMenuOpen = false
                                    svgHelpOpen = false
                                    canvasMessage = "SVG export preparing..."
                                    scope.launch {
                                        canvasMessage = runCatching {
                                            shareHistorySvg(context, it, "compat")
                                            "SVG exported F${it.renderHashShort}"
                                        }.getOrElse { error -> error.message ?: "SVG export failed." }
                                    }
                                },
                            )
                        }
                    }
                    Box {
                        MiniPill(text = "PNG ▾", onClick = { pngMenuOpen = true })
                        DropdownMenu(
                            expanded = pngMenuOpen,
                            onDismissRequest = { pngMenuOpen = false },
                        ) {
                            state.exportTemplates.forEach { template ->
                                DropdownMenuItem(
                                    text = {
                                        Column {
                                            Text(template.name, style = MaterialTheme.typography.labelMedium)
                                            Text(
                                                exportTemplateDescription(template.description, template.heightPx),
                                                style = MaterialTheme.typography.labelSmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            )
                                        }
                                    },
                                    onClick = {
                                        pngMenuOpen = false
                                        pngExporting = true
                                        canvasMessage = "PNG export preparing..."
                                        scope.launch {
                                            canvasMessage = runCatching {
                                                shareHistoryPng(context, it, template.heightPx)
                                                "PNG exported F${it.renderHashShort}"
                                            }.getOrElse { error -> error.message ?: "PNG export failed." }
                                            pngExporting = false
                                        }
                                    },
                                )
                            }
                        }
                    }
                }
            }
        }
    }
    if (!presentation && showControls && pngExporting) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp)
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
                Modifier.fillMaxWidth().height(360.dp),
            )
            RenderTab.Json -> RenderTextView(renderJsonText(it), Modifier.fillMaxWidth().height(360.dp))
        }
    }
}

@Composable
private fun SvgExportOption(title: String, sub: String, onClick: () -> Unit) {
    DropdownMenuItem(
        text = {
            Column {
                Text(title, style = MaterialTheme.typography.labelMedium)
                Text(sub, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        },
        onClick = onClick,
    )
}

@Composable
private fun SvgExportHelp() {
    Column(
        modifier = Modifier
            .widthIn(min = 260.dp, max = 360.dp)
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        SvgExportHelpRow("表示用SVG", "Web表示", "標準表示向け")
        SvgExportHelpRow("編集用SVG", "ベクター編集", "メタデータとIDを含む")
        SvgExportHelpRow("汎用SVG", "外部共有", "互換性重視")
    }
}

@Composable
private fun SvgExportHelpRow(format: String, use: String, feature: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
        Text(format, modifier = Modifier.width(76.dp), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
        Text(use, modifier = Modifier.width(82.dp), style = MaterialTheme.typography.labelSmall)
        Text(feature, modifier = Modifier.weight(1f), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

private fun exportTemplateDescription(description: String, heightPx: Int): String {
    return description.ifBlank { "PNG / Y軸 ${heightPx}px" }
}

@Composable
private fun ConditionChips(state: InkuUiState, viewModel: InkuViewModel) {
    WrapRow {
        ChipButton("◐ ${ColorCatalogs.get(state.selectedCatalogId).name}", onClick = viewModel::openCatalogSelection)
        ChipButton("◇ モデル", onClick = viewModel::openModelSelection)
    }
}

@Composable
private fun DrawPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            CompactLabel("指示")
            Spacer(Modifier.weight(1f))
            MiniPill(
                text = "◐ ${shortCatalogLabel(state)}",
                onClick = viewModel::openCatalogSelection,
                modifier = Modifier.widthIn(max = 112.dp),
            )
            MiniPill(
                text = "◇ ${shortModelLabel(state)}",
                onClick = viewModel::openModelSelection,
                modifier = Modifier.widthIn(max = 124.dp),
            )
            MiniPill("新規作成", onClick = viewModel::clearPrompt)
        }
        DenseMultilineInput(
            value = state.prompt,
            onValueChange = viewModel::setPrompt,
            modifier = Modifier.fillMaxWidth(),
            minLines = 5,
            maxLines = 8,
        )
        DrawingActionButton(
            idleText = "▶  描画する",
            runningText = "■  描画中",
            state = state,
            onClick = viewModel::draw,
            onStop = viewModel::stopDrawing,
        )
        state.message?.takeIf { it.isNotBlank() }?.let { message ->
            Text(message, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelSmall)
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
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
}

@Composable
private fun InputSectionHeader(state: InkuUiState, viewModel: InkuViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        CompactLabel("指示")
        WrapRow {
            SecondarySmallButton(
                text = ColorCatalogs.get(state.selectedCatalogId).name,
                onClick = viewModel::openCatalogSelection,
            )
            PrimarySmallButton(
                text = "モデル",
                onClick = viewModel::openModelSelection,
            )
        }
    }
}

@Composable
private fun BatchPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    val lines = state.batchText.lines()
    val nonEmpty = lines.count { it.trim().isNotBlank() }
    Column(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            CompactLabel("バッチ")
            Spacer(Modifier.weight(1f))
            MiniPill("新規作成", onClick = viewModel::clearBatchText)
        }
        NumberedBatchTextField(
            value = state.batchText,
            onValueChange = viewModel::setBatchText,
            enabled = !state.isDrawing,
            modifier = Modifier.fillMaxWidth(),
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                "${nonEmpty}件/100件",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.weight(1f))
            MiniPill(
                text = "ランダムな色カタログ",
                selected = state.batchRandomColorCatalog,
                onClick = if (state.isDrawing) null else {
                    { viewModel.setBatchRandomColorCatalog(!state.batchRandomColorCatalog) }
                },
            )
        }
        if (!state.isDrawing) {
            if (state.batchPromptHistory.isNotEmpty()) {
                CompactLabel("バッチ指示履歴")
                WrapRow(horizontal = 6.dp, vertical = 6.dp) {
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
        lineHeight = 17.sp,
    )

    Surface(
        modifier = modifier
            .height(320.dp)
            .bringIntoViewRequester(bringIntoViewRequester),
        shape = RoundedCornerShape(4.dp),
        color = Color(0xFF191816),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .clipToBounds()
                .verticalScroll(scrollState)
                .padding(horizontal = 8.dp, vertical = 6.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            lines.forEachIndexed { index, line ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.Top,
                ) {
                    Text(
                        (index + 1).toString(),
                        style = textStyle,
                        textAlign = TextAlign.End,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.width(28.dp),
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
                            .heightIn(min = 20.dp)
                            .onFocusChanged { focusState ->
                                if (focusState.isFocused) {
                                    scope.launchImeBringIntoViewGuard(bringIntoViewRequester)
                                }
                            },
                    )
                }
            }
            if (lineCount < 6) {
                Spacer(Modifier.height(20.dp * (6 - lineCount)))
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
    Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
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
                modifier = Modifier.fillMaxWidth().height(116.dp),
            )
        }
    }
}

@Composable
private fun BatchFailureSummary(state: InkuUiState) {
    Surface(color = Color(0x22E08A7A), shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
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
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        CanvasHeroCard(
            state,
            viewModel,
            showControls = false,
            maxPreviewHeight = 250.dp,
            canvasAspectOverride = DemoCanvasAspectId,
        )

        CompactLabel("生成された指示文")
        Surface(
            color = MaterialTheme.colorScheme.surface,
            shape = RoundedCornerShape(14.dp),
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                state.demoGeneratedPrompt.ifBlank { "—" },
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                style = MaterialTheme.typography.bodyMedium,
                lineHeight = 22.sp,
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
                modifier = Modifier.fillMaxWidth().height(140.dp),
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
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
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
                .padding(start = 14.dp)
                .height(1.dp)
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
        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
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
    Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
        ImeAwareOutlinedTextField(
            value = state.historySearchQuery,
            onValueChange = viewModel::setHistorySearchQuery,
            label = "プロンプト・ハッシュ・モデルで検索",
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
            ChipButton("★ 星のみ", selected = state.historyStarredOnly, onClick = viewModel::toggleHistoryStarredFilter)
            Text("${filteredCount}/${sourceCount}件", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
            .padding(horizontal = 4.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("設定", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Medium)
        }
        SettingsListItem(mark = "◇", title = "モデル設定", sub = "OpenAI / Claude / Gemini / NVIDIA", onClick = { viewModel.setSettingsPane(SettingsPane.Models) })
        SettingsListItem(mark = "◉", title = "デモ設定", sub = "シードフレーズ", onClick = { viewModel.setSettingsPane(SettingsPane.Demo) })
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
        modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        MiniPill("‹", onClick = { viewModel.setSettingsPane(SettingsPane.Home) })
        Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
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
            .padding(horizontal = 4.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
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
        modifier = modifier.verticalScroll(rememberScrollState()).padding(horizontal = 4.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        SettingsHeader(state.settingsPane, viewModel)
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
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
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
        modifier = modifier.verticalScroll(rememberScrollState()).padding(horizontal = 4.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        SettingsHeader(state.settingsPane, viewModel)
        SettingsCard("PNG / SVG", "Web版の出力設定", "保存済み") {
            SettingCheckRow(
                checked = state.pngAlphaWhite,
                text = "PNG透過時の白背景",
                onCheckedChange = viewModel::setPngAlphaWhite,
            )
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
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
        modifier = modifier.verticalScroll(rememberScrollState()).padding(horizontal = 4.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        SettingsHeader(state.settingsPane, viewModel)
        SettingsCard("マスコット", "Web版の表示設定", "保存済み") {
            SettingCheckRow(state.showKiwi, "進行表示のKiwi", viewModel::setShowKiwi)
            SettingCheckRow(state.showCrab, "バッチ表示のCrab", viewModel::setShowCrab)
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
            .padding(horizontal = 4.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
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
            modifier = Modifier.padding(start = 12.dp).weight(1f),
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
            .padding(horizontal = 4.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        SettingsHeader(state.settingsPane, viewModel)

        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
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
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
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
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("APIキー", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
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
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
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
                    WrapRow(horizontal = 6.dp, vertical = 6.dp) {
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
                    modifier = Modifier.height(32.dp),
                    shape = RoundedCornerShape(4.dp),
                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp),
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
        color = Color(0xFF20201E),
        shape = RoundedCornerShape(100),
        border = BorderStroke(1.dp, Color(0xFF34302B)),
        modifier = Modifier.widthIn(max = 220.dp),
    ) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
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
                modifier = Modifier.fillMaxWidth().height(520.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
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
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    filtered.forEach { model ->
                        val checked = selected.contains(model.id)
                        Row(
                            modifier = Modifier.fillMaxWidth().clickable {
                                selected = if (checked) selected - model.id else selected + model.id
                            }.padding(vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
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
                .heightIn(max = 680.dp),
            shape = RoundedCornerShape(22.dp),
            color = MaterialTheme.colorScheme.surface,
            tonalElevation = 6.dp,
        ) {
            Column(
                modifier = Modifier.padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
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
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        ModelPickerActionButton(text = "全選択", onClick = { selected = assetIds }, modifier = Modifier.width(76.dp))
                        ModelPickerActionButton(text = "全解除", onClick = { selected = emptySet() }, modifier = Modifier.width(76.dp))
                    }
                }

                Column(
                    modifier = Modifier.fillMaxWidth().weight(1f, fill = false).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
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
        shape = RoundedCornerShape(14.dp),
        color = Color(0xFF181715),
        border = BorderStroke(1.dp, Color(0xFF34302B)),
    ) {
        Column(
            modifier = Modifier.padding(10.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Checkbox(checked = checked, onCheckedChange = onCheckedChange)
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(asset.displayName, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(asset.qualityTier, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                }
                StatusPill(modelStatusLabel(asset.downloadState), modelStatusColor(asset.downloadState))
            }
            progressValue?.let {
                LinearProgressIndicator(
                    progress = { it },
                    modifier = Modifier.fillMaxWidth().height(4.dp),
                    color = if (isReady) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.primary,
                    trackColor = Color(0x3324211E),
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
                        Spacer(modifier = Modifier.width(6.dp))
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
        modifier = modifier.height(40.dp),
        shape = RoundedCornerShape(4.dp),
        contentPadding = PaddingValues(horizontal = 4.dp, vertical = 0.dp),
    ) {
        Text(text, maxLines = 1, overflow = TextOverflow.Clip, fontSize = 11.sp)
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
                    modifier = Modifier.fillMaxWidth().height(420.dp).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    ImeAwareOutlinedTextField(value = providerId, onValueChange = { providerId = it }, label = "サービスID", modifier = Modifier.fillMaxWidth(), singleLine = true)
                    ImeAwareOutlinedTextField(value = displayName, onValueChange = { displayName = it }, label = "サービス名", modifier = Modifier.fillMaxWidth(), singleLine = true)
                    CompactLabel("接続形式")
                    WrapRow(horizontal = 6.dp, vertical = 6.dp) {
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
        shape = RoundedCornerShape(14.dp),
        color = if (active) Color(0x1A7FA6D8) else Color.Transparent,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Box(
                modifier = Modifier.size(38.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(10.dp)),
                contentAlignment = Alignment.Center,
            ) {
                Text(mark, style = MaterialTheme.typography.titleMedium)
            }
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
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
    SettingsPane.Demo -> "デモ設定"
    SettingsPane.Export -> "エクスポート"
    SettingsPane.Misc -> "その他"
    SettingsPane.Version -> "バージョン情報"
}

private fun settingsPaneSubtitle(pane: SettingsPane): String = when (pane) {
    SettingsPane.Home -> "List + Detail"
    SettingsPane.ModelSelection -> "Stage 1 / Stage 2 共通"
    SettingsPane.Models -> "OpenAI / Claude / Gemini / NVIDIA"
    SettingsPane.Demo -> "seed phrase / interval"
    SettingsPane.Export -> "PNG / SVG templates"
    SettingsPane.Misc -> "言語・テーマ・密度"
    SettingsPane.Version -> "version / build"
}

@Composable
private fun SettingCheckRow(checked: Boolean, text: String, onCheckedChange: (Boolean) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().clickable { onCheckedChange(!checked) },
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
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
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        CompactLabel(title)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
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
        shape = RoundedCornerShape(10.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            ImeAwareOutlinedTextField(name, { name = it }, label = "名前", modifier = Modifier.fillMaxWidth(), singleLine = true)
            ImeAwareOutlinedTextField(description, { description = it }, label = "説明", modifier = Modifier.fillMaxWidth(), singleLine = true)
            ImeAwareOutlinedTextField(height, { height = it.filter(Char::isDigit) }, label = "Y軸px", modifier = Modifier.fillMaxWidth(), singleLine = true)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
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
    WrapRow {
        choices.forEach { choice ->
            MiniPill(
                text = "${choice.providerName.take(10)} / ${choice.label.take(18)}",
                selected = choice.id == selectedValue,
                onClick = { onSelect(choice.id) },
            )
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
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF1B1A18)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier
                .border(1.dp, Color(0xFF34302B), RoundedCornerShape(14.dp))
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
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
        shape = RoundedCornerShape(14.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier
                .border(1.dp, Color(0xFF34302B), RoundedCornerShape(14.dp))
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(9.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(
                    modifier = Modifier.size(38.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(10.dp)),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(if (asset.qualityTier.contains("high", ignoreCase = true)) "E4" else "E2", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
                }
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(asset.displayName, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(asset.qualityTier, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                }
                StatusPill(modelStatusLabel(asset.downloadState), modelStatusColor(asset.downloadState))
            }

            progressValue?.let {
                LinearProgressIndicator(
                    progress = { it },
                    modifier = Modifier.fillMaxWidth().height(4.dp),
                    color = if (isReady) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.primary,
                    trackColor = Color(0x3324211E),
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
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
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
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
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
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
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
        modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
        verticalAlignment = Alignment.Bottom,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
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
            .border(1.dp, color.copy(alpha = 0.42f), RoundedCornerShape(100))
            .padding(horizontal = 9.dp, vertical = 4.dp),
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
    "failed", "cancelled" -> Color(0xFFE08A7A)
    "ready_to_download" -> Color(0xFFB8D58A)
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
                modifier = Modifier.height(54.dp).fillMaxWidth(),
                shape = RoundedCornerShape(4.dp),
                colors = if (selected) {
                    ButtonDefaults.outlinedButtonColors(
                        containerColor = MaterialTheme.colorScheme.secondary,
                        contentColor = Color(0xFF19150F),
                    )
                } else {
                    ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.onSurfaceVariant)
                },
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SwatchStrip(catalog.swatches.take(4))
                    Text(catalog.name, maxLines = 1)
                }
            }
        }
    }
}

@Composable
private fun SwatchStrip(colors: List<String>) {
    Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        colors.forEach { hex ->
            Box(
                modifier = Modifier
                    .size(14.dp)
                    .background(parseColor(hex), RoundedCornerShape(2.dp))
                    .border(1.dp, Color(0x66000000), RoundedCornerShape(2.dp)),
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
        modifier = modifier.border(1.dp, Color(0xFF2C2925), RoundedCornerShape(6.dp)),
        color = Color(0xFF1B1B1A),
        shape = RoundedCornerShape(6.dp),
    ) {
        Column(modifier = Modifier.fillMaxSize().padding(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
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
                    .background(Color(0xFF20201E), RoundedCornerShape(4.dp))
                    .padding(10.dp),
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
            .background(Color(0xFFF8F8F6), RoundedCornerShape(2.dp))
            .padding(10.dp)
            .verticalScroll(rememberScrollState()),
    ) {
        Text(text, color = Color(0xFF22201D), style = MaterialTheme.typography.bodySmall)
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
            .border(2.dp, if (selected) MaterialTheme.colorScheme.primary else Color.Transparent, RoundedCornerShape(0.dp))
            .border(4.dp, if (selected) Color(0x337FA6D8) else Color.Transparent, RoundedCornerShape(0.dp)),
        shape = RoundedCornerShape(0.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Box {
                HistoryArtworkPreview(item, modifier = Modifier.fillMaxWidth().aspectRatio(1f))
                if (selected) {
                    Box(
                        modifier = Modifier
                            .width(22.dp)
                            .height(22.dp)
                            .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(bottomEnd = 16.dp)),
                    )
                }
                if (item.starred) {
                    HistoryBadge(text = "★", selected = true, modifier = Modifier.align(Alignment.TopEnd).padding(6.dp))
                }
            }
            Row(modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(historyTitle(item), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.fillMaxWidth())
            }
        }
    }
}

@Composable
private fun HistoryBadge(text: String, selected: Boolean = false, onClick: (() -> Unit)? = null, modifier: Modifier = Modifier) {
    val base = modifier
        .size(26.dp)
        .background(
            if (selected) MaterialTheme.colorScheme.secondary else Color(0xCC24211E),
            RoundedCornerShape(13.dp),
        )
    Box(
        modifier = onClick?.let { base.clickable(onClick = it) } ?: base,
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelSmall,
            color = if (selected) Color(0xFF101010) else MaterialTheme.colorScheme.onSurface,
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
    WrapRow(horizontal = 6.dp, vertical = 6.dp) {
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
            .background(Color(0xFF191816), RoundedCornerShape(4.dp))
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(4.dp))
            .padding(horizontal = 8.dp, vertical = 6.dp)
            .clickable(onClick = onClick),
    ) {
        BasicTextField(
            value = value,
            onValueChange = {},
            readOnly = true,
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 112.dp)
                .pointerInput(value) {
                    detectTapGestures(onTap = { onClick() })
                }
                .drawBehind {
                    val layout = textLayoutResult ?: return@drawBehind
                    drawDdlKeywordHighlights(layout, value, vocabularyTokens)
                },
            textStyle = MaterialTheme.typography.bodySmall.copy(
                color = MaterialTheme.colorScheme.onSurface,
                lineHeight = 17.sp,
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
                        style = MaterialTheme.typography.bodySmall.copy(lineHeight = 17.sp),
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
                if (focusState.isFocused) {
                    scope.launchImeBringIntoViewGuard(bringIntoViewRequester)
                }
            }
            .background(Color(0xFF191816), RoundedCornerShape(4.dp))
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(4.dp))
            .padding(horizontal = 8.dp, vertical = 6.dp),
        textStyle = MaterialTheme.typography.bodySmall.copy(
            color = MaterialTheme.colorScheme.onSurface,
            lineHeight = 17.sp,
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
            .background(Color(0xFF191816), RoundedCornerShape(4.dp))
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 4.dp),
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
                fontSize = 16.sp,
                lineHeight = 21.sp,
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
    val horizontalPad = 1.5.dp.toPx()
    val verticalPad = 1.dp.toPx()
    val radius = 2.5.dp.toPx()
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
                            color = if (isLightColor(token.color)) Color(0xFF12110F) else Color(0xFFF8F8F6),
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
            .background(Color(0xFF191816), RoundedCornerShape(4.dp))
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(4.dp))
            .padding(horizontal = 8.dp, vertical = 6.dp),
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
    horizontal: androidx.compose.ui.unit.Dp = 8.dp,
    vertical: androidx.compose.ui.unit.Dp = 8.dp,
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
        shape = RoundedCornerShape(16.dp),
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
    Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
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
    val base = modifier.background(
        if (selected) MaterialTheme.colorScheme.primary else Color(0xDD24211E),
        RoundedCornerShape(100),
    )
    Text(
        text,
        modifier = (onClick?.let { base.clickable(onClick = it) } ?: base).padding(horizontal = 10.dp, vertical = 5.dp),
        style = MaterialTheme.typography.labelSmall,
        color = if (selected) Color(0xFF101010) else MaterialTheme.colorScheme.onSurface,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
    )
}

private fun BoxScope.presentationCaptionPlacement(screenWidth: Dp): Modifier =
    Modifier.align(Alignment.BottomCenter)
        .width(screenWidth * 0.92f)
        .padding(bottom = 92.dp)

@Composable
private fun PresentationCaption(text: String, rotation: DeviceRotation, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(8.dp),
        color = Color(0xB8000000),
        tonalElevation = 0.dp,
    ) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = 18.dp, vertical = 12.dp),
            color = Color(0xFFFFFDF8),
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
        color = Color(0xE01C1C1C),
        border = BorderStroke(1.dp, Color(0x2EFFFFFF)),
        tonalElevation = 0.dp,
        shadowElevation = 8.dp,
    ) {
        Row(
            modifier = Modifier.padding(6.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            PresentationControlButton("‹", enabled = canGoOlder, onClick = onGoOlder)
            PresentationControlButton("最新", enabled = canGoLatest, wide = true, onClick = onGoLatest)
            PresentationControlButton("›", enabled = canGoNewer, onClick = onGoNewer)
            Text(
                counter,
                modifier = Modifier.widthIn(min = 44.dp).padding(horizontal = 4.dp),
                color = Color(0xB8FFFDF8),
                style = MaterialTheme.typography.labelSmall,
                textAlign = TextAlign.Center,
                maxLines = 1,
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
    val shape = if (wide) RoundedCornerShape(100) else RoundedCornerShape(50)
    val background = when {
        selected -> Color(0x29FFFFFF)
        else -> Color(0x10FFFFFF)
    }
    val border = when {
        selected && text == "★" -> Color(0x9EFFD45C)
        else -> Color(0x2EFFFFFF)
    }
    Box(
        modifier = Modifier
            .then(if (wide) Modifier.widthIn(min = 54.dp) else Modifier.size(34.dp))
            .height(34.dp)
            .background(background, shape)
            .border(1.dp, border, shape)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = if (wide) 12.dp else 0.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text,
            color = when {
                !enabled -> Color(0x59FFFDF8)
                selected && text == "★" -> Color(0xFFFFD45C)
                else -> Color(0xFFFFFDF8)
            },
            style = if (wide) MaterialTheme.typography.labelSmall else MaterialTheme.typography.titleMedium,
            textAlign = TextAlign.Center,
            maxLines = 1,
        )
    }
}

@Composable
private fun ChipButton(text: String, selected: Boolean = false, onClick: () -> Unit) {
    if (selected) {
        Button(
            onClick = onClick,
            shape = RoundedCornerShape(100),
            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary, contentColor = Color(0xFF19150F)),
        ) { Text(text, maxLines = 1) }
    } else {
        OutlinedButton(
            onClick = onClick,
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
                    .width(64.dp)
                    .height(32.dp)
                    .background(
                        if (selected) Color(0x337FA6D8) else Color.Transparent,
                        RoundedCornerShape(16.dp),
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
        Row(modifier = modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Surface(
                modifier = Modifier.weight(1f).height(56.dp),
                shape = RoundedCornerShape(8.dp),
                color = if (tonal) MaterialTheme.colorScheme.surfaceVariant else Color(0xFF233144),
                tonalElevation = 1.dp,
            ) {
                Box(modifier = Modifier.fillMaxSize()) {
                    LinearProgressIndicator(
                        modifier = Modifier
                            .align(Alignment.BottomStart)
                            .fillMaxWidth()
                            .height(4.dp),
                        color = MaterialTheme.colorScheme.secondary,
                        trackColor = Color(0x3324211E),
                    )
                    Row(
                        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
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
            SecondaryActionButton(text = "停止", onClick = onStop, modifier = Modifier.width(104.dp))
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
        modifier = modifier.fillMaxWidth().height(56.dp),
        shape = RoundedCornerShape(28.dp),
        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary, contentColor = Color(0xFF101010)),
    ) { Text(text, maxLines = 1) }
}

@Composable
private fun SecondaryActionButton(text: String, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().height(56.dp),
        shape = RoundedCornerShape(28.dp),
    ) { Text(text, maxLines = 1) }
}

@Composable
private fun PrimarySmallButton(text: String, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.height(40.dp),
        shape = RoundedCornerShape(4.dp),
        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary, contentColor = Color(0xFF101010)),
    ) { Text(text, maxLines = 1) }
}

@Composable
private fun SecondarySmallButton(text: String, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.height(40.dp),
        shape = RoundedCornerShape(4.dp),
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
            color = Color(0xFFCFC6B6).copy(alpha = 0.72f),
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
            color = Color(0xFFDED6C9).copy(alpha = 0.72f),
            style = Stroke(
                width = unit * 0.004f,
                cap = StrokeCap.Round,
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(unit * 0.018f, unit * 0.018f)),
            ),
        )
        val shapeStroke = Stroke(width = unit * 0.006f, cap = StrokeCap.Round, join = StrokeJoin.Round)
        drawCircle(
            color = Color(0xFFD8CFC0).copy(alpha = 0.72f),
            radius = unit * 0.055f,
            center = Offset(w * 0.33f, h * 0.53f),
            style = shapeStroke,
        )
        drawRect(
            color = Color(0xFFD8CFC0).copy(alpha = 0.72f),
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
            color = Color(0xFFD8CFC0).copy(alpha = 0.72f),
            style = shapeStroke,
        )
    }
}

@Composable
private fun HistoryArtworkPreview(item: HistoryListItem, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val thumbnail by produceState<ImageBitmap?>(initialValue = null, item.id, item.renderHash, item.thumbnailPath) {
        value = HistoryThumbnailCache.get(context, item)
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

private fun hash01(index: Int, seed: String): Double {
    val digest = MessageDigest.getInstance("SHA-256").digest("$seed:$index".toByteArray())
    val raw = ((digest[0].toInt() and 0xff) shl 24) or ((digest[1].toInt() and 0xff) shl 16) or ((digest[2].toInt() and 0xff) shl 8) or (digest[3].toInt() and 0xff)
    return (raw.toLong() and 0xffffffffL).toDouble() / 0xffffffffL.toDouble()
}
