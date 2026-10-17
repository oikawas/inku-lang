package app.inku.mobile.llm

import app.inku.mobile.pipeline.CoreIdentityJson
import app.inku.mobile.pipeline.NativePipelineBridge
import app.inku.mobile.pipeline.SharedPipelineBinding
import org.json.JSONObject

/** JSON transport to the core; provider HTTP and secret injection stay with the host. */
internal object SharedProviderWire {
    const val SCHEMA = "inku.provider-wire.v1"

    fun call(request: JSONObject, binding: SharedPipelineBinding = NativePipelineBridge): JSONObject =
        call(CoreIdentityJson.encode(request), binding)

    /** Use this when the prompt carries a raw schema whose member order must survive. */
    fun call(requestJson: String, binding: SharedPipelineBinding = NativePipelineBridge): JSONObject {
        val answer = JSONObject(binding.providerWire(requestJson.encodeToByteArray())
            .toString(Charsets.UTF_8))
        if (answer.has("error")) throw IllegalStateException(answer.getString("error"))
        check(answer.optString("schema") == SCHEMA) { "provider wire schema mismatch" }
        return answer
    }
}
