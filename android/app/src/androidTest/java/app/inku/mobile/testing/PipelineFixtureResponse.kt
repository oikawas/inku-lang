package app.inku.mobile.testing

import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import org.json.JSONObject

/**
 * What a stand-in model answers the shared pipeline.
 *
 * The pipeline asks for a structured answer through one tool: Stage 1 for
 * `normalized_ddl`, 写生 for `sketch`. The stand-ins these tests used before
 * the shared pipeline echoed the prompt back as text, which the pipeline
 * refuses as a malformed answer, so every drawing stopped at 「DDLと描画の診断を
 * 確認してください。」 and nothing was ever saved. A request with no tool (the
 * demo's instruction) still gets its prompt back.
 *
 * The DDL is picked from the prompt, so two descriptions usually draw two
 * pictures, as the echo did, and it is written in the prompt's language, which
 * is the language the run was configured to read.
 */
internal fun pipelineFixtureResponse(request: ModelRequest): ModelResponse {
    val tool = request.tool ?: return ModelResponse(text = request.prompt, modelId = request.modelId)
    val answer = if (tool.parametersJson.contains("\"sketch\"")) {
        JSONObject().put("sketch", "夕方の光の中、静かな場面。")
    } else {
        JSONObject().put("normalized_ddl", fixtureDdl(request))
    }
    return ModelResponse(text = answer.toString(), modelId = request.modelId)
}

internal fun fixtureDdl(request: ModelRequest): String {
    val hash = request.prompt.hashCode()
    val colorIndex = Math.floorMod(hash, JA_COLORS.size)
    val placeIndex = Math.floorMod(hash / JA_COLORS.size, JA_PLACES.size)
    val japanese = (request.systemInstruction.orEmpty() + request.prompt).any { it in '぀'..'ヿ' || it in '一'..'鿿' }
    return if (japanese) {
        "${JA_PLACES[placeIndex]}に${JA_COLORS[colorIndex]}の円を1個置く。"
    } else {
        "place one ${EN_COLORS[colorIndex]} circle at ${EN_PLACES[placeIndex]}."
    }
}

private val JA_COLORS = listOf("黒", "赤", "青", "緑", "黄", "紫")
private val EN_COLORS = listOf("black", "red", "blue", "green", "yellow", "purple")
private val JA_PLACES = listOf("中心", "上", "下")
private val EN_PLACES = listOf("center", "top", "bottom")
