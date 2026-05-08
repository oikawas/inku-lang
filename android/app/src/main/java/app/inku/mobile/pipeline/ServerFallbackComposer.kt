package app.inku.mobile.pipeline

import kotlin.math.min
import org.json.JSONArray
import org.json.JSONObject

internal object ServerFallbackComposer {
    fun fallbackDdlFromText(text: String): String {
        val background = if (text.containsAny("夜", "黒", "暗")) "黒" else "白"
        val foreground = if (background == "黒") "白" else "黒"
        val accent = if (foreground == "黒" && text.containsAny("白", "雪")) "青" else "灰色"
        return "背景を${background}で塗りつぶす。${foreground}い細い斜めの線を三本並べる。${accent}の小さな点を十二個、画面全体に点々と散らす。"
    }

    fun fallbackInstruction(text: String, color: String, weight: String): JSONObject {
        val lower = text.lowercase()
        val filled = text.contains("塗") || lower.contains("fill")
        val base = JSONObject()
            .put("color", color)
            .put("weight", weight)
            .put("filled", filled)
            .put("style", ServerScoreSemantics.styleKey(text))
            .put("color_hint", "fallback from DDL")
        return when {
            text.containsAny("多角形", "五角", "六角", "結晶", "鉱物", "硬い欠片") || lower.contains("polygon") || lower.contains("crystal") -> base
                .put("primitive", "polygon")
                .put("center", JSONArray(listOf(0.62, 0.38)))
                .put("radius", 0.08)
                .put("sides", 6)
                .put("rotation", 18)
            text.containsAny("三角", "山", "屋根", "尖", "峰") || lower.contains("triangle") || lower.contains("mountain") -> base
                .put("primitive", "triangle")
                .put("position", JSONArray(listOf(0.54, 0.22)))
                .put("size", JSONArray(listOf(0.20, 0.18)))
                .put("rotation", -8)
            text.containsAny("弧", "円弧", "半円", "上弦", "下弦", "三日月", "波紋", "渦") || lower.contains("arc") || lower.contains("crescent") -> base
                .put("primitive", "arc")
                .put("center", JSONArray(listOf(0.72, 0.32)))
                .put("radius", 0.16)
                .put(
                    "angle_start",
                    when {
                        text.contains("半円") -> 0
                        text.contains("上弦") -> 270
                        text.contains("下弦") -> 90
                        else -> 210
                    },
                )
                .put(
                    "angle_end",
                    when {
                        text.contains("半円") -> 180
                        text.contains("上弦") -> 90
                        text.contains("下弦") -> 270
                        else -> 330
                    },
                )
            text.containsAny("四角", "紙片", "パッチワーク") || lower.contains("square") || lower.contains("rectangle") || lower.contains("patch") -> base
                .put("primitive", "square")
                .put("position", JSONArray(listOf(0.62, 0.28)))
                .put("size", JSONArray(listOf(if (text.contains("横長")) 0.28 else 0.18, if (text.contains("縦長")) 0.28 else 0.12)))
                .put("rotation", if (text.containsAny("回転", "斜め", "右上がり")) -18 else 0)
            text.containsAny("円", "丸", "月", "蕾", "花びら", "香り", "光") || lower.contains("circle") || lower.contains("moon") || lower.contains("petal") || lower.contains("bud") -> base
                .put("primitive", "ellipse")
                .put("center", ServerScoreSemantics.focusPoint(text))
                .put("size", JSONArray(listOf(0.18, 0.11)))
                .put("rotation", -18)
            else -> base
                .put("primitive", "line")
                .put(
                    "from",
                    JSONArray(
                        when {
                            text.contains("垂直") -> listOf(0.5, 0.0)
                            text.contains("全幅") || text.contains("水平") -> listOf(0.0, 0.5)
                            text.contains("半幅") -> listOf(0.25, 0.5)
                            else -> listOf(0.16, 0.78)
                        },
                    ),
                )
                .put(
                    "to",
                    JSONArray(
                        when {
                            text.contains("垂直") -> listOf(0.5, 1.0)
                            text.contains("全幅") || text.contains("水平") -> listOf(1.0, 0.5)
                            text.contains("半幅") -> listOf(0.75, 0.5)
                            else -> listOf(0.84, 0.28)
                        },
                    ),
                )
                .put("rotation", if (text.contains("右下がり")) 30 else -8)
        }
    }

    fun arrangementFrom(text: String): JSONObject? {
        val lower = text.lowercase()
        val count = ServerScoreSemantics.countHintFromDdl(text)
        val arrangement = when {
            text.containsAny("散ら", "点々", "全面", "画面全体", "満天", "砂", "雨", "雪") || lower.contains("scatter") || lower.contains("dotted") ->
                JSONObject().put("count", count ?: ServerScoreSemantics.vagueCount(text)).put("layout", "scatter").put("margin", 0.18)
            text.containsAny("円環", "放射", "同心円", "正五角形") || lower.contains("radial") ->
                JSONObject().put("count", count ?: 8).put("layout", "radial").put("margin", 0.1)
            text.containsAny("並べ", "横に", "縦に", "上から下", "左から右") || lower.contains("line up") ->
                JSONObject().put("count", count ?: 3).put("layout", ServerScoreSemantics.detectLayoutKey(text)).put("margin", 0.1)
            else -> null
        } ?: return null
        when {
            text.containsAny("波打つ軌跡", "波") || lower.contains("undulating trace") -> arrangement.put("path", "wave")
            text.containsAny("斜めの帯", "斜め") || lower.contains("diagonal band") -> arrangement.put("path", "diagonal")
            text.contains("右半分") || lower.contains("right half") -> arrangement.put("path", "right_half")
            text.contains("上から下") || lower.contains("top to bottom") -> arrangement.put("layout", "vertical").put("path", "top_to_bottom")
            text.contains("左から右") || lower.contains("left to right") -> arrangement.put("layout", "horizontal").put("path", "left_to_right")
            else -> arrangement.put("path", "none")
        }
        val originalCount = arrangement.optInt("count", 1)
        when {
            originalCount > 120 -> {
                arrangement.put("count", min(originalCount, 120))
                arrangement.put("density", if (originalCount >= 300) "high" else "medium")
                arrangement.put("cluster_count", if (originalCount >= 300) 9 else 5)
                arrangement.put("fade", if (arrangement.optString("path", "none") != "none") "directional" else "outward")
                arrangement.put("preserve_space", true)
            }
            originalCount >= 40 -> {
                arrangement.put("density", "medium")
                arrangement.put("cluster_count", 4)
                arrangement.put("fade", if (arrangement.optString("path", "none") != "none") "directional" else "outward")
                arrangement.put("preserve_space", true)
            }
        }
        return arrangement
    }

    private fun String.containsAny(vararg markers: String): Boolean = markers.any { contains(it) }
}
