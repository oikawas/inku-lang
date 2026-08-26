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
import androidx.compose.runtime.getValue
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

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            val application = application as InkuApplication
            var startupResult by remember { mutableStateOf(application.prepareDatabase()) }

            when (startupResult) {
                is RoomV10ResetCoordinator.Result.Ready -> InkuApp()
                is RoomV10ResetCoordinator.Result.Refused -> DatabaseStartupRefusedScreen(
                    onRetry = { startupResult = application.prepareDatabase() },
                )
            }
        }
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
