package app.inku.mobile.ui

import android.content.Context
import android.content.Intent
import android.content.ClipData
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.model.CanvasAspects
import app.inku.mobile.data.model.ColorCatalogs
import java.io.File
import java.security.MessageDigest
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

@Composable
fun InkuApp() {
    val viewModel: InkuViewModel = androidx.lifecycle.viewmodel.compose.viewModel()
    val state by viewModel.state.collectAsState()
    val history by viewModel.historyItems.collectAsState()

    MaterialTheme(colorScheme = InkuColors) {
        Scaffold(
            topBar = { AppHeader(state) },
            bottomBar = { HistoryStrip(history, state.selectedHistory, viewModel) },
            containerColor = MaterialTheme.colorScheme.background,
        ) { padding ->
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .background(MaterialTheme.colorScheme.background),
            ) {
                ModeTabs(state.tab, viewModel)
                Workbench(state, history, viewModel)
            }
        }
    }
}

@Composable
private fun AppHeader(state: InkuUiState) {
    Surface(modifier = Modifier.statusBarsPadding(), color = Color(0xFF151412), tonalElevation = 2.dp) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("inku", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Medium)
            Spacer(Modifier.weight(1f))
            Text(
                "色カタログ ${ColorCatalogs.get(state.selectedCatalogId).name}   キャンバス ${state.selectedCanvasAspect}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun ModeTabs(selected: AppTab, viewModel: InkuViewModel) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        AppTab.entries.forEach { tab ->
            val active = selected == tab
            val colors = if (active) {
                ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary, contentColor = Color(0xFF19150F))
            } else {
                ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (active) {
                Button(
                    onClick = { viewModel.setTab(tab) },
                    shape = RoundedCornerShape(4.dp),
                    colors = colors,
                ) { Text(tab.name) }
            } else {
                OutlinedButton(
                    onClick = { viewModel.setTab(tab) },
                    shape = RoundedCornerShape(4.dp),
                    colors = colors,
                ) { Text(tab.name) }
            }
        }
    }
}

@Composable
private fun Workbench(state: InkuUiState, history: List<HistoryItemEntity>, viewModel: InkuViewModel) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        PanelContainer(modifier = Modifier.fillMaxWidth().weight(0.45f)) {
            when (state.tab) {
                AppTab.Draw -> DrawPanel(state, viewModel)
                AppTab.Batch -> BatchPanel(state, viewModel)
                AppTab.Demo -> DemoPanel(state, viewModel)
                AppTab.History -> HistoryPanel(state, history, viewModel)
                AppTab.Settings -> SettingsPanel(state, viewModel)
            }
        }
        CanvasPanel(state, viewModel, modifier = Modifier.fillMaxWidth().weight(0.55f))
    }
}

@Composable
private fun PanelContainer(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Surface(
        modifier = modifier.border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(6.dp)),
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(6.dp),
    ) {
        Box(modifier = Modifier.padding(10.dp)) {
            content()
        }
    }
}

@Composable
private fun DrawPanel(state: InkuUiState, viewModel: InkuViewModel) {
    Column(
        modifier = Modifier.verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        CompactLabel("指示")
        OutlinedTextField(
            value = state.prompt,
            onValueChange = viewModel::setPrompt,
            modifier = Modifier.fillMaxWidth(),
            minLines = 3,
            maxLines = 4,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            PrimarySmallButton(text = if (state.isDrawing) "描画中" else "描画する", onClick = viewModel::draw, enabled = !state.isDrawing, modifier = Modifier.weight(1f))
            SecondarySmallButton(text = "DDLから描画", onClick = viewModel::drawFromDdl, enabled = !state.isDrawing, modifier = Modifier.weight(1f))
        }
        CompactLabel("解釈（正規化DDL）")
        OutlinedTextField(
            value = state.ddl,
            onValueChange = viewModel::setDdl,
            modifier = Modifier.fillMaxWidth(),
            minLines = 3,
            maxLines = 5,
        )
    }
}

@Composable
private fun BatchPanel(state: InkuUiState, viewModel: InkuViewModel) {
    Column(
        modifier = Modifier.verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        CompactLabel("バッチ")
        OutlinedTextField(
            value = state.batchText,
            onValueChange = viewModel::setBatchText,
            modifier = Modifier.fillMaxWidth(),
            minLines = 6,
            maxLines = 8,
        )
        PrimarySmallButton(text = if (state.isDrawing) "実行中" else "バッチ描画", onClick = viewModel::runBatch, enabled = !state.isDrawing)
        state.message?.let { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable
private fun DemoPanel(state: InkuUiState, viewModel: InkuViewModel) {
    Column(
        modifier = Modifier.verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        CompactLabel("デモ")
        OutlinedTextField(
            value = state.demoSeed,
            onValueChange = viewModel::setDemoSeed,
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )
        Text("interval ${state.demoIntervalSeconds}s / save current result manually", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        PrimarySmallButton(text = if (state.isDrawing) "描画中" else "1回描画", onClick = viewModel::runDemoOnce, enabled = !state.isDrawing)
        state.message?.let { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable
private fun HistoryPanel(state: InkuUiState, history: List<HistoryItemEntity>, viewModel: InkuViewModel) {
    val context = LocalContext.current
    var exportMessage by remember { mutableStateOf<String?>(null) }
    Column(
        modifier = Modifier.verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        CompactLabel("履歴 ${history.size}")
        history.firstOrNull()?.let { latest ->
            Text(
                "最新 F${latest.renderHashShort} / ${latest.canvasAspect}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        state.selectedHistory?.let { item ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SecondarySmallButton(text = if (item.starred) "Star解除" else "Star", onClick = { viewModel.toggleStar(item) }, modifier = Modifier.weight(1f))
                SecondarySmallButton(text = "Trash", onClick = { viewModel.trash(item) }, modifier = Modifier.weight(1f))
                PrimarySmallButton(
                    text = "JSON共有",
                    onClick = {
                        exportMessage = runCatching {
                            shareHistoryJson(context, item)
                            "Exported F${item.renderHashShort}"
                        }.getOrElse { error ->
                            error.message ?: "Export failed."
                        }
                    },
                    modifier = Modifier.weight(1f),
                )
            }
        }
        exportMessage?.let { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall) }
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(history, key = { it.id }) { item ->
                HistoryTile(item = item, selected = state.selectedHistory?.id == item.id, onSelect = { viewModel.selectHistory(item) })
            }
        }
    }
}

@Composable
private fun SettingsPanel(state: InkuUiState, viewModel: InkuViewModel) {
    Column(
        modifier = Modifier.verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            listOf("モデル設定", "プラグイン", "ログ保存", "エクスポート", "その他").forEachIndexed { index, label ->
                val active = index == 0
                if (active) PrimarySmallButton(text = label, onClick = {}) else SecondarySmallButton(text = label, onClick = {})
            }
        }
        SettingsCard(
            "選択",
            "描画条件をボタンで切り替え",
            "${selectedModelLabel(state)} / ${ColorCatalogs.get(state.selectedCatalogId).name} / ${CanvasAspects.all.firstOrNull { it.id == state.selectedCanvasAspect }?.label ?: state.selectedCanvasAspect}",
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                CompactLabel("モデル")
                HorizontalChoiceRow(
                    values = state.modelAssets.map { it.modelId to "${it.displayName} ${it.qualityTier}" },
                    selectedValue = state.selectedModelId,
                    onSelect = viewModel::setSelectedModel,
                )
                CompactLabel("色カタログ")
                ColorCatalogButtonRow(state.selectedCatalogId, viewModel::setCatalog)
                CompactLabel("キャンバス")
                HorizontalChoiceRow(
                    values = CanvasAspects.all.map { it.id to it.label },
                    selectedValue = state.selectedCanvasAspect,
                    onSelect = viewModel::setCanvasAspect,
                )
            }
        }
        SettingsCard("LiteRT-LM / Local", "Gemma 4 E2B 標準 / Gemma 4 E4B 高品質", "状態: ${state.modelDownloadState}") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                val downloadInProgress = state.modelAssets.any { asset ->
                    asset.downloadState in setOf("queued", "connecting", "downloading", "verifying")
                }
                state.modelAssets.forEach { asset ->
                    ModelAssetControls(
                        asset = asset,
                        active = asset.modelId == state.selectedModelId,
                        onSelect = { viewModel.setSelectedModel(asset.modelId) },
                        onAccept = { viewModel.acceptModelLicense(asset.modelId) },
                        onDownload = { viewModel.downloadModel(asset.modelId) },
                    )
                }
                SecondarySmallButton(text = "取得中断", onClick = viewModel::cancelModelDownload, enabled = downloadInProgress)
                state.message?.let {
                    Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

@Composable
private fun SettingsCard(title: String, sub: String, status: String, actions: @Composable () -> Unit) {
    Card(
        shape = RoundedCornerShape(4.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
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
    active: Boolean,
    onSelect: () -> Unit,
    onAccept: () -> Unit,
    onDownload: () -> Unit,
) {
    val isReady = asset.downloadState == "ready"
    val isBusy = asset.downloadState in setOf("queued", "connecting", "downloading", "verifying")
    val progress = if (asset.bytesTotal != null && asset.bytesTotal > 0L) {
        val percent = (asset.bytesDownloaded * 100.0 / asset.bytesTotal).coerceIn(0.0, 100.0)
        " ${"%.1f".format(percent)}%"
    } else {
        ""
    }
    val path = asset.localPath?.substringAfterLast("/") ?: "not stored"
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, if (active) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.outline, RoundedCornerShape(4.dp))
            .padding(8.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(asset.displayName, style = MaterialTheme.typography.titleSmall)
            Spacer(Modifier.weight(1f))
            Text(asset.qualityTier, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Text(
            "${asset.downloadState}$progress / $path",
            style = MaterialTheme.typography.labelSmall,
            color = if (active) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SecondarySmallButton(text = if (active) "選択中" else "選択", onClick = onSelect, modifier = Modifier.weight(1f))
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

@Composable
private fun HorizontalChoiceRow(
    values: List<Pair<String, String>>,
    selectedValue: String,
    onSelect: (String) -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
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
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        ColorCatalogs.all.forEach { catalog ->
            val selected = catalog.id == selectedValue
            OutlinedButton(
                onClick = { onSelect(catalog.id) },
                modifier = Modifier.height(54.dp),
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
    return state.modelAssets.firstOrNull { it.modelId == state.selectedModelId }?.displayName
        ?: state.selectedModelId.substringAfterLast(":")
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
                val modelLabel = selectedModelLabel(state)
                Text(state.message ?: "LLM Stage1 $modelLabel | Stage2 $modelLabel", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
    return buildString {
        appendLine("JSON Score:")
        appendLine(JSONObject(item.scoreJson).toString(2))
        appendLine()
        appendLine("render metadata:")
        appendLine(JSONObject(item.renderMetadataJson).toString(2))
    }
}

private fun shareHistoryJson(context: Context, item: HistoryItemEntity) {
    val exportDir = File(context.cacheDir, "exports")
    exportDir.mkdirs()
    val file = File(exportDir, "inku-${item.renderHashShort}.json")
    file.writeText(historyExportJson(item).toString(2), Charsets.UTF_8)
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "application/json"
        putExtra(Intent.EXTRA_SUBJECT, "inku ${item.renderHashShort}")
        putExtra(Intent.EXTRA_STREAM, uri)
        clipData = ClipData.newUri(context.contentResolver, "inku-${item.renderHashShort}.json", uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(intent, "Export inku JSON"))
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

@Composable
private fun HistoryStrip(history: List<HistoryItemEntity>, selected: HistoryItemEntity?, viewModel: InkuViewModel) {
    Surface(modifier = Modifier.navigationBarsPadding(), color = Color(0xFF151412), tonalElevation = 2.dp) {
        Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("履歴 (${history.size})", style = MaterialTheme.typography.labelMedium)
                Spacer(Modifier.weight(1f))
                selected?.let { Text(it.renderHashShort, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.secondary) }
            }
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(history.take(20), key = { it.id }) { item ->
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
            ArtworkPreview(item, modifier = Modifier.fillMaxWidth().height(52.dp))
            Text(item.elapsedMs?.let { "${it / 1000.0}s" } ?: item.renderHashShort, style = MaterialTheme.typography.labelSmall, maxLines = 1)
            Text(item.renderHashShort, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
        }
    }
}

@Composable
private fun CompactLabel(text: String) {
    Text(text, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
    Surface(color = Color.White, shape = RoundedCornerShape(2.dp), modifier = modifier) {
        Canvas(modifier = Modifier.fillMaxSize().padding(2.dp)) {
            val score = JSONObject(item.scoreJson)
            val catalog = ColorCatalogs.get(item.colorCatalogId)
            val background = parseColor(catalog.map[score.optString("background", "white")] ?: "#ffffff")
            drawRect(background)
            val instructions = score.optJSONArray("instructions") ?: return@Canvas
            val side = minOf(size.width, size.height)
            val offsetX = (size.width - side) / 2f
            val offsetY = (size.height - side) / 2f
            for (i in 0 until instructions.length()) {
                val instruction = instructions.optJSONObject(i) ?: continue
                expandPreview(instruction).forEach { mark ->
                    val color = parseColor(catalog.map[mark.optString("color", "black")] ?: "#111111")
                    val stroke = Stroke(width = strokeWidthPx(mark.optString("weight", "pen")))
                    when (mark.optString("primitive", "line")) {
                        "line" -> drawPreviewLine(mark, color, stroke.width, offsetX, offsetY, side)
                        "square" -> drawPreviewSquare(mark, color, stroke, offsetX, offsetY, side)
                        else -> drawPreviewCircle(mark, color, stroke, offsetX, offsetY, side)
                    }
                }
            }
        }
    }
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

private fun hash01(index: Int, seed: String): Double {
    val digest = MessageDigest.getInstance("SHA-256").digest("$seed:$index".toByteArray())
    val raw = ((digest[0].toInt() and 0xff) shl 24) or ((digest[1].toInt() and 0xff) shl 16) or ((digest[2].toInt() and 0xff) shl 8) or (digest[3].toInt() and 0xff)
    return (raw.toLong() and 0xffffffffL).toDouble() / 0xffffffffL.toDouble()
}
