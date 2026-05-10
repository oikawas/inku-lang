package app.inku.mobile.llm

import java.net.URL

object ProviderUrlValidator {
    fun validateRemoteBaseUrl(baseUrl: String) {
        val url = runCatching { URL(baseUrl) }.getOrElse {
            error("Base URLが正しいURLではありません。")
        }
        val protocol = url.protocol.lowercase()
        val host = url.host.orEmpty()
        val secure = protocol == "https"
        val loopbackHttp = protocol == "http" && isLoopbackHost(host)
        require(secure || loopbackHttp) {
            "安全でないBase URLです。HTTPS、または端末内localhost/127.0.0.1のHTTPのみ使用できます。"
        }
    }

    private fun isLoopbackHost(host: String): Boolean {
        val normalized = host.lowercase()
        return normalized == "localhost" ||
            normalized == "127.0.0.1" ||
            normalized == "::1" ||
            normalized == "[::1]"
    }
}
