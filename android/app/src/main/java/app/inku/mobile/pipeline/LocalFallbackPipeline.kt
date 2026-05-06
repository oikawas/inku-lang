package app.inku.mobile.pipeline

import app.inku.mobile.render.DefaultSvgRenderer
import java.util.UUID
import org.json.JSONArray
import org.json.JSONObject

class LocalFallbackPipeline(
    private val renderer: DefaultSvgRenderer = DefaultSvgRenderer(),
) {
    fun paint(request: PaintRequest): PaintResult {
        val normalizedDdl = normalizeDdl(request.description)
        val expandedDdl = expandDdl(normalizedDdl)
        val scoreJson = scoreFrom(expandedDdl, request.canvasAspect).toString()
        val render = renderer.render(
            RenderRequest(
                scoreJson = scoreJson,
                colorCatalogId = request.colorCatalogId,
                canvasAspect = request.canvasAspect,
                svgProfile = "display",
            ),
        )
        return PaintResult(
            originalInput = request.description,
            normalizedDdl = normalizedDdl,
            expandedDdl = expandedDdl,
            scoreJson = scoreJson,
            displaySvg = render.svg,
            renderMetadataJson = render.metadataJson,
            renderHash = render.renderHash,
            renderHashShort = render.renderHash.takeLast(4).uppercase(),
        )
    }

    fun composeFromDdl(ddl: String, request: PaintRequest): PaintResult {
        val expandedDdl = expandDdl(ddl)
        val scoreJson = scoreFrom(expandedDdl, request.canvasAspect).toString()
        val render = renderer.render(
            RenderRequest(
                scoreJson = scoreJson,
                colorCatalogId = request.colorCatalogId,
                canvasAspect = request.canvasAspect,
                svgProfile = "display",
            ),
        )
        return PaintResult(
            originalInput = request.description,
            normalizedDdl = ddl,
            expandedDdl = expandedDdl,
            scoreJson = scoreJson,
            displaySvg = render.svg,
            renderMetadataJson = render.metadataJson,
            renderHash = render.renderHash,
            renderHashShort = render.renderHash.takeLast(4).uppercase(),
        )
    }

    private fun normalizeDdl(text: String): String {
        val color = detectColor(text)
        val primitive = detectPrimitive(text)
        val count = detectCount(text)
        val touch = detectWeight(text)
        val motion = detectLayout(text)
        return "$color $touch $primitive を $count 個 $motion。"
    }

    private fun expandDdl(ddl: String): String {
        return if (ddl.contains("斜め") || ddl.contains("波") || ddl.contains("散ら")) {
            "$ddl 余白を残し、軌跡に沿って密度を変える。"
        } else {
            "$ddl 中央から少し外した焦点を保つ。"
        }
    }

    private fun scoreFrom(ddl: String, canvasAspect: String): JSONObject {
        val primitive = detectPrimitive(ddl)
        val color = detectColorKey(ddl)
        val weight = detectWeightKey(ddl)
        val count = detectCount(ddl).coerceIn(1, 80)
        val instruction = JSONObject()
            .put("primitive", primitive)
            .put("color", color)
            .put("weight", weight)
            .put("style", if (ddl.contains("破線")) "dashed" else if (ddl.contains("点線")) "dotted" else "solid")
            .put("filled", ddl.contains("塗"))
        when (primitive) {
            "line" -> {
                instruction.put("from", JSONArray(listOf(0.2, 0.25)))
                instruction.put("to", JSONArray(listOf(0.8, 0.75)))
            }
            "square", "triangle" -> {
                instruction.put("position", JSONArray(listOf(0.38, 0.36)))
                instruction.put("size", JSONArray(listOf(0.22, 0.22)))
            }
            "ellipse" -> {
                instruction.put("center", JSONArray(listOf(0.5, 0.5)))
                instruction.put("size", JSONArray(listOf(0.34, 0.2)))
            }
            "arc" -> {
                instruction.put("center", JSONArray(listOf(0.5, 0.5)))
                instruction.put("radius", 0.24)
                instruction.put("angle_start", 30)
                instruction.put("angle_end", 310)
            }
            "polygon" -> {
                instruction.put("center", JSONArray(listOf(0.5, 0.5)))
                instruction.put("radius", 0.16)
                instruction.put("sides", 5)
            }
            else -> {
                instruction.put("center", JSONArray(listOf(0.5, 0.5)))
                instruction.put("radius", 0.12)
            }
        }
        if (count > 1) {
            instruction.put(
                "arrangement",
                JSONObject()
                    .put("count", count)
                    .put("layout", detectLayoutKey(ddl))
                    .put("path", if (ddl.contains("波")) "wave" else if (ddl.contains("斜め")) "diagonal" else "none")
                    .put("margin", 0.12),
            )
        }
        return JSONObject()
            .put("version", "0.1.0")
            .put("canvas", canvasAspect)
            .put("background", if (ddl.contains("黒い背景")) "black" else "white")
            .put("instructions", JSONArray().put(instruction))
    }

    private fun detectPrimitive(text: String): String = when {
        text.contains("楕円") || text.contains("ellipse", ignoreCase = true) -> "ellipse"
        text.contains("三角") || text.contains("triangle", ignoreCase = true) -> "triangle"
        text.contains("四角") || text.contains("square", ignoreCase = true) -> "square"
        text.contains("多角") || text.contains("五角") || text.contains("polygon", ignoreCase = true) -> "polygon"
        text.contains("弧") || text.contains("円弧") || text.contains("arc", ignoreCase = true) -> "arc"
        text.contains("線") || text.contains("line", ignoreCase = true) -> "line"
        else -> "circle"
    }

    private fun detectColor(text: String): String = when (detectColorKey(text)) {
        "white" -> "白い"
        "blue" -> "青い"
        "red" -> "赤い"
        "green" -> "緑の"
        "gray" -> "灰色の"
        else -> "黒い"
    }

    private fun detectColorKey(text: String): String = when {
        text.contains("青") || text.contains("blue", ignoreCase = true) -> "blue"
        text.contains("赤") || text.contains("red", ignoreCase = true) -> "red"
        text.contains("緑") || text.contains("green", ignoreCase = true) -> "green"
        text.contains("灰") || text.contains("gray", ignoreCase = true) || text.contains("grey", ignoreCase = true) -> "gray"
        text.contains("白い") || text.contains("白の") || text.contains("白 ") || text.contains("white", ignoreCase = true) -> "white"
        else -> "black"
    }

    private fun detectWeight(text: String): String = when (detectWeightKey(text)) {
        "pencil" -> "鉛筆の"
        "brush_thick" -> "太筆の"
        "brush_thin" -> "細筆の"
        "crayon" -> "クレヨンの"
        "chalk" -> "チョークの"
        "rope" -> "縄の"
        "rotring" -> "ロットリングの"
        else -> "ペンの"
    }

    private fun detectWeightKey(text: String): String = when {
        text.contains("鉛筆") -> "pencil"
        text.contains("太筆") -> "brush_thick"
        text.contains("細筆") -> "brush_thin"
        text.contains("クレヨン") -> "crayon"
        text.contains("チョーク") -> "chalk"
        text.contains("縄") -> "rope"
        text.contains("ロットリング") -> "rotring"
        else -> "pen"
    }

    private fun detectCount(text: String): Int = when {
        Regex("""\d+""").find(text) != null -> Regex("""\d+""").find(text)?.value?.toIntOrNull() ?: 1
        text.contains("無数") || text.contains("たくさん") -> 48
        text.contains("三") || text.contains("3") -> 3
        text.contains("二") || text.contains("2") -> 2
        text.contains("五") || text.contains("5") -> 5
        text.contains("並") || text.contains("散ら") -> 12
        else -> 1
    }

    private fun detectLayout(text: String): String = when (detectLayoutKey(text)) {
        "vertical" -> "縦に並べる"
        "scatter" -> "散らす"
        "radial" -> "円環に並べる"
        else -> "横に並べる"
    }

    private fun detectLayoutKey(text: String): String = when {
        text.contains("縦") -> "vertical"
        text.contains("散ら") || text.contains("scatter", ignoreCase = true) -> "scatter"
        text.contains("円環") || text.contains("放射") -> "radial"
        else -> "horizontal"
    }

    fun newHistoryId(): String = UUID.randomUUID().toString()
}
