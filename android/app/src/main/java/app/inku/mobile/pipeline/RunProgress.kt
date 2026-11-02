package app.inku.mobile.pipeline

import org.json.JSONObject

data class ProgressUsage(val input: Long? = null, val output: Long? = null, val unreportedSends: Int = 0) {
    fun add(input: Int?, output: Int?): ProgressUsage = ProgressUsage(
        input = input?.let { (this.input ?: 0) + it } ?: this.input,
        output = output?.let { (this.output ?: 0) + it } ?: this.output,
        unreportedSends = unreportedSends + if (input == null && output == null) 1 else 0,
    )
}

data class ProgressItem(val action: String, val outcome: String, val facts: JSONObject)
data class ProgressCurrent(val kind: String, val action: String)
data class RunProgress(
    val executionId: String,
    val current: ProgressCurrent?,
    val finished: List<ProgressItem>,
    val stageTokens: Map<String, ProgressUsage>,
    val total: ProgressUsage,
    val receivedBytes: Long?,
)

internal class ProgressTracker(private val executionId: String) {
    private var current: ProgressCurrent? = null
    private var finished: List<ProgressItem>? = null
    private val stages = mutableMapOf<String, ProgressUsage>()
    private var total = ProgressUsage()
    private var received: Long? = null

    @Synchronized fun update(report: ByteArray) {
        val value = JSONObject(report.toString(Charsets.UTF_8)).optJSONObject("run_progress")
        if (value == null) { finished = null; current = null; return }
        current = value.optJSONObject("current")?.let { ProgressCurrent(it.getString("kind"), it.getString("action")) }
        val items = value.getJSONArray("finished")
        finished = (0 until items.length()).map { index ->
            val item = items.getJSONObject(index)
            ProgressItem(item.getString("action"), item.getString("outcome"), item.optJSONObject("facts") ?: JSONObject())
        }
    }
    @Synchronized fun render() { current = ProgressCurrent("local", "render") }
    @Synchronized fun unavailable() { current = null; finished = null }
    @Synchronized fun usage(action: String, input: Int?, output: Int?) {
        stages[action] = (stages[action] ?: ProgressUsage()).add(input, output)
        total = total.add(input, output)
    }
    @Synchronized fun received(bytes: Long?) { received = bytes }
    @Synchronized fun value(): RunProgress? = finished?.let {
        RunProgress(executionId, current, it.toList(), stages.toMap(),
            if (stages.isEmpty()) ProgressUsage(0, 0) else total, received)
    }
}
