package app.inku.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import app.inku.mobile.data.db.RoomV10ResetCoordinator
import app.inku.mobile.ui.InkuApp
import app.inku.mobile.ui.theme.Dimens
import app.inku.mobile.ui.theme.InkuColors
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            val application = application as InkuApplication
            DatabaseStartupGate(
                prepare = application::prepareDatabase,
                alreadyOpen = application.databaseOpen,
            ) { InkuApp() }
        }
    }
}

/**
 * Opens the database before [content], off the main thread: the v10 reset
 * check and Room's migrations run inside [prepare]. Until it answers, only the
 * app's background is shown; a refusal shows [DatabaseStartupRefusedScreen],
 * whose retry prepares again in the same way. An activity recreated after the
 * database opened ([alreadyOpen]) goes straight to [content], so a
 * configuration change (theme, font scale) does not pass through the blank frame.
 */
@Composable
internal fun DatabaseStartupGate(
    prepare: () -> RoomV10ResetCoordinator.Result,
    alreadyOpen: Boolean = false,
    content: @Composable () -> Unit,
) {
    var attempt by remember { mutableIntStateOf(0) }
    var result by remember {
        mutableStateOf<RoomV10ResetCoordinator.Result?>(
            if (alreadyOpen) RoomV10ResetCoordinator.Result.Ready(resetPerformed = false) else null,
        )
    }
    LaunchedEffect(attempt) {
        if (result == null) result = withContext(Dispatchers.IO) { prepare() }
    }
    when (result) {
        null -> MaterialTheme(colorScheme = InkuColors) {
            Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {}
        }
        is RoomV10ResetCoordinator.Result.Ready -> content()
        is RoomV10ResetCoordinator.Result.Refused -> DatabaseStartupRefusedScreen(
            onRetry = {
                result = null
                attempt += 1
            },
        )
    }
}

@Composable
internal fun DatabaseStartupRefusedScreen(onRetry: () -> Unit) {
    MaterialTheme(colorScheme = InkuColors) {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = MaterialTheme.colorScheme.background,
        ) {
            Column(
                modifier = Modifier.padding(Dimens.databaseStartupPageInset),
                verticalArrangement = Arrangement.spacedBy(Dimens.databaseStartupGap, Alignment.CenterVertically),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    text = stringResource(R.string.database_startup_refused_title),
                    style = MaterialTheme.typography.headlineSmall,
                )
                Text(
                    text = stringResource(R.string.database_startup_refused_message),
                    style = MaterialTheme.typography.bodyLarge,
                )
                Button(onClick = onRetry) {
                    Text(stringResource(R.string.database_startup_retry))
                }
            }
        }
    }
}
