package app.inku.mobile.llm

import app.inku.mobile.pipeline.CoreIdentityJson
import app.inku.mobile.pipeline.NativePipelineBridge
import org.json.JSONObject

/** JNI transport; the shared core owns the rate decisions. */
internal object SharedProviderAdmission {
    fun call(request: JSONObject): JSONObject = JSONObject(
        NativePipelineBridge.providerAdmission(CoreIdentityJson.encode(request).toByteArray(Charsets.UTF_8))
            .toString(Charsets.UTF_8),
    )
}
