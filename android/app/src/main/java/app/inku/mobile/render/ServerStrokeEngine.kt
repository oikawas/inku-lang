package app.inku.mobile.render

import java.math.BigDecimal
import java.math.RoundingMode
import java.security.MessageDigest

/**
 * Deterministic shared stroke synthesis for hand- and engraving-like tools.
 * Kotlin port of server/src/inku_server/stroke_engine.py.
 */
data class ToolGrammar(
    val stiffness: Double,
    val damping: Double,
    val energyWidth: Double,
    val energyLateral: Double,
    val eventRate: Double,
    val taper: Double,
    val bulge: Double,
    val gesture: Double,
    val periodic: Boolean = false,
    val quantize: Double = 0.0,
    val widthSteps: Int = 0
)

val GRAMMARS: Map<String, ToolGrammar> = mapOf(
    "silverpoint" to ToolGrammar(0.93, 0.90, 0.08, 0.05, 0.04, 0.05, 0.02, 0.012),
    "pencil" to ToolGrammar(0.58, 0.68, 0.34, 0.42, 0.55, 0.12, 0.14, 0.05),
    "pen" to ToolGrammar(0.82, 0.80, 0.16, 0.12, 0.12, 0.08, 0.06, 0.022),
    "rotring" to ToolGrammar(1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    "crayon" to ToolGrammar(0.48, 0.60, 0.38, 0.34, 0.75, 0.14, 0.18, 0.06),
    "chalk" to ToolGrammar(0.42, 0.56, 0.42, 0.38, 0.90, 0.18, 0.20, 0.07),
    "brush_thin" to ToolGrammar(0.36, 0.52, 0.66, 0.48, 0.48, 0.88, 0.28, 0.10),
    "brush_thick" to ToolGrammar(0.30, 0.48, 0.78, 0.55, 0.58, 0.92, 0.34, 0.13),
    "burin" to ToolGrammar(0.91, 0.86, 0.58, 0.09, 0.08, 0.98, 1.0, 0.018),
    "drypoint" to ToolGrammar(0.68, 0.70, 0.44, 0.20, 0.45, 0.55, 0.48, 0.05),
    "computer" to ToolGrammar(
        1.0,
        1.0,
        0.30,
        0.34,
        0.0,
        0.0,
        0.0,
        0.06,
        periodic = true,
        quantize = 0.018,
        widthSteps = 4
    )
)

const val WILD_GAIN: Double = 3.5
const val GESTURE_EDGE: Double = 0.16

data class StrokeSample(
    val t: Double,
    val x: Double,
    val y: Double,
    val width: Double,
    val energy: Double,
    val lateral: Double,
    val event: String? = null,
    val residual: Double = 0.0
)

data class StrokeResult(
    val samples: List<StrokeSample>,
    val outline: List<Pair<Double, Double>>,
    val eventCount: Int,
    val burrSide: Int,
    val burrOpacity: Double,
    val gridStep: Double = 0.0
)

data class ContourStrokeResult(
    val samples: List<StrokeSample>,
    val left: List<Pair<Double, Double>>,
    val right: List<Pair<Double, Double>>,
    val eventCount: Int,
    val burrSide: Int,
    val burrOpacity: Double,
    val closed: Boolean,
    val gridStep: Double = 0.0
)

const val CLOSED_ENVELOPE_FLOOR: Double = 0.35

object ServerStrokeEngine {

    fun unitHash(seed: Long, label: String, index: Int): Double {
        val digest = MessageDigest.getInstance("SHA-256")
        val input = "${seed.toULong()}:$label:$index".toByteArray(Charsets.UTF_8)
        val hash = digest.digest(input)
        
        var raw: ULong = 0uL
        for (i in 0 until 8) {
            raw = raw or ((hash[i].toULong() and 0xFFuL) shl (i * 8))
        }
        val maxVal = 18446744073709551615.0 // 2^64 - 1
        return raw.toDouble() / maxVal
    }

    fun smoothNoise(t: Double, seed: Long, octave: Int): Double {
        val frequency = Math.pow(2.0, octave.toDouble())
        val x = t * frequency
        val i = Math.floor(x).toInt()
        var f = x - i
        f = f * f * (3.0 - 2.0 * f)
        val a = unitHash(seed, "energy-$octave", i) * 2.0 - 1.0
        val b = unitHash(seed, "energy-$octave", i + 1) * 2.0 - 1.0
        return a * (1.0 - f) + b * f
    }

    fun latentEnergy(t: Double, seed: Long): Double {
        var sum = 0.0
        for (octave in 1..6) {
            val freq = Math.pow(2.0, octave.toDouble())
            sum += smoothNoise(t, seed, octave) / Math.sqrt(freq)
        }
        val valNorm = sum / 1.75
        return Math.max(-1.0, Math.min(1.0, valNorm))
    }

    fun smoothNoiseSalted(t: Double, seed: Long, salt: String, frequency: Double): Double {
        val x = t * frequency
        val i = Math.floor(x).toInt()
        var f = x - i
        f = f * f * (3.0 - 2.0 * f)
        val a = unitHash(seed, salt, i) * 2.0 - 1.0
        val b = unitHash(seed, salt, i + 1) * 2.0 - 1.0
        return a * (1.0 - f) + b * f
    }

    fun edgeWindow(t: Double): Double {
        if (t <= 0.0 || t >= 1.0) return 0.0
        if (t < GESTURE_EDGE) {
            return 0.5 * (1.0 - Math.cos(Math.PI * t / GESTURE_EDGE))
        }
        if (t > 1.0 - GESTURE_EDGE) {
            return 0.5 * (1.0 - Math.cos(Math.PI * (1.0 - t) / GESTURE_EDGE))
        }
        return 1.0
    }

    fun swell(t: Double, seed: Long): Double {
        val n = smoothNoiseSalted(t, seed, "swell", 1.5)
        return 0.45 + 0.55 * (0.5 + 0.5 * n)
    }

    fun gestureWave(t: Double, seed: Long, salt: String): Double {
        val a = smoothNoiseSalted(t, seed, salt, 1.0)
        val b = smoothNoiseSalted(t, seed, salt, 2.0)
        return Math.max(-1.0, Math.min(1.0, a * 0.7 + b * 0.35))
    }

    fun quantize(value: Double, step: Double): Double {
        return if (step <= 0.0) value else Math.rint(value / step) * step
    }

    fun gridPoint(value: Double, step: Double): Double {
        return quantize(value, step)
    }

    fun machineEnergy(t: Double): Double {
        val tau = 2.0 * Math.PI
        return 0.72 * Math.sin(t * tau * 5.0) + 0.28 * Math.sin(t * tau * 10.0)
    }

    fun machineSwell(t: Double): Double {
        return 0.45 + 0.55 * Math.sin(Math.PI * t)
    }

    fun machineGesture(t: Double): Double {
        val tau = 2.0 * Math.PI
        return Math.sin(t * tau * 2.0)
    }

    fun eventMap(seed: Long, rate: Double, count: Int): Map<Int, String> {
        val events = mutableMapOf<Int, String>()
        val probability = Math.min(0.12, rate / Math.max(1, count - 2).toDouble())
        val kinds = listOf("catch", "fade", "correction")
        
        for (i in 3 until (count - 3)) {
            if (unitHash(seed, "event-arrival", i) < probability) {
                val kindIndex = (unitHash(seed, "event-kind", i) * kinds.size).toInt() % kinds.size
                events[i] = kinds[kindIndex]
                if (events.size >= 2) {
                    break
                }
            }
        }
        return events
    }

    fun synthesizeStroke(
        start: Pair<Double, Double>,
        end: Pair<Double, Double>,
        baseWidth: Double,
        weight: String,
        seed: Long,
        samplesCount: Int = 49,
        wild: Boolean = false,
        gridStep: Double = 0.0
    ): StrokeResult {
        val grammar = GRAMMARS[weight] ?: error("Unknown weight: $weight")
        val dx = end.first - start.first
        val dy = end.second - start.second
        val length = Math.max(1e-6, Math.hypot(dx, dy))
        val ux = dx / length
        val uy = dy / length
        val nx = -uy
        val ny = ux
        val events = eventMap(seed, grammar.eventRate, samplesCount)
        
        val position = doubleArrayOf(start.first, start.second)
        val velocity = doubleArrayOf(dx / (samplesCount - 1), dy / (samplesCount - 1))
        var gestureAmp = length * grammar.gesture
        if (wild && !grammar.periodic) {
            gestureAmp *= WILD_GAIN
        }
        val result = mutableListOf<StrokeSample>()

        for (i in 0 until samplesCount) {
            val t = i.toDouble() / (samplesCount - 1)
            val target = Pair(start.first + dx * t, start.second + dy * t)
            
            if (i > 0) {
                velocity[0] = velocity[0] * grammar.damping + (target.first - position[0]) * grammar.stiffness
                velocity[1] = velocity[1] * grammar.damping + (target.second - position[1]) * grammar.stiffness
                position[0] += velocity[0] * 0.72
                position[1] += velocity[1] * 0.72
            }
            
            val energy: Double
            val envelope: Double
            if (grammar.periodic) {
                energy = machineEnergy(t)
                envelope = machineSwell(t)
            } else {
                energy = latentEnergy(t, seed)
                envelope = edgeWindow(t) * swell(t, seed)
            }
            var lateral = energy * grammar.energyLateral * baseWidth * (0.18 + 0.82 * envelope)
            
            val event = events[i]
            var eventWidth = 1.0
            if (event == "catch") {
                eventWidth = 1.45
                lateral += (unitHash(seed, "catch-side", i) * 2.0 - 1.0) * baseWidth * 0.35
            } else if (event == "fade") {
                eventWidth = 0.04
            } else if (event == "correction") {
                lateral += (unitHash(seed, "correction-kick", i) * 2.0 - 1.0) * baseWidth * 0.25
            }

            var profile = 1.0
            if (grammar.taper != 0.0) {
                profile *= (1.0 - grammar.taper) + grammar.taper * envelope
            }
            if (grammar.bulge != 0.0) {
                profile *= 1.0 + grammar.bulge * envelope
            }

            var width = Math.max(
                0.015,
                baseWidth * profile * (1.0 + grammar.energyWidth * energy * 0.45) * eventWidth
            )

            var gx = 0.0
            var gy = 0.0
            if (gestureAmp != 0.0) {
                val win: Double
                val gLat: Double
                val gLon: Double
                if (grammar.periodic) {
                    win = 1.0
                    gLat = machineGesture(t)
                    gLon = 0.0
                } else {
                    win = edgeWindow(t)
                    gLat = gestureWave(t, seed, "gesture-lat")
                    gLon = gestureWave(t, seed, "gesture-lon")
                }
                gx = gestureAmp * win * (nx * gLat + ux * gLon)
                gy = gestureAmp * win * (ny * gLat + uy * gLon)
            }

            var x = position[0] + nx * lateral + gx
            var y = position[1] + ny * lateral + gy
            var residual = 0.0

            if (gridStep > 0.0) {
                val qx = quantize(x, gridStep)
                val qy = quantize(y, gridStep)
                residual = Math.hypot(x - qx, y - qy)
                x = qx
                y = qy
            }

            if (grammar.widthSteps > 0) {
                width = Math.max(0.015, quantize(width, baseWidth / grammar.widthSteps))
            }

            result.add(
                StrokeSample(
                    t,
                    x,
                    y,
                    width,
                    energy,
                    lateral,
                    event,
                    residual
                )
            )
        }

        // Pin intention endpoints. Width still carries the entry/exit profile.
        result[0] = StrokeSample(0.0, start.first, start.second, result[0].width, result[0].energy, 0.0, null, 0.0)
        result[result.size - 1] = StrokeSample(1.0, end.first, end.second, result[result.size - 1].width, result[result.size - 1].energy, 0.0, null, 0.0)

        val left = result.map { p -> Pair(p.x + nx * p.width / 2.0, p.y + ny * p.width / 2.0) }
        val right = result.reversed().map { p -> Pair(p.x - nx * p.width / 2.0, p.y - ny * p.width / 2.0) }
        
        val side = if (unitHash(seed, "burr-side", 0) < 0.5) -1 else 1
        val slowEnergy = result.sumOf { it.energy } / result.size
        val burrOpacity = 0.15 + 0.12 * (1.0 - slowEnergy) + 0.08 * unitHash(seed, "burr-ink", 0)

        return StrokeResult(
            result,
            left + right,
            events.size,
            side,
            Math.min(0.35, burrOpacity),
            gridStep
        )
    }

    private fun formatCoord(valNum: Double): String {
        return ServerRendererGeometry.fmt(valNum)
    }

    fun polygonPath(points: List<Pair<Double, Double>>): String {
        if (points.isEmpty()) return ""
        return "M " + points.joinToString(" L ") { "${formatCoord(it.first)} ${formatCoord(it.second)}" } + " Z"
    }

    fun ringPath(outer: List<Pair<Double, Double>>, inner: List<Pair<Double, Double>>): String {
        return "${polygonPath(outer)} ${polygonPath(inner)}".trim()
    }

    fun contourStrokePath(result: ContourStrokeResult): String {
        if (result.closed) {
            return ringPath(result.left, result.right)
        }
        return polygonPath(result.left + result.right.reversed())
    }

    fun centerlineNormals(points: List<Pair<Double, Double>>, closed: Boolean): List<Pair<Double, Double>> {
        val count = points.size
        val last = count - 1
        val normals = mutableListOf<Pair<Double, Double>>()

        for (index in 0 until count) {
            val before = if (closed) {
                points[(index - 1 + count) % count]
            } else {
                points[Math.max(0, index - 1)]
            }
            val after = if (closed) {
                points[(index + 1) % count]
            } else {
                points[Math.min(last, index + 1)]
            }

            val dx = after.first - before.first
            val dy = after.second - before.second
            val length = Math.max(1e-6, Math.hypot(dx, dy))
            normals.add(Pair(-dy / length, dx / length))
        }
        return normals
    }

    fun arcLengthParameters(points: List<Pair<Double, Double>>, closed: Boolean): List<Double> {
        val running = mutableListOf(0.0)
        var total = 0.0
        for (index in 1 until points.size) {
            val previous = points[index - 1]
            val current = points[index]
            total += Math.hypot(current.first - previous.first, current.second - previous.second)
            running.add(total)
        }
        if (closed && points.size > 1) {
            val first = points[0]
            val last = points[points.size - 1]
            total += Math.hypot(first.first - last.first, first.second - last.second)
        }
        if (total <= 1e-9) {
            return List(points.size) { 0.0 }
        }
        return running.map { it / total }
    }

    fun outlineForCenterline(points: List<Pair<Double, Double>>, widths: List<Double>): List<Pair<Double, Double>> {
        if (points.size < 2) {
            return points
        }
        val (left, right) = banksForCenterline(points, widths, closed = false)
        return left + right.reversed()
    }

    fun banksForCenterline(
        points: List<Pair<Double, Double>>,
        widths: List<Double>,
        closed: Boolean
    ): Pair<List<Pair<Double, Double>>, List<Pair<Double, Double>>> {
        val normals = centerlineNormals(points, closed)
        val left = mutableListOf<Pair<Double, Double>>()
        val right = mutableListOf<Pair<Double, Double>>()

        for (index in points.indices) {
            val (x, y) = points[index]
            val (nx, ny) = normals[index]
            val width = widths[Math.min(index, widths.size - 1)]
            left.add(Pair(x + nx * width / 2.0, y + ny * width / 2.0))
            right.add(Pair(x - nx * width / 2.0, y - ny * width / 2.0))
        }
        return Pair(left, right)
    }

    fun synthesizeAlong(
        centerline: List<Pair<Double, Double>>,
        baseWidth: Double,
        weight: String,
        seed: Long,
        closed: Boolean,
        anchors: Set<Int> = emptySet(),
        gridStep: Double = 0.0,
        wild: Boolean = false
    ): ContourStrokeResult {
        val points = centerline
        val count = points.size
        val grammar = GRAMMARS[weight] ?: error("Unknown weight: $weight")

        if (count < 2) {
            val sample = StrokeSample(0.0, points[0].first, points[0].second, baseWidth, 0.0, 0.0)
            return ContourStrokeResult(
                listOf(sample), points, points, 0, 1, 0.0, closed, gridStep
            )
        }

        val normals = centerlineNormals(points, closed)
        val parameters = arcLengthParameters(points, closed)
        val events = eventMap(seed, grammar.eventRate, count)

        var gestureAmp = 0.0
        if (wild && !grammar.periodic) {
            val totalLength = Math.max(
                1e-6,
                (0 until count - 1).sumOf { i ->
                    Math.hypot(points[i + 1].first - points[i].first, points[i + 1].second - points[i].second)
                }
            )
            val size = if (closed) totalLength / (2.0 * Math.PI) else totalLength
            gestureAmp = size * grammar.gesture * WILD_GAIN
        }

        var gestures = DoubleArray(count)
        if (gestureAmp != 0.0) {
            gestures = DoubleArray(count) { i -> gestureWave(parameters[i], seed, "gesture-lat") }
            if (closed) {
                val mean = gestures.sum() / count
                for (i in 0 until count) {
                    gestures[i] -= mean
                }
            }
        }

        val position = doubleArrayOf(points[0].first, points[0].second)
        val velocity = doubleArrayOf(0.0, 0.0)
        var samples = mutableListOf<StrokeSample>()

        for (index in points.indices) {
            val target = points[index]
            val t = parameters[index]

            if (index > 0) {
                val previous = points[index - 1]
                val step = Pair(target.first - previous.first, target.second - previous.second)
                velocity[0] = velocity[0] * grammar.damping + (target.first - position[0] - step.first) * grammar.stiffness
                velocity[1] = velocity[1] * grammar.damping + (target.second - position[1] - step.second) * grammar.stiffness
                position[0] += step.first + velocity[0] * 0.72
                position[1] += step.second + velocity[1] * 0.72
            }

            val energy: Double
            val envelope: Double
            if (grammar.periodic) {
                energy = machineEnergy(t)
                envelope = if (closed) 1.0 else machineSwell(t)
            } else if (closed) {
                energy = latentEnergy(t, seed)
                envelope = swell(t, seed)
            } else {
                energy = latentEnergy(t, seed)
                envelope = edgeWindow(t) * swell(t, seed)
            }

            var lateral = energy * grammar.energyLateral * baseWidth * (0.18 + 0.82 * envelope)
            val event = events[index]
            var eventWidth = 1.0

            if (event == "catch") {
                eventWidth = 1.45
                lateral += (unitHash(seed, "catch-side", index) * 2.0 - 1.0) * baseWidth * 0.35
            } else if (event == "fade") {
                eventWidth = 0.04
            } else if (event == "correction") {
                lateral += (unitHash(seed, "correction-kick", index) * 2.0 - 1.0) * baseWidth * 0.25
            }

            var profile = 1.0
            if (grammar.taper != 0.0) {
                profile *= (1.0 - grammar.taper) + grammar.taper * envelope
            }
            if (grammar.bulge != 0.0) {
                profile *= 1.0 + grammar.bulge * envelope
            }

            var width = Math.max(
                0.015,
                baseWidth * profile * (1.0 + grammar.energyWidth * energy * 0.45) * eventWidth
            )

            var gesture = 0.0
            if (gestureAmp != 0.0) {
                var win = if (closed) 1.0 else edgeWindow(t)
                if (anchors.isNotEmpty()) {
                    val minDist = anchors.minOf { anchor -> Math.abs(index - anchor) }
                    win *= Math.min(1.0, minDist / 12.0)
                }
                gesture = gestureAmp * win * gestures[index]
            }

            val (nx, ny) = normals[index]
            var x = position[0] + nx * (lateral + gesture)
            var y = position[1] + ny * (lateral + gesture)
            var residual = 0.0

            if (gridStep > 0.0) {
                val qx = quantize(x, gridStep)
                val qy = quantize(y, gridStep)
                residual = Math.hypot(x - qx, y - qy)
                x = qx
                y = qy
            }

            if (grammar.widthSteps > 0) {
                width = Math.max(0.015, quantize(width, baseWidth / grammar.widthSteps))
            }

            var finalLateral = lateral
            var finalEvent = event

            if (anchors.contains(index)) {
                x = target.first
                y = target.second
                finalLateral = 0.0
                finalEvent = null
                position[0] = target.first
                position[1] = target.second
                residual = 0.0
            }

            samples.add(StrokeSample(t, x, y, width, energy, finalLateral, finalEvent, residual))
        }

        if (!closed) {
            samples[0] = StrokeSample(0.0, points[0].first, points[0].second, samples[0].width, samples[0].energy, 0.0, null, 0.0)
            val lastPIdx = points.lastIndex
            val lastSIdx = samples.lastIndex
            samples[lastSIdx] = StrokeSample(1.0, points[lastPIdx].first, points[lastPIdx].second, samples[lastSIdx].width, samples[lastSIdx].energy, 0.0, null, 0.0)
        } else if (anchors.isEmpty() && count > 2) {
            samples = closedSeamCorrection(samples, points, parameters)
        }

        val performed = samples.map { Pair(it.x, it.y) }
        val widths = samples.map { it.width }
        val (left, right) = banksForCenterline(performed, widths, closed)

        val side = if (unitHash(seed, "burr-side", 0) < 0.5) -1 else 1
        val slowEnergy = samples.sumOf { it.energy } / samples.size
        val burrOpacity = 0.15 + 0.12 * (1.0 - slowEnergy) + 0.08 * unitHash(seed, "burr-ink", 0)

        return ContourStrokeResult(
            samples,
            left,
            right,
            events.size,
            side,
            Math.min(0.35, burrOpacity),
            closed,
            gridStep
        )
    }

    private fun closedSeamCorrection(
        samples: List<StrokeSample>,
        points: List<Pair<Double, Double>>,
        parameters: List<Double>
    ): MutableList<StrokeSample> {
        val span = parameters.last()
        if (span <= 1e-9) {
            return samples.toMutableList()
        }
        val first = samples.first()
        val last = samples.last()

        val gapX = (last.x - points.last().first) - (first.x - points.first().first)
        val gapY = (last.y - points.last().second) - (first.y - points.first().second)
        val gapWidth = last.width - first.width

        val corrected = mutableListOf<StrokeSample>()
        for (index in samples.indices) {
            val sample = samples[index]
            val factor = parameters[index] / span
            corrected.add(
                StrokeSample(
                    sample.t,
                    sample.x - gapX * factor,
                    sample.y - gapY * factor,
                    Math.max(0.015, sample.width - gapWidth * factor),
                    sample.energy,
                    sample.lateral,
                    sample.event,
                    sample.residual
                )
            )
        }
        return corrected
    }
}

