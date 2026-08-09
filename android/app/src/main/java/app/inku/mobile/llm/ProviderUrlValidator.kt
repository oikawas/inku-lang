package app.inku.mobile.llm

import app.inku.mobile.ui.i18n.inkuError
import java.net.URL

object ProviderUrlValidator {
    fun validateRemoteBaseUrl(baseUrl: String) {
        val url = runCatching { URL(baseUrl) }.getOrElse { inkuError { s -> s.errorBaseUrlInvalid } }
        val protocol = url.protocol.lowercase()
        val host = url.host.orEmpty()
        val secure = protocol == "https"
        val loopbackHttp = protocol == "http" && isLoopbackHost(host)
        // `require` would raise an IllegalArgumentException carrying a fixed
        // string. The reader sees this one, so it has to be chosen when shown.
        if (!(secure || loopbackHttp)) inkuError { it.errorBaseUrlInsecure }
    }

    private fun isLoopbackHost(host: String): Boolean {
        val normalized = host.lowercase()
        return normalized == "localhost" ||
            normalized == "127.0.0.1" ||
            normalized == "::1" ||
            normalized == "[::1]"
    }
}
