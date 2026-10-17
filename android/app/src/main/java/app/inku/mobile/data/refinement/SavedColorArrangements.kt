package app.inku.mobile.data.refinement

import java.io.StringReader
import java.math.BigInteger
import java.security.MessageDigest
import javax.xml.parsers.DocumentBuilderFactory
import kotlin.math.round
import org.xml.sax.InputSource

data class ColorArrangementPage(
    val entries: List<Int>,
    val nextCursor: Int?,
    val total: Int,
)

/** Distinct visible color assignments in the server's spread order. */
class SavedColorArrangements private constructor(
    private val palette: List<String>,
    private val used: List<String>,
    private val identityRank: Long,
    private val start: Long,
) {
    val total: Int = (permutations(palette.size, used.size) - 1).also {
        require(it in 0..Int.MAX_VALUE.toLong()) { "saved color arrangement count is too large" }
    }.toInt()

    fun page(cursor: Int = 0): ColorArrangementPage {
        require(cursor >= 0) { "color arrangement cursor must be nonnegative" }
        val end = (cursor.toLong() + 8).coerceAtMost(total.toLong()).toInt()
        return ColorArrangementPage((cursor until end).toList(), end.takeIf { it < total }, total)
    }

    fun colorMap(parentMap: Map<String, String>, index: Int): Map<String, String> {
        val substitution = substitution(index)
        val previous = parentMap.filterKeys { it.startsWith("recolor:") }.map { (key, value) ->
            val source = normalizedHex(key.removePrefix("recolor:"))
            val target = normalizedHex(value)
            require(source != null && target != null) { "saved work has an invalid color arrangement" }
            source to target
        }.toMap()
        val result = parentMap.filterKeys { !it.startsWith("recolor:") }.toMutableMap()
        val originals = result.values.mapNotNull(::normalizedHex).toSet() + previous.keys
        for (original in originals) {
            val current = previous[original] ?: original
            val target = substitution[current] ?: current
            if (target != original) result["recolor:$original"] = target
        }
        return result
    }

    private fun substitution(index: Int): Map<String, String> {
        require(index in 0 until total) { "color arrangement index is exhausted or invalid" }
        val spread = (start + index.toLong() * stride()) % total
        var rank = spread + if (spread >= identityRank) 1 else 0
        val remaining = palette.toMutableList()
        return used.associateWith { color ->
            val block = permutations(remaining.size - 1, used.size - (palette.size - remaining.size) - 1)
            val digit = (rank / block).toInt()
            rank %= block
            remaining.removeAt(digit)
        }
    }

    private fun stride(): Long {
        var step = round(total * ((kotlin.math.sqrt(5.0) - 1.0) / 2.0)).toLong().coerceAtLeast(1)
        while (gcd(step, total.toLong()) != 1L) step++
        return step
    }

    companion object {
        private val hex = Regex("#[0-9a-f]{6}")
        private val shortHex = Regex("#[0-9a-f]{3}")
        private val paintAttributes = setOf("fill", "stroke", "stop-color", "flood-color", "lighting-color", "color")

        fun fromSaved(svg: String, colorMap: Map<String, String>, workId: String): SavedColorArrangements {
            val colors = colorMap.filterKeys { it.startsWith("palette:") }.values.map { value ->
                normalizedHex(value) ?: throw IllegalArgumentException("saved color catalog has no usable palette")
            }
            require(colors.isNotEmpty()) { "saved color catalog has no usable palette" }
            val palette = colors.distinct().sorted()
            require(!svg.contains("<!DOCTYPE", ignoreCase = true)) { "saved work has no usable SVG" }
            val factory = DocumentBuilderFactory.newInstance().apply {
                isNamespaceAware = true
                isExpandEntityReferences = false
                runCatching { setFeature("http://apache.org/xml/features/disallow-doctype-decl", true) }
                runCatching { setFeature("http://xml.org/sax/features/external-general-entities", false) }
                runCatching { setFeature("http://xml.org/sax/features/external-parameter-entities", false) }
            }
            val root = runCatching { factory.newDocumentBuilder().parse(InputSource(StringReader(svg))).documentElement }
                .getOrElse { throw IllegalArgumentException("saved work has no usable SVG", it) }
            val paints = mutableSetOf<String>()
            fun visit(element: org.w3c.dom.Element) {
                val attributes = element.attributes
                val values = mutableMapOf<String, String>()
                for (i in 0 until attributes.length) {
                    val attribute = attributes.item(i)
                    values[attribute.nodeName] = attribute.nodeValue
                }
                element.getAttribute("style").split(';').forEach { declaration ->
                    val split = declaration.indexOf(':')
                    if (split > 0) values[declaration.substring(0, split).trim()] = declaration.substring(split + 1).trim()
                }
                values.forEach { (name, value) ->
                    if (name in paintAttributes) normalizedHex(value)?.let(paints::add)
                }
                val children = element.childNodes
                for (i in 0 until children.length) (children.item(i) as? org.w3c.dom.Element)?.let(::visit)
            }
            visit(root)
            val used = paints.intersect(palette.toSet()).sorted()
            val remaining = palette.toMutableList()
            var rank = 0L
            for ((position, color) in used.withIndex()) {
                val digit = remaining.indexOf(color)
                rank += digit * permutations(remaining.size - 1, used.size - position - 1)
                remaining.removeAt(digit)
            }
            val digest = MessageDigest.getInstance("SHA-256").digest(workId.toByteArray(Charsets.UTF_8))
            val options = permutations(palette.size, used.size) - 1
            val start = if (options == 0L) 0L else
                BigInteger(1, digest.copyOfRange(0, 8)).mod(BigInteger.valueOf(options)).toLong()
            return SavedColorArrangements(palette, used, rank, start)
        }

        private fun normalizedHex(value: String): String? {
            val clean = value.trim().lowercase()
            return when {
                hex.matches(clean) -> clean
                shortHex.matches(clean) -> "#" + clean.drop(1).flatMap { listOf(it, it) }.joinToString("")
                else -> null
            }
        }

        private fun permutations(n: Int, k: Int): Long {
            var value = 1L
            for (i in 0 until k) value = Math.multiplyExact(value, (n - i).toLong())
            return value
        }

        private tailrec fun gcd(a: Long, b: Long): Long = if (b == 0L) a else gcd(b, a % b)
    }
}
