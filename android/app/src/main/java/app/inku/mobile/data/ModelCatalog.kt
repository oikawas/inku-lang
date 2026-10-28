package app.inku.mobile.data

import android.content.Context
import app.inku.mobile.pipeline.NativePipelineBridge
import java.util.concurrent.ConcurrentHashMap
import org.json.JSONArray
import org.json.JSONObject

data class ModelCatalogLabel(val id: String, val ja: String, val en: String, val publishable: Boolean) {
    fun name(english: Boolean): String = if (english) en else ja
}

data class CatalogModel(
    val id: String,
    val record: JSONObject,
    val labels: List<ModelCatalogLabel>,
    val selection: JSONObject,
    val fold: String?,
) {
    val publishable: Boolean get() = !selection.getBoolean("unselectable")
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
    private val info by lazy { catalogRequest("catalog") }
    private val storedKeys by lazy { info.getJSONObject("stored_label_keys") }
    private val cache = ConcurrentHashMap<String, CatalogModel>()
    val labels: List<ModelCatalogLabel> by lazy { (this.source.optJSONArray("labels") ?: info.getJSONObject("catalog").getJSONArray("labels")).let { rows ->
        (0 until rows.length()).map { index -> rows.getJSONObject(index).let {
            ModelCatalogLabel(it.getString("id"), it.getString("ja"), it.getString("en"), it.getBoolean("publishable"))
        } }
    } }

    init {
        val providers = this.source.optJSONObject("providers")
        val models = JSONArray()
        val originals = mutableMapOf<String, Pair<String, JSONObject>>()
        providers?.keys()?.forEach { providerId ->
            val rows = providers.getJSONObject(providerId).optJSONArray("models") ?: JSONArray()
            for (index in 0 until rows.length()) {
                val record = withObservations(rows.getJSONObject(index), null, null)
                val marker = "$providerId\u0000${record.getString("id")}"
                originals[marker] = providerId to record
                models.put(internalRecord(record).put("_android_catalog_key", marker))
            }
        }
        if (models.length() > 0) {
            val sorted = catalogRequest("sort", JSONObject().put("models", models)).getJSONArray("models")
            for (index in 0 until sorted.length()) {
                val result = sorted.getJSONObject(index)
                val (provider, record) = originals.getValue(result.getString("_android_catalog_key"))
                cache[cacheKey(provider, record)] = model(record, result)
            }
        }
    }

    fun defaults(providerId: String): List<String> = provider(providerId)?.optJSONArray("defaults").strings()
    fun ids(providerId: String): List<String> = provider(providerId)?.optJSONArray("models")?.let { rows ->
        (0 until rows.length()).map { rows.getJSONObject(it).getString("id") }
    }.orEmpty()

    fun resolve(providerId: String, modelId: String, offered: Set<String>? = null, accessible: Boolean? = null): CatalogModel {
        val id = rawId(providerId, modelId)
        val rows = provider(providerId)?.optJSONArray("models")
        val original = rows?.let { (0 until it.length()).map(it::getJSONObject).firstOrNull { row -> row.getString("id") == id } }
        val record = original?.let { JSONObject(it.toString()) } ?: JSONObject().put("id", id)
        val observed = withObservations(record, offered, accessible)
        return cached(providerId, observed)
    }

    private fun withObservations(input: JSONObject, offered: Set<String>?, accessible: Boolean?): JSONObject {
        val record = JSONObject(input.toString())
        val id = record.optString("id")
        val stored = record.optJSONArray("labels").strings().toMutableSet()
        offered?.let { if (id in it) stored.remove("eol") else stored.add("eol") }
        accessible?.let { if (it) stored.remove("subscription") else stored.add("subscription") }
        record.put("labels", JSONArray(stored.toList()))
        return record
    }

    fun classify(record: JSONObject): CatalogModel = cached("", JSONObject(record.toString()))

    private fun cached(providerId: String, record: JSONObject): CatalogModel =
        cache.computeIfAbsent(cacheKey(providerId, record)) {
            model(record, catalogRequest("label", JSONObject().put("model", internalRecord(record))).getJSONObject("model"))
        }

    private fun cacheKey(providerId: String, record: JSONObject) = "$providerId\u0000${record.optString("id")}\u0000$record"

    /** Translate stored label names to the core's input fields; the catalog supplies this mapping. */
    private fun internalRecord(record: JSONObject): JSONObject {
        val input = JSONObject(record.toString())
        input.optJSONArray("labels").strings().forEach { label ->
            if (storedKeys.has(label)) input.put(storedKeys.getString(label), true)
        }
        input.remove("labels")
        return input
    }

    private fun model(record: JSONObject, result: JSONObject): CatalogModel {
        val ids = result.getJSONArray("labels").strings().toSet()
        return CatalogModel(record.optString("id"), JSONObject(record.toString()), labels.filter { it.id in ids },
            JSONObject(result.getJSONObject("selection").toString()),
            if (result.isNull("fold")) null else result.getString("fold"))
    }

    private fun provider(id: String): JSONObject? = source.optJSONObject("providers")?.optJSONObject(id)

    companion object {
        val EMPTY = ModelCatalog(JSONObject())
        fun load(@Suppress("UNUSED_PARAMETER") context: Context): ModelCatalog {
            val source = catalogRequest("catalog").getJSONObject("catalog")
            require(source.getString("schema") == "inku.model-catalog.v2")
            return ModelCatalog(source)
        }
        fun rawId(providerId: String, id: String): String = id.removePrefix("$providerId:").removePrefix("models/")
    }
}

internal fun catalogRequest(action: String, fields: JSONObject = JSONObject()): JSONObject {
    val request = JSONObject(fields.toString()).put("schema", "inku.model-catalog-request.v1").put("action", action)
    val answer = JSONObject(NativePipelineBridge.modelCatalog(request.toString().toByteArray()).toString(Charsets.UTF_8))
    require(answer.optString("schema") == "inku.model-catalog.v1" && answer.optString("outcome") == "ok") { "model_catalog_request_failed" }
    return answer
}

internal fun JSONArray?.strings(): List<String> = if (this == null) emptyList() else (0 until length()).map { getString(it) }
