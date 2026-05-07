package app.inku.mobile.ui

import android.content.Context
import android.content.Intent
import android.content.ClipData
import android.graphics.Bitmap
import android.graphics.Canvas as AndroidCanvas
import android.net.Uri
import android.util.LruCache
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
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
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.text.AnnotatedString
import androidx.core.content.FileProvider
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.ColorCatalogs
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
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

private data class SaijikiGroup(val label: String, val en: String, val words: List<String>)
private data class ModelChoice(val id: String, val label: String, val providerName: String)
private data class ModelOptionChoice(val rawId: String, val qualifiedId: String, val label: String, val notes: String? = null)

private object HistoryThumbnailCache {
    private const val THUMBNAIL_PX = 384
    private val cache = LruCache<String, ImageBitmap>(64)

    suspend fun get(item: HistoryItemEntity): ImageBitmap? {
        val key = "${item.id}:${item.renderHash}:${item.displaySvg.length}:$THUMBNAIL_PX"
        synchronized(cache) {
            cache.get(key)?.let { return it }
        }
        return withContext(Dispatchers.Default) {
            val rendered = renderSvgThumbnail(item.displaySvg, THUMBNAIL_PX)
            if (rendered != null) {
                synchronized(cache) {
                    cache.put(key, rendered)
                }
            }
            rendered
        }
    }

    private fun renderSvgThumbnail(svgText: String, sizePx: Int): ImageBitmap? {
        return runCatching {
            val parsed = SVG.getFromString(svgText)
            val documentWidth = parsed.documentWidth.takeIf { it > 0f } ?: 1000f
            val documentHeight = parsed.documentHeight.takeIf { it > 0f } ?: 1000f
            val documentAspect = documentWidth / documentHeight
            val bitmap = Bitmap.createBitmap(sizePx, sizePx, Bitmap.Config.ARGB_8888)
            val canvas = AndroidCanvas(bitmap)
            canvas.drawColor(android.graphics.Color.WHITE)
            val drawWidth: Float
            val drawHeight: Float
            if (documentAspect >= 1f) {
                drawWidth = sizePx.toFloat()
                drawHeight = sizePx.toFloat() / documentAspect
            } else {
                drawHeight = sizePx.toFloat()
                drawWidth = sizePx.toFloat() * documentAspect
            }
            val left = (sizePx - drawWidth) / 2f
            val top = (sizePx - drawHeight) / 2f
            canvas.save()
            canvas.translate(left, top)
            parsed.setDocumentWidth(drawWidth)
            parsed.setDocumentHeight(drawHeight)
            parsed.renderToCanvas(canvas)
            canvas.restore()
            bitmap.asImageBitmap()
        }.getOrNull()
    }
}

private val saijikiGroups = listOf(
    SaijikiGroup("かたち", "forms", listOf("円", "楕円", "三角", "四角", "線", "弧")),
    SaijikiGroup("てざわり", "touches", listOf("髪", "鉛筆", "ペン", "ロットリング", "クレヨン", "チョーク", "細筆", "太筆", "縄")),
    SaijikiGroup("つらなり", "continuity", listOf("実線", "破線", "点線", "一点鎖線")),
    SaijikiGroup("いろ", "colors", listOf("白", "黒", "青", "赤", "緑", "灰")),
    SaijikiGroup("ゆらぎ", "movements", listOf("細かく", "大きく", "ゆっくり", "速く", "揺れる", "波打つ", "震える", "滲む")),
    SaijikiGroup("ばしょ", "places", listOf("上", "下", "中央", "左端", "右端", "上端", "下端", "中心", "隅")),
    SaijikiGroup("うごき", "motions", listOf("置く", "並べる", "埋める", "散らす", "引く")),
    SaijikiGroup("かたむき", "angles", listOf("水平", "垂直", "斜め", "右上がり", "右下がり", "回転")),
    SaijikiGroup("わりあい", "proportions", listOf("縦長", "横長", "全幅", "半幅", "半円", "上弦", "下弦", "三日月")),
)

@Composable
fun InkuApp() {
    val viewModel: InkuViewModel = androidx.lifecycle.viewmodel.compose.viewModel()
    val state by viewModel.state.collectAsState()
    val history by viewModel.historyItems.collectAsState()

    MaterialTheme(colorScheme = InkuColors) {
        Scaffold(
            bottomBar = { BottomNavigationBar(state.tab, viewModel) },
            containerColor = MaterialTheme.colorScheme.background,
        ) { padding ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .imePadding()
                    .background(MaterialTheme.colorScheme.background),
            ) {
                when (state.tab) {
                    AppTab.Compose -> ComposeScreen(state, viewModel)
                    AppTab.History -> HistoryScreen(state, history, viewModel)
                    AppTab.Demo -> DemoPanel(state, viewModel, modifier = Modifier.fillMaxSize().padding(12.dp))
                    AppTab.Settings -> SettingsPanel(state, viewModel, modifier = Modifier.fillMaxSize().padding(12.dp))
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
    AlertDialog(
        onDismissRequest = viewModel::closeDdlEditor,
        title = { Text("DDL編集") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                ImeAwareOutlinedTextField(
                    value = state.ddl,
                    onValueChange = viewModel::setDdl,
                    label = "正規化DDL",
                    modifier = Modifier.fillMaxWidth().height(320.dp),
                    minLines = 12,
                    maxLines = 18,
                    enabled = !state.isDrawing,
                )
                Text(
                    "歳時記の語は編集欄へ挿入されます。編集後は「DDLから描画」で Stage 2 を再実行します。",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    viewModel.closeDdlEditor()
                    viewModel.drawFromDdl()
                },
                enabled = !state.isDrawing,
            ) {
                Text("DDLから描画")
            }
        },
        dismissButton = {
            TextButton(onClick = viewModel::closeDdlEditor) {
                Text("閉じる")
            }
        },
    )
}

@Composable
private fun ModelSelectionDialog(state: InkuUiState, viewModel: InkuViewModel) {
    AlertDialog(
        onDismissRequest = viewModel::cancelModelSelection,
        title = { Text("モデル選択") },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth().height(560.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                WebStyleModelStageEditor(
                    title = "Stage 1",
                    sub = "自由記述 → 正規化DDL",
                    state = state,
                    selectedModelId = state.selectedModelId,
                    onSelectModel = viewModel::setStage1Model,
                )
                if (state.selectedModelId.contains("qwen3")) {
                    SettingCheckRow(
                        checked = state.includeThinking,
                        text = "思考を表示",
                        onCheckedChange = viewModel::setIncludeThinking,
                    )
                }
                WebStyleModelStageEditor(
                    title = "Stage 2",
                    sub = "正規化DDL → Score JSON",
                    state = state,
                    selectedModelId = state.selectedStage2ModelId,
                    onSelectModel = viewModel::setStage2Model,
                )
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
                        modifier = Modifier.fillMaxWidth().clickable { viewModel.setCanvasAspect(aspect.id) },
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
    return CanvasAspects.all.firstOrNull { it.id == state.selectedCanvasAspect }?.label ?: state.selectedCanvasAspect
}

@Composable
private fun ComposeScreen(state: InkuUiState, viewModel: InkuViewModel) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
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
            ConditionChips(state, viewModel)
            DrawPanel(state, viewModel)
        }
        Spacer(Modifier.height(96.dp))
    }
}

@Composable
private fun CanvasHeroCard(state: InkuUiState, viewModel: InkuViewModel) {
    val item = state.selectedHistory
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    var canvasMessage by remember { mutableStateOf<String?>(null) }
    var svgMenuOpen by remember { mutableStateOf(false) }
    var pngMenuOpen by remember { mutableStateOf(false) }
    BoxWithConstraints(modifier = Modifier.fillMaxWidth()) {
        val ratio = canvasAspectRatio(state.selectedCanvasAspect)
        val previewHeight = (maxWidth / ratio).coerceAtMost(330.dp)
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item?.let {
                WrapRow {
                    MiniPill(text = if (it.starred) "★" else "☆", selected = it.starred, onClick = { viewModel.toggleStar(it) })
                    MiniPill(
                        text = "F${it.renderHashShort}",
                        onClick = {
                            clipboard.setText(AnnotatedString(it.renderHashShort))
                            canvasMessage = "Hash copied."
                        },
                    )
                    MiniPill("-", onClick = { viewModel.setCanvasZoom(state.canvasZoom - 0.25f) })
                    MiniPill("${(state.canvasZoom * 100).toInt()}%", onClick = viewModel::resetCanvasZoom)
                    MiniPill("+", onClick = { viewModel.setCanvasZoom(state.canvasZoom + 0.25f) })
                }
            }
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(previewHeight)
                    .border(1.dp, Color(0x1A000000)),
                color = Color(0xFFFAFAF6),
                shape = RoundedCornerShape(0.dp),
                tonalElevation = 1.dp,
            ) {
                Box(modifier = Modifier.fillMaxSize()) {
                    if (item == null) {
                        Text("No render yet", color = Color(0xFF7D766E), modifier = Modifier.align(Alignment.Center))
                    } else {
                        ArtworkPreview(
                            item,
                            modifier = Modifier
                                .fillMaxSize()
                                .pointerInput(Unit) {
                                    detectTransformGestures { _, pan, zoom, _ ->
                                        if (zoom != 1f) viewModel.scaleCanvasZoom(zoom)
                                        if (pan != Offset.Zero) viewModel.panCanvas(pan.x, pan.y)
                                    }
                                }
                                .graphicsLayer(
                                    scaleX = state.canvasZoom,
                                    scaleY = state.canvasZoom,
                                    translationX = state.canvasPanX,
                                    translationY = state.canvasPanY,
                                ),
                        )
                    }
                }
            }
            item?.let {
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
                    }
                    Box {
                        MiniPill(text = "PNG ▾", onClick = { pngMenuOpen = true })
                    }
                }
                if (svgMenuOpen) {
                    WrapRow(horizontal = 6.dp, vertical = 6.dp) {
                        listOf(
                            "display" to "表示用SVG",
                            "editable" to "編集用SVG",
                            "compat" to "汎用SVG",
                        ).forEach { (profile, label) ->
                            MiniPill(
                                text = label,
                                onClick = {
                                    svgMenuOpen = false
                                    canvasMessage = "SVG export preparing..."
                                    scope.launch {
                                        canvasMessage = runCatching {
                                            shareHistorySvg(context, it, profile)
                                            "SVG exported F${it.renderHashShort}"
                                        }.getOrElse { error -> error.message ?: "SVG export failed." }
                                    }
                                },
                            )
                        }
                    }
                }
                if (pngMenuOpen) {
                    WrapRow(horizontal = 6.dp, vertical = 6.dp) {
                        listOf(1080, 2160, 4320).forEach { size ->
                            MiniPill(
                                text = "PNG ${size}px",
                                onClick = {
                                    pngMenuOpen = false
                                    canvasMessage = "PNG export preparing..."
                                    scope.launch {
                                        canvasMessage = runCatching {
                                            shareHistoryPng(context, it, size)
                                            "PNG exported F${it.renderHashShort}"
                                        }.getOrElse { error -> error.message ?: "PNG export failed." }
                                    }
                                },
                            )
                        }
                    }
                }
            }
        }
    }
    canvasMessage?.let { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelSmall) }
    item?.let {
        when (state.renderTab) {
            RenderTab.Artwork -> Unit
            RenderTab.Prompt -> RenderTextView(renderPromptText(it), Modifier.fillMaxWidth().height(180.dp))
            RenderTab.Json -> RenderTextView(renderJsonText(it), Modifier.fillMaxWidth().height(220.dp))
        }
    }
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
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            CompactLabel("指示")
            Spacer(Modifier.weight(1f))
            MiniPill("新規作成", onClick = viewModel::clearPrompt)
        }
        ImeAwareOutlinedTextField(
            value = state.prompt,
            onValueChange = viewModel::setPrompt,
            modifier = Modifier.fillMaxWidth(),
            minLines = 3,
            maxLines = 4,
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
            CompactLabel("解釈（正規化DDL）")
            Spacer(Modifier.weight(1f))
            DdlActionRow(state, viewModel)
        }
        if (state.saijikiOpen) {
            SaijikiPanel(viewModel)
        }
        ImeAwareOutlinedTextField(
            value = state.ddl,
            onValueChange = viewModel::setDdl,
            modifier = Modifier.fillMaxWidth(),
            minLines = 3,
            maxLines = 5,
        )
        DrawingActionButton(
            idleText = "▶  DDLから描画",
            runningText = "■  描画中",
            state = state,
            onClick = viewModel::drawFromDdl,
            onStop = viewModel::stopDrawing,
            tonal = true,
        )
        MetaPanel(state)
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
        if (nonEmpty > 0) {
            Text("${nonEmpty} 件", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (!state.isDrawing) {
            SettingCheckRow(
                checked = state.batchRandomColorCatalog,
                text = "描画ごとに色カタログをランダム選択",
                onCheckedChange = viewModel::setBatchRandomColorCatalog,
            )
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
    val lines = remember(value) { value.lines() }
    val lineCount = maxOf(lines.size, 1)
    val lineNumbers = remember(lineCount) { (1..lineCount).joinToString("\n") }
    val scrollState = rememberScrollState()
    val bringIntoViewRequester = remember { BringIntoViewRequester() }
    val scope = rememberCoroutineScope()
    val textStyle = MaterialTheme.typography.bodyLarge.copy(
        color = MaterialTheme.colorScheme.onSurface,
        lineHeight = 32.sp,
    )

    Surface(
        modifier = modifier
            .height(320.dp)
            .bringIntoViewRequester(bringIntoViewRequester),
        shape = RoundedCornerShape(16.dp),
        color = Color.Transparent,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        Row(
            modifier = Modifier
                .fillMaxSize()
                .clipToBounds()
                .verticalScroll(scrollState)
                .padding(horizontal = 12.dp, vertical = 14.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                lineNumbers,
                style = textStyle,
                textAlign = TextAlign.End,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.width(36.dp),
            )
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                enabled = enabled,
                textStyle = textStyle,
                cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 32.dp * maxOf(lineCount, 6))
                    .onFocusChanged { focusState ->
                        if (focusState.isFocused) {
                            scope.launch {
                                delay(260)
                                bringIntoViewRequester.bringIntoView()
                            }
                        }
                    },
            )
        }
    }
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
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        CanvasHeroCard(state, viewModel)
        CompactLabel("デモ")
        ImeAwareOutlinedTextField(
            value = state.demoSeed,
            onValueChange = viewModel::setDemoSeed,
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )
        Text("interval ${state.demoIntervalSeconds}s / save current result manually", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        DrawingActionButton(
            idleText = "▶  1回描画",
            runningText = "■  描画中",
            state = state,
            onClick = viewModel::runDemoOnce,
            onStop = viewModel::stopDrawing,
        )
        state.message?.let { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall) }
        MetaPanel(state)
    }
}

@Composable
private fun HistoryScreen(
    state: InkuUiState,
    history: List<HistoryItemEntity>,
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
        SettingsPane.Export -> ExportSettingsPanel(state, viewModel, modifier)
        SettingsPane.Misc -> MiscSettingsPanel(state, viewModel, modifier)
        SettingsPane.OutputFiles -> OutputFilesSettingsPanel(state, viewModel, modifier)
        SettingsPane.ColorCatalog -> ColorCatalogSelectionPanel(state, viewModel, modifier)
        SettingsPane.Canvas -> CanvasSelectionPanel(state, viewModel, modifier)
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
        SettingsListItem(mark = "◐", title = "表示設定", sub = "言語・テーマ・密度", onClick = { viewModel.setSettingsPane(SettingsPane.Misc) })
        SettingsListItem(mark = "◇", title = "モデル設定", sub = "OpenAI / Claude / Gemini / NVIDIA", onClick = { viewModel.setSettingsPane(SettingsPane.Models) })
        SettingsListItem(
            mark = "◓",
            title = "色カタログ",
            sub = "${ColorCatalogs.get(state.selectedCatalogId).name}（選択中）",
            onClick = viewModel::openCatalogSelection,
        )
        SettingsListItem(mark = "⬚", title = "エクスポート", sub = "PNG 1080 / 2160 / 4320", onClick = { viewModel.setSettingsPane(SettingsPane.Export) })
        SettingsListItem(mark = "◭", title = "出力ファイル", sub = "共有シート · PNG/SVG/JSON", onClick = { viewModel.setSettingsPane(SettingsPane.OutputFiles) })
        SettingsListItem(
            mark = "□",
            title = "キャンバス",
            sub = CanvasAspects.all.firstOrNull { it.id == state.selectedCanvasAspect }?.label ?: state.selectedCanvasAspect,
            onClick = viewModel::openCanvasSelection,
        )
        Text("BUILD debug · v0.1.0", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp))
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
        SettingsCard("Stage 1", "自由記述 → 正規化DDL", selectedModelLabel(state)) {
            ModelChoiceRow(
                choices = modelChoices,
                selectedValue = state.selectedModelId,
                onSelect = viewModel::setStage1Model,
            )
        }
        SettingsCard("Stage 2", "正規化DDL → Score JSON", selectedStage2ModelLabel(state)) {
            ModelChoiceRow(
                choices = modelChoices,
                selectedValue = state.selectedStage2ModelId,
                onSelect = viewModel::setStage2Model,
            )
        }
        SecondaryActionButton(text = "接続先設定を開く", onClick = { viewModel.setSettingsPane(SettingsPane.Models) })
    }
}

@Composable
private fun ColorCatalogSelectionPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
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
            Text("色カタログ", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
            SecondarySmallButton(text = "取消", onClick = viewModel::cancelCatalogSelection)
            PrimarySmallButton(text = "決定", onClick = viewModel::confirmCatalogSelection)
        }
        ColorCatalogButtonRow(state.selectedCatalogId, viewModel::setCatalog)
        ColorCatalogs.all.forEach { catalog ->
            SettingsCard(catalog.name, catalog.id, if (catalog.id == state.selectedCatalogId) "選択中" else "未選択") {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    SwatchStrip(catalog.swatches.take(8))
                    Spacer(Modifier.weight(1f))
                    SecondarySmallButton(text = "選択", onClick = { viewModel.setCatalog(catalog.id) })
                }
            }
        }
    }
}

@Composable
private fun CanvasSelectionPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
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
            Text("キャンバス", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
            PrimarySmallButton(text = "閉じる", onClick = viewModel::closeTransientPanel)
        }
        HorizontalChoiceRow(
            values = CanvasAspects.all.map { it.id to it.label },
            selectedValue = state.selectedCanvasAspect,
            onSelect = viewModel::setCanvasAspect,
        )
        CanvasAspects.all.forEach { aspect ->
            SettingsCard(aspect.label, "${aspect.ratioW}:${aspect.ratioH}", if (aspect.id == state.selectedCanvasAspect) "選択中" else "未選択") {
                SecondarySmallButton(text = "選択", onClick = { viewModel.setCanvasAspect(aspect.id) })
            }
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
private fun OutputFilesSettingsPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.verticalScroll(rememberScrollState()).padding(horizontal = 4.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        SettingsHeader(state.settingsPane, viewModel)
        SettingsCard("共有形式", "Android share sheet", "有効") {
            Text("描画結果はSVG、PNG、JSONとして共有できます。PNG生成はバックグラウンドで実行し、生成完了後に共有シートを開きます。", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            WrapRow {
                MiniPill("SVG display")
                MiniPill("SVG editable")
                MiniPill("SVG compat")
                MiniPill("PNG 1080")
                MiniPill("PNG 2160")
                MiniPill("PNG 4320")
                MiniPill("JSON")
            }
        }
        SettingsCard("PNG背景", "Web版のPNG出力設定", if (state.pngAlphaWhite) "白背景" else "透明") {
            SettingCheckRow(
                checked = state.pngAlphaWhite,
                text = "PNG透過時の白背景",
                onCheckedChange = viewModel::setPngAlphaWhite,
            )
        }
    }
}

@Composable
private fun ModelSettingsPanel(state: InkuUiState, viewModel: InkuViewModel, modifier: Modifier = Modifier) {
    val modelChoices = remember(state.modelAssets, state.providerSettings) { modelChoicesFor(state) }
    val selectedChoice = modelChoices.firstOrNull { it.id == state.selectedModelId }
    val selectedStage2Choice = modelChoices.firstOrNull { it.id == state.selectedStage2ModelId }
    val downloadInProgress = state.modelAssets.any { asset ->
        asset.downloadState in setOf("queued", "connecting", "downloading", "verifying")
    }
    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 4.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        SettingsHeader(state.settingsPane, viewModel)

        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(18.dp),
            color = Color(0x1A7FA6D8),
            tonalElevation = 1.dp,
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, Color(0x407FA6D8), RoundedCornerShape(18.dp))
                    .padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Box(
                        modifier = Modifier.size(44.dp).background(MaterialTheme.colorScheme.primary, RoundedCornerShape(22.dp)),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text("◇", color = Color(0xFF101010), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    }
                    Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        Text("既定モデル", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Medium)
                        Text(
                            "Stage1 · ${selectedChoice?.label ?: selectedModelLabel(state)} / Stage2 · ${selectedStage2Choice?.label ?: selectedStage2ModelLabel(state)}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    StatusPill("LOCAL", MaterialTheme.colorScheme.primary)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    SecondarySmallButton(text = "モデル選択を開く", onClick = viewModel::openModelSelection, modifier = Modifier.weight(1f))
                    SecondarySmallButton(text = "S1/S2を標準へ", onClick = {
                        state.modelAssets.firstOrNull()?.let {
                            viewModel.setStage1Model(it.modelId)
                            viewModel.setStage2Model(it.modelId)
                        }
                    }, modifier = Modifier.weight(1f))
                }
                SettingsSectionHeader("STAGE 1", "自由記述 → 正規化DDL")
                ModelChoiceRow(
                    choices = modelChoices,
                    selectedValue = state.selectedModelId,
                    onSelect = viewModel::setStage1Model,
                )
                SettingsSectionHeader("STAGE 2", "正規化DDL → Score JSON")
                ModelChoiceRow(
                    choices = modelChoices,
                    selectedValue = state.selectedStage2ModelId,
                    onSelect = viewModel::setStage2Model,
                )
            }
        }

        SettingsSectionHeader("AI SERVICE CONNECTIONS", "Web版と同じ接続先")
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            state.providerSettings.forEach { provider ->
                ProviderConnectionCard(
                    provider = provider,
                    assets = state.modelAssets,
                    onSave = viewModel::saveProviderSetting,
                    onFetchModels = { viewModel.fetchProviderModels(provider.providerId) },
                    onClearApiKey = { viewModel.clearProviderApiKey(provider.providerId) },
                    onDelete = { viewModel.deleteProvider(provider.providerId) },
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SecondarySmallButton(text = "モデルリスト取得", onClick = viewModel::refreshModelCatalog, modifier = Modifier.weight(1f))
            }
            AddProviderCard(onAdd = viewModel::saveProviderSetting)
        }

        SettingsSectionHeader("MODEL ASSETS", "使用可能モデル")
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            state.modelAssets.forEach { asset ->
                ModelAssetControls(
                    asset = asset,
                    stage1Active = asset.modelId == state.selectedModelId,
                    stage2Active = asset.modelId == state.selectedStage2ModelId,
                    onSelectStage1 = { viewModel.setStage1Model(asset.modelId) },
                    onSelectStage2 = { viewModel.setStage2Model(asset.modelId) },
                    onAccept = { viewModel.acceptModelLicense(asset.modelId) },
                    onDownload = { viewModel.downloadModel(asset.modelId) },
                )
            }
            SecondaryActionButton(text = "取得中断", onClick = viewModel::cancelModelDownload, enabled = downloadInProgress)
            state.message?.let {
                Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun ProviderConnectionCard(
    provider: app.inku.mobile.data.db.ProviderSettingEntity,
    assets: List<app.inku.mobile.data.db.ModelAssetEntity>,
    onSave: (String, String, String, String, String, String) -> Unit,
    onFetchModels: () -> Unit,
    onClearApiKey: () -> Unit,
    onDelete: () -> Unit,
) {
    val requiresKey = provider.providerId in setOf("openai", "nvidia", "anthropic", "gemini")
    val keySet = !provider.encryptedApiKey.isNullOrBlank()
    var displayName by remember(provider.providerId, provider.displayName) { mutableStateOf(provider.displayName) }
    var kind by remember(provider.providerId, provider.kind) { mutableStateOf(provider.kind) }
    var baseUrl by remember(provider.providerId, provider.baseUrl) { mutableStateOf(provider.baseUrl.orEmpty()) }
    var apiKey by remember(provider.providerId, provider.encryptedApiKey) { mutableStateOf("") }
    var confirmClearKey by remember(provider.providerId) { mutableStateOf(false) }
    var confirmDeleteService by remember(provider.providerId) { mutableStateOf(false) }
    var publishedModels by remember(provider.providerId, provider.publishedModelsJson) {
        mutableStateOf(parsePublishedModelIds(provider.publishedModelsJson).joinToString("\n"))
    }
    SettingsCard(
        provider.displayName,
        "接続形式: ${provider.kind}${if (requiresKey) " / APIキー必須" else " / APIキー任意"}",
        "Service ID: ${provider.providerId} / Base URL: ${provider.baseUrl ?: "-"}",
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                StatusPill(if (keySet) "APIキー設定済み" else if (requiresKey) "APIキー未設定" else "APIキー不要", if (keySet || !requiresKey) MaterialTheme.colorScheme.secondary else Color(0xFFE08A7A))
                StatusPill(if (provider.isEnabled) "有効" else "無効", if (provider.isEnabled) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant)
                if (provider.isDefaultLocal) StatusPill("LOCAL", MaterialTheme.colorScheme.primary)
            }
            ImeAwareOutlinedTextField(
                value = displayName,
                onValueChange = { displayName = it },
                label = "サービス名",
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            ImeAwareOutlinedTextField(
                value = kind,
                onValueChange = { kind = it },
                label = "接続形式",
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            ImeAwareOutlinedTextField(
                value = baseUrl,
                onValueChange = { baseUrl = it },
                label = "Base URL",
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            ImeAwareOutlinedTextField(
                value = apiKey,
                onValueChange = { apiKey = it },
                label = if (keySet) "新しいAPIキー（空なら維持）" else "APIキー",
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            ImeAwareOutlinedTextField(
                value = publishedModels,
                onValueChange = { publishedModels = it },
                label = "使用可能モデル（1行に1 model-id）",
                modifier = Modifier.fillMaxWidth().height(120.dp),
            )
            ProviderModelActionRow(
                provider = provider,
                publishedModels = publishedModels,
                onPublishedModelsChange = { publishedModels = it },
                onFetchModels = onFetchModels,
                onSave = { onSave(provider.providerId, displayName, kind, baseUrl, apiKey, publishedModels) },
            )
            PublishedModelsSummary(publishedModelsJsonFromText(publishedModels), assets)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SecondarySmallButton(text = "APIキー削除", onClick = { confirmClearKey = true }, enabled = keySet, modifier = Modifier.weight(1f))
                SecondarySmallButton(text = "サービス削除", onClick = { confirmDeleteService = true }, enabled = !provider.isDefaultLocal, modifier = Modifier.weight(1f))
                PrimarySmallButton(
                    text = "保存",
                    onClick = { onSave(provider.providerId, displayName, kind, baseUrl, apiKey, publishedModels) },
                    modifier = Modifier.weight(1f),
                )
            }
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
private fun ProviderModelActionRow(
    provider: app.inku.mobile.data.db.ProviderSettingEntity,
    publishedModels: String,
    onPublishedModelsChange: (String) -> Unit,
    onFetchModels: () -> Unit,
    onSave: () -> Unit,
) {
    var pickerOpen by remember(provider.providerId) { mutableStateOf(false) }
    val currentModels = parsePublishedModelIds(provider.publishedModelsJson).ifEmpty { defaultProviderModelIds(provider.providerId) }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        SecondarySmallButton(
            text = "全て選択",
            onClick = { onPublishedModelsChange(currentModels.joinToString("\n")) },
            modifier = Modifier.weight(1f),
        )
        SecondarySmallButton(
            text = "全て解除",
            onClick = { onPublishedModelsChange("") },
            modifier = Modifier.weight(1f),
        )
        SecondarySmallButton(
            text = "最新取得",
            onClick = onFetchModels,
            modifier = Modifier.weight(1f),
        )
        SecondarySmallButton(
            text = "モデル選択",
            onClick = {
                pickerOpen = true
            },
            modifier = Modifier.weight(1f),
        )
    }
    if (pickerOpen) {
        ProviderModelPickerDialog(
            providerName = provider.displayName,
            models = currentModels,
            publishedModels = publishedModels,
            onPublishedModelsChange = onPublishedModelsChange,
            onFetchModels = onFetchModels,
            onSave = onSave,
            onClose = { pickerOpen = false },
        )
    }
}

@Composable
private fun ProviderModelPickerDialog(
    providerName: String,
    models: List<String>,
    publishedModels: String,
    onPublishedModelsChange: (String) -> Unit,
    onFetchModels: () -> Unit,
    onSave: () -> Unit,
    onClose: () -> Unit,
) {
    var search by remember(providerName) { mutableStateOf("") }
    var selected by remember(providerName, publishedModels) {
        mutableStateOf(publishedModels.lines().map { it.trim() }.filter { it.isNotBlank() }.toSet())
    }
    val filtered = remember(models, search) {
        val query = search.trim().lowercase()
        if (query.isBlank()) models else models.filter { it.lowercase().contains(query) }
    }

    fun save(next: Set<String>) {
        selected = next
        onPublishedModelsChange(next.joinToString("\n"))
    }

    AlertDialog(
        onDismissRequest = onClose,
        title = { Text("$providerName モデル選択") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SecondarySmallButton(text = "最新取得", onClick = onFetchModels, modifier = Modifier.weight(1f))
                    SecondarySmallButton(text = "全て選択", onClick = { save(filtered.toSet()) }, modifier = Modifier.weight(1f))
                    SecondarySmallButton(text = "全て解除", onClick = { save(selected - filtered.toSet()) }, modifier = Modifier.weight(1f))
                }
                ImeAwareOutlinedTextField(
                    value = search,
                    onValueChange = { search = it },
                    label = "モデル検索",
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                )
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(280.dp)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    filtered.forEach { modelId ->
                        val active = modelId in selected
                        Surface(
                            modifier = Modifier.fillMaxWidth().clickable {
                                save(if (active) selected - modelId else selected + modelId)
                            },
                            shape = RoundedCornerShape(8.dp),
                            color = if (active) Color(0x1AEAD7A3) else MaterialTheme.colorScheme.surface,
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 9.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                Text(if (active) "✓" else "", modifier = Modifier.width(18.dp), color = MaterialTheme.colorScheme.secondary)
                                Text(modelId, style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                onPublishedModelsChange(selected.joinToString("\n"))
                onSave()
                onClose()
            }) { Text("保存") }
        },
        dismissButton = {
            TextButton(onClick = onClose) { Text("キャンセル") }
        },
    )
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
    var publishedModels by remember { mutableStateOf("") }
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
                    ImeAwareOutlinedTextField(value = publishedModels, onValueChange = { publishedModels = it }, label = "モデル一覧（1行に1 model-id）", modifier = Modifier.fillMaxWidth().height(110.dp))
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        onAdd(providerId, displayName, kind, baseUrl, apiKey, publishedModels)
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
    SettingsPane.Export -> "エクスポート"
    SettingsPane.Misc -> "表示設定"
    SettingsPane.OutputFiles -> "出力ファイル"
    SettingsPane.ColorCatalog -> "色カタログ"
    SettingsPane.Canvas -> "キャンバス"
}

private fun settingsPaneSubtitle(pane: SettingsPane): String = when (pane) {
    SettingsPane.Home -> "List + Detail"
    SettingsPane.ModelSelection -> "Stage 1 / Stage 2"
    SettingsPane.Models -> "OpenAI / Claude / Gemini / NVIDIA"
    SettingsPane.Export -> "PNG / SVG templates"
    SettingsPane.Misc -> "言語・テーマ・密度"
    SettingsPane.OutputFiles -> "共有シート · PNG/SVG/JSON"
    SettingsPane.ColorCatalog -> "render color catalog"
    SettingsPane.Canvas -> "canvas aspect"
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

@Composable
private fun PublishedModelsSummary(
    publishedModelsJson: String?,
    assets: List<app.inku.mobile.data.db.ModelAssetEntity>,
) {
    val ids = remember(publishedModelsJson, assets) {
        publishedModelsJson?.takeIf { it.isNotBlank() }?.let(::parsePublishedModelIds)
            ?: assets.map { it.modelId }
    }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        CompactLabel("使用可能モデル")
        if (ids.isEmpty()) {
            Text("使用可能モデルは未選択です。", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            WrapRow(horizontal = 6.dp, vertical = 6.dp) {
                ids.forEach { id ->
                    val label = assets.firstOrNull { it.modelId == id }?.displayName ?: id.substringAfterLast(":")
                    MiniPill(label.take(22))
                }
            }
        }
    }
}

private fun parsePublishedModelIds(value: String): List<String> {
    return runCatching {
        val array = JSONArray(value)
        (0 until array.length()).mapNotNull { array.optString(it).takeIf { id -> id.isNotBlank() } }
    }.getOrElse {
        value.lines().map { it.trim() }.filter { it.isNotBlank() }
    }
}

private fun publishedModelsJsonFromText(value: String): String {
    return JSONArray(value.lines().map { it.trim() }.filter { it.isNotBlank() }).toString()
}

private fun defaultProviderModelIds(providerId: String): List<String> = when (providerId) {
    "openai" -> listOf("openai:gpt-5.1", "openai:gpt-5.1-mini", "openai:gpt-4.1", "openai:gpt-4.1-mini")
    "nvidia" -> listOf("google/gemma-4-31b-it", "meta/llama-3.3-70b-instruct", "mistralai/mistral-large-2-instruct")
    "anthropic" -> listOf("anthropic:claude-opus-4-7", "anthropic:claude-sonnet-4-6", "anthropic:claude-haiku-4-5-20251001")
    "gemini" -> listOf("gemini:gemini-2.5-pro", "gemini:gemini-2.5-flash", "gemini:gemini-2.5-flash-lite")
    "ollama" -> listOf("ollama:llama3.2", "ollama:gpt-oss:20b", "ollama:qwen3:8b")
    "ovms" -> listOf("qwen3-api", "qwen-api", "gemma3-12b-api", "gemma3-4b-api")
    "local-litert-lm" -> listOf("local-litert-lm:gemma-4-e2b", "local-litert-lm:gemma-4-e4b")
    else -> emptyList()
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
private fun SettingsCard(title: String, sub: String, status: String, actions: @Composable () -> Unit) {
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
            Text(title, style = MaterialTheme.typography.titleSmall)
            Text(sub, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(status, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
            actions()
        }
    }
}

@Composable
private fun ModelAssetControls(
    asset: app.inku.mobile.data.db.ModelAssetEntity,
    stage1Active: Boolean,
    stage2Active: Boolean,
    onSelectStage1: () -> Unit,
    onSelectStage2: () -> Unit,
    onAccept: () -> Unit,
    onDownload: () -> Unit,
) {
    val isReady = asset.downloadState == "ready"
    val isBusy = asset.downloadState in setOf("queued", "connecting", "downloading", "verifying")
    val active = stage1Active || stage2Active
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
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onSelectStage1),
        shape = RoundedCornerShape(14.dp),
        color = if (active) Color(0x1AEAD7A3) else MaterialTheme.colorScheme.surface,
        tonalElevation = if (active) 2.dp else 0.dp,
    ) {
        Column(
            modifier = Modifier
                .border(1.dp, if (active) MaterialTheme.colorScheme.secondary else Color(0xFF34302B), RoundedCornerShape(14.dp))
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
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(asset.displayName, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        if (stage1Active) StatusPill("S1", MaterialTheme.colorScheme.secondary)
                        if (stage2Active) StatusPill("S2", MaterialTheme.colorScheme.primary)
                    }
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
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SecondarySmallButton(text = if (stage1Active) "Stage1中" else "Stage1", onClick = onSelectStage1, modifier = Modifier.weight(1f))
                SecondarySmallButton(text = if (stage2Active) "Stage2中" else "Stage2", onClick = onSelectStage2, modifier = Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SecondarySmallButton(text = if (asset.licenseAcceptedAt != null) "同意済み" else "同意", onClick = onAccept, modifier = Modifier.weight(1f))
                PrimarySmallButton(
                    text = when {
                        isReady -> "取得済み"
                        isBusy -> "取得中"
                        else -> "取得/再開"
                    },
                    onClick = onDownload,
                    enabled = !isReady && !isBusy,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
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
                        RenderTab.Prompt -> RenderTextView(renderPromptText(item), Modifier.fillMaxSize())
                        RenderTab.Json -> RenderTextView(renderJsonText(item), Modifier.fillMaxSize())
                    }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    state.message ?: "LLM Stage1 ${selectedModelLabel(state)} | Stage2 ${selectedStage2ModelLabel(state)}",
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

private fun renderPromptText(item: HistoryItemEntity): String {
    return buildString {
        appendLine("original:")
        appendLine(item.originalInput)
        appendLine()
        appendLine("normalized DDL:")
        appendLine(item.normalizedDdl)
        item.expandedDdl?.let {
            appendLine()
            appendLine("expanded DDL:")
            appendLine(it)
        }
    }
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

private fun JSONObject.putFrom(source: JSONObject, key: String, fallback: String? = null) {
    if (source.has(key) && !source.isNull(key)) {
        put(key, source.get(key))
    } else if (!fallback.isNullOrBlank()) {
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
    val height = targetHeight.coerceIn(64, 12000)
    val width = (height * documentWidth / documentHeight).toInt().coerceAtLeast(64)
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

private fun filterHistoryItems(history: List<HistoryItemEntity>, state: InkuUiState): List<HistoryItemEntity> {
    val query = state.historySearchQuery.trim().lowercase()
    return history.filter { item ->
        (!state.historyStarredOnly || item.starred) &&
            (query.isBlank() || historySearchText(item).contains(query))
    }
}

private fun historySearchText(item: HistoryItemEntity): String {
    return listOf(
        item.originalInput,
        item.normalizedDdl,
        item.renderHash,
        item.renderHashShort,
        item.stage1Model,
        item.stage2Model,
        item.colorCatalogId,
        item.canvasAspect,
    ).joinToString("\n").lowercase()
}

@Composable
private fun HistoryStrip(history: List<HistoryItemEntity>, selected: HistoryItemEntity?, viewModel: InkuViewModel) {
    Surface(modifier = Modifier.navigationBarsPadding(), color = Color(0xFF151412), tonalElevation = 2.dp) {
        Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("履歴 (${history.size})", style = MaterialTheme.typography.labelMedium)
                Spacer(Modifier.weight(1f))
                selected?.let { Text(it.renderHashShort, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.secondary) }
            }
            WrapRow {
                history.take(8).forEach { item ->
                    HistoryTile(item = item, selected = selected?.id == item.id, onSelect = { viewModel.selectHistory(item) })
                }
            }
        }
    }
}

@Composable
private fun HistoryTile(item: HistoryItemEntity, selected: Boolean, onSelect: () -> Unit) {
    Card(
        modifier = Modifier
            .width(84.dp)
            .height(96.dp)
            .clickable(onClick = onSelect)
            .border(1.dp, if (selected) MaterialTheme.colorScheme.secondary else Color.Transparent, RoundedCornerShape(4.dp)),
        shape = RoundedCornerShape(4.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF24211E)),
    ) {
        Column(modifier = Modifier.padding(5.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            HistoryArtworkPreview(item, modifier = Modifier.fillMaxWidth().height(52.dp))
            Text(item.elapsedMs?.let { "${it / 1000.0}s" } ?: item.renderHashShort, style = MaterialTheme.typography.labelSmall, maxLines = 1)
            Text(historyTitle(item), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun HistoryGridTile(
    item: HistoryItemEntity,
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
            .border(2.dp, if (selected) MaterialTheme.colorScheme.primary else Color.Transparent, RoundedCornerShape(14.dp))
            .border(4.dp, if (selected) Color(0x337FA6D8) else Color.Transparent, RoundedCornerShape(18.dp)),
        shape = RoundedCornerShape(14.dp),
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
                Text(historyTitle(item), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                Text(item.renderHashShort, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.secondary)
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

private fun historyTitle(item: HistoryItemEntity): String {
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

@Composable
private fun DdlActionRow(state: InkuUiState, viewModel: InkuViewModel) {
    WrapRow(horizontal = 6.dp, vertical = 6.dp) {
        MiniPill("歳時記", selected = state.saijikiOpen, onClick = viewModel::toggleSaijiki)
        MiniPill("DDL編集", onClick = viewModel::openDdlEditor)
        MiniPill("自動補正", selected = state.ddlAutoRepairEnabled, onClick = viewModel::toggleDdlAutoRepair)
    }
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
                    scope.launch {
                        delay(260)
                        bringIntoViewRequester.bringIntoView()
                    }
                }
            },
        minLines = minLines,
        maxLines = maxLines,
        singleLine = singleLine,
        enabled = enabled,
        shape = RoundedCornerShape(16.dp),
    )
}

@Composable
private fun MetaPanel(state: InkuUiState) {
    Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("LLM Stage1 · ${selectedModelLabel(state)}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("LLM Stage2 · ${selectedStage2ModelLabel(state)}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("Color · ${ColorCatalogs.get(state.selectedCatalogId).name}   Canvas · ${state.selectedCanvasAspect}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
    )
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

@Composable
private fun ArtworkPreview(item: HistoryItemEntity, modifier: Modifier = Modifier) {
    val svg = remember(item.id, item.displaySvg) {
        runCatching { SVG.getFromString(item.displaySvg) }.getOrNull()
    }
    Surface(color = Color.White, shape = RoundedCornerShape(2.dp), modifier = modifier) {
        Canvas(modifier = Modifier.fillMaxSize().padding(2.dp)) {
            drawRect(Color.White)
            val parsed = svg ?: return@Canvas
            val documentWidth = parsed.documentWidth.takeIf { it > 0f } ?: 1000f
            val documentHeight = parsed.documentHeight.takeIf { it > 0f } ?: 1000f
            val documentAspect = documentWidth / documentHeight
            val boxAspect = size.width / size.height
            val drawWidth: Float
            val drawHeight: Float
            if (documentAspect >= boxAspect) {
                drawWidth = size.width
                drawHeight = size.width / documentAspect
            } else {
                drawHeight = size.height
                drawWidth = size.height * documentAspect
            }
            val left = (size.width - drawWidth) / 2f
            val top = (size.height - drawHeight) / 2f
            drawIntoCanvas { canvas ->
                val native = canvas.nativeCanvas
                native.save()
                native.translate(left, top)
                parsed.setDocumentWidth(drawWidth)
                parsed.setDocumentHeight(drawHeight)
                parsed.renderToCanvas(native)
                native.restore()
            }
        }
    }
}

@Composable
private fun HistoryArtworkPreview(item: HistoryItemEntity, modifier: Modifier = Modifier) {
    val thumbnail by produceState<ImageBitmap?>(initialValue = null, item.id, item.renderHash, item.displaySvg) {
        value = HistoryThumbnailCache.get(item)
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

private fun strokeWidthPx(weight: String): Float = when (weight) {
    "brush_thick" -> 8f
    "rope" -> 10f
    "crayon" -> 4f
    "chalk", "brush_thin" -> 3f
    "pencil" -> 1.5f
    else -> 2f
}

private fun ratio(value: Double): Float = value.coerceIn(0.0, 1.0).toFloat()

private fun canvasAspectRatio(id: String): Float {
    return when (CanvasAspects.normalize(id)) {
        "golden" -> 1.618f
        "a4" -> 0.707f
        "b4" -> 0.707f
        "pillar" -> 0.5f
        "oban" -> 0.68f
        "wide" -> 1.777f
        "byobu" -> 2.4f
        "vertical" -> 0.75f
        else -> 1f
    }
}

private fun hash01(index: Int, seed: String): Double {
    val digest = MessageDigest.getInstance("SHA-256").digest("$seed:$index".toByteArray())
    val raw = ((digest[0].toInt() and 0xff) shl 24) or ((digest[1].toInt() and 0xff) shl 16) or ((digest[2].toInt() and 0xff) shl 8) or (digest[3].toInt() and 0xff)
    return (raw.toLong() and 0xffffffffL).toDouble() / 0xffffffffL.toDouble()
}
