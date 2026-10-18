package app.inku.mobile.ui

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.ui.ddl3d.Ddl3DController
import app.inku.mobile.ui.ddl3d.Ddl3DInitialView
import app.inku.mobile.ui.ddl3d.Ddl3DInput
import app.inku.mobile.ui.ddl3d.Ddl3DInstallation
import app.inku.mobile.ui.ddl3d.Ddl3DWebHost
import app.inku.mobile.ui.theme.Dimens
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private val S: app.inku.mobile.ui.i18n.InkuStrings
    @Composable @androidx.compose.runtime.ReadOnlyComposable get() = app.inku.mobile.ui.i18n.LocalStrings.current

/** The registration in the app's copy of the viewer, read once; null hides the 3D switch. */
private var ddl3dRegistration: Ddl3DInstallation.Registered? = null
private var ddl3dRegistrationRead = false

internal fun ddl3dRegistration(context: Context): Ddl3DInstallation.Registered? {
    if (!ddl3dRegistrationRead) {
        ddl3dRegistration = Ddl3DInstallation.registration { path ->
            runCatching { context.assets.open(path).use { it.readBytes() } }.getOrNull()
        }
        ddl3dRegistrationRead = true
    }
    return ddl3dRegistration
}

/**
 * The work in the experimental 3D view, in place of the 2D canvas. While it is
 * preparing it says so with a way back to 2D; when it fails it says so with the
 * reason under Details, Retry and Return to 2D (Web `Ddl3DHost.svelte`).
 */
@Composable
internal fun Ddl3DCanvas(
    item: HistoryItemEntity,
    registered: Ddl3DInstallation.Registered,
    controller: Ddl3DController,
    english: Boolean,
    onReturn: () -> Unit,
    onMessage: (String) -> Unit,
    modifier: Modifier = Modifier,
    pictureRatio: Float? = null,
    zoom: Float = 1f,
    panX: Float = 0f,
    panY: Float = 0f,
    clearTopInset: Boolean = false,
) {
    val context = LocalContext.current
    val density = LocalDensity.current.density
    // In the full screen the frame reaches under the status bar and the camera,
    // where the viewer's own "3D controls" button sat on the clock. The viewer
    // starts below them; the band above shows the full screen's background.
    val topInset = if (clearTopInset) WindowInsets.safeDrawing.getTop(LocalDensity.current) else 0
    val title = S.ddl3dTitle
    val shareFailed = S.ddl3dShareFailed
    val currentReturn by rememberUpdatedState(onReturn)
    val currentMessage by rememberUpdatedState(onMessage)
    val host = remember(registered, controller) {
        Ddl3DWebHost(context, registered, title, controller) { currentMessage(shareFailed) }
    }
    DisposableEffect(host) {
        controller.onReturn = { currentReturn() }
        controller.mount(host)
        onDispose { host.close() }
    }
    LaunchedEffect(host, item.id, item.scoreJson, item.renderMetadataJson, english) {
        val input = withContext(Dispatchers.Default) { Ddl3DInput.snapshot(item) }
        controller.update(input, if (english) "en" else "ja")
    }
    Box(modifier.onSizeChanged {
        // The first front view is the picture as the 2D canvas showed it, so the
        // button seems to give that picture depth where it stands (Web
        // `initialView`). A picture the full screen turned on its side has no
        // such view, and the viewer fits it by itself.
        // The 2D picture is centred in the whole frame and the viewer's middle is
        // half the inset lower, so the picture is moved up by that half.
        controller.initialView = pictureRatio?.takeIf { r -> r > 0f }?.let { r ->
            Ddl3DInitialView.ofPicture(it.width / density.toDouble(), it.height / density.toDouble(), r.toDouble(),
                zoom.toDouble(), panX / density.toDouble(), (panY - topInset / 2f) / density.toDouble())
        }
    }) {
        AndroidView(factory = { host.webView }, modifier = Modifier.fillMaxSize().padding(top = (topInset / density).dp))
        val failure = controller.failure
        if (failure != null) {
            var details by remember(failure) { mutableStateOf(false) }
            Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                Column(
                    modifier = Modifier.fillMaxSize().padding(Dimens.spaceXl).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(Dimens.spaceM, Alignment.CenterVertically),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(S.ddl3dFailed, textAlign = TextAlign.Center, style = MaterialTheme.typography.bodyMedium)
                    TextButton(onClick = { details = !details }) { Text(S.ddl3dDetails) }
                    if (details) Text(failure, style = MaterialTheme.typography.labelSmall, fontFamily = FontFamily.Monospace)
                    Row(horizontalArrangement = Arrangement.spacedBy(Dimens.spaceM)) {
                        TextButton(onClick = controller::retry) { Text(S.ddl3dRetry) }
                        TextButton(onClick = onReturn) { Text(S.ddl3dReturn) }
                    }
                }
            }
        } else if (controller.preparing) {
            Surface(
                modifier = Modifier.align(Alignment.TopStart).padding(Dimens.spaceM),
                shape = RoundedCornerShape(Dimens.spaceXs),
                color = MaterialTheme.colorScheme.background,
            ) {
                Row(modifier = Modifier.padding(start = Dimens.spaceM), verticalAlignment = Alignment.CenterVertically) {
                    Text(S.ddl3dPreparing, style = MaterialTheme.typography.labelMedium)
                    TextButton(onClick = onReturn) { Text(S.ddl3dReturn) }
                }
            }
        }
    }
}

/** The viewer's own notices file, read from the app's copy when asked for, so no version name is baked in. */
@Composable
internal fun Ddl3DNoticesDialog(registered: Ddl3DInstallation.Registered, onDismiss: () -> Unit) {
    val context = LocalContext.current
    var text by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(registered) {
        text = withContext(Dispatchers.IO) {
            runCatching {
                context.assets.open("${Ddl3DInstallation.ASSET_ROOT}/${registered.build}/THIRD_PARTY_NOTICES.txt")
                    .use { it.readBytes().toString(Charsets.UTF_8) }
            }.getOrDefault("")
        }
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(S.ddl3dNotices) },
        text = {
            Text(
                text ?: "…",
                modifier = Modifier.verticalScroll(rememberScrollState()),
                style = MaterialTheme.typography.labelSmall,
                fontFamily = FontFamily.Monospace,
            )
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text(S.close) } },
    )
}
