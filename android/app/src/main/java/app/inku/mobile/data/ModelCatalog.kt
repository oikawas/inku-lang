package app.inku.mobile.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

data class ModelCatalogLabel(val id: String, val ja: String, val en: String, val publishable: Boolean) {
    fun name(english: Boolean): String = if (english) en else ja
}

data class CatalogModel(
    val id: String,
    val record: JSONObject,
    val labels: List<ModelCatalogLabel>,
) {
    val fold: String? get() = labels.lastOrNull()?.id
    val publishable: Boolean get() = labels.all { it.publishable }
    val name: String get() = record.optString("label").ifBlank { id }
}

data class ModelCatalogObservation(val seen: List<String> = emptyList(), val access: Map<String, Boolean> = emptyMap()) {
    companion object {
        fun read(json: String?): ModelCatalogObservation = runCatching {
            val value = JSONObject(json ?: "{}")
            val access = value.optJSONObject("access") ?: JSONObject()
            ModelCatalogObservation(value.optJSONArray("seen").strings(), access.keys().asSequence().associateWith(access::getBoolean))
        }.getOrDefault(ModelCatalogObservation())
    }
    fun json(): String = JSONObject().put("seen", JSONArray(seen)).put("access", JSONObject(access)).toString()
}

/** Read-only repository catalog; local observations are applied to a fresh record. */
class ModelCatalog(source: JSONObject) {
    private val source = JSONObject(source.toString())
    val labels: List<ModelCatalogLabel> = this.source.optJSONArray("labels")?.let { rows ->
        (0 until rows.length()).map { index -> rows.getJSONObject(index).let {
            ModelCatalogLabel(it.getString("id"), it.getString("ja"), it.getString("en"), it.getBoolean("publishable"))
        } }
    }.orEmpty()

    fun defaults(providerId: String): List<String> = provider(providerId)?.optJSONArray("defaults").strings()
    fun ids(providerId: String): List<String> = provider(providerId)?.optJSONArray("models")?.let { rows ->
        (0 until rows.length()).map { rows.getJSONObject(it).getString("id") }
    }.orEmpty()

    fun resolve(providerId: String, modelId: String, offered: Set<String>? = null, accessible: Boolean? = null): CatalogModel {
        val id = rawId(providerId, modelId)
        val rows = provider(providerId)?.optJSONArray("models")
        val original = rows?.let { (0 until it.length()).map(it::getJSONObject).firstOrNull { row -> row.getString("id") == id } }
        val record = original?.let { JSONObject(it.toString()) } ?: JSONObject().put("id", id)
        val stored = record.optJSONArray("labels").strings().toMutableSet()
        offered?.let { if (id in it) stored.remove("eol") else stored.add("eol") }
        accessible?.let { if (it) stored.remove("subscription") else stored.add("subscription") }
        record.put("labels", JSONArray(stored.toList()))
        return classify(record)
    }

    fun classify(record: JSONObject): CatalogModel {
        val keys = record.optJSONArray("labels").strings().toMutableSet()
        // Server `model_labels`: no purpose it is offered for is one it answered when measured.
        val unsupported = record.optJSONArray("unsupported_purposes").strings()
        val purposes = if (record.has("purposes")) record.optJSONArray("purposes").strings() else listOf("llm")
        if (purposes.none { it !in unsupported }) keys += "no_response"
        if (MEASUREMENT_KEYS.none(record::has) && labels.filter { it.id in keys }.all { it.publishable }) keys += "unmeasured"
        return CatalogModel(record.optString("id"), JSONObject(record.toString()), labels.filter { it.id in keys })
    }

    private fun provider(id: String): JSONObject? = source.optJSONObject("providers")?.optJSONObject(id)

    companion object {
        val EMPTY = ModelCatalog(JSONObject())
        fun load(context: Context): ModelCatalog = context.assets.open("model_catalog.json").bufferedReader().use {
            val source = JSONObject(it.readText())
            require(source.getString("schema") == "inku.model-catalog.v2")
            ModelCatalog(source)
        }
        fun rawId(providerId: String, id: String): String = id.removePrefix("$providerId:").removePrefix("models/")
        private val MEASUREMENT_KEYS = listOf(
            "recommendation_llm", "recommendation_vision", "recommendation_stage1", "recommendation_stage2",
            "recommendation_level", "speed_class", "speed_label", "speed_llm_seconds", "speed_vision_seconds",
            "cost_usd_llm", "cost_usd_vision", "comment_ja", "comment_en", "unsupported_purposes",
        )
    }
}

internal fun JSONArray?.strings(): List<String> = if (this == null) emptyList() else (0 until length()).map { getString(it) }
