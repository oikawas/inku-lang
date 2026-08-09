package app.inku.mobile.render

import org.json.JSONArray
import org.json.JSONObject

/**
 * Render engines 25 and 26: each member of a group gets its own size and angle.
 *
 * Kotlin port of `_scale_member` / `_turn_member` / `_apply_member_sizes` /
 * `_apply_member_rotations` in server/src/inku_server/renderer.py.
 *
 * An `Arrangement` is "several of this shape"; it never says "all of them the
 * same size" and no more says "all of them at the same angle". Until here the
 * shift rewrote coordinates and nothing else, so the N members came out
 * congruent -- the largest signature the engine was adding on its own. Nothing
 * is added to the vocabulary and no field is added to the schema.
 */
object ServerRendererMembers {

    private fun grammar(weight: String): ToolGrammar =
        GRAMMARS[weight] ?: GRAMMARS.getValue("pen")

    private fun coords(ins: JSONObject, key: String): Pair<Double, Double>? {
        val arr = ins.optJSONArray(key) ?: return null
        if (arr.length() < 2) return null
        return arr.getDouble(0) to arr.getDouble(1)
    }

    private fun putCoords(ins: JSONObject, key: String, x: Double, y: Double) {
        ins.put(key, JSONArray(listOf(x, y)))
    }

    /**
     * Scale one member about its own anchor by `k`, keeping the aspect.
     *
     * Every branch here has to leave the anchor where it was: the group is
     * placed afterwards by the fit, which reads nothing but the anchors, so a
     * rule that moved one would hand the placement a different group.
     * circle/ellipse/arc/polygon/cloudform are anchored on `center` and never
     * touch it; `square`/`triangle` are anchored on the middle of a bbox whose
     * corner is `position`, so growing `size` has to pull the corner back by
     * half the growth; a line is anchored on its midpoint, so both ends move
     * away from the midpoint rather than one end away from the other.
     */
    fun scaleMember(ins: JSONObject, k: Double): JSONObject {
        val primitive = ins.optString("primitive", "line")
        val from = coords(ins, "from_") ?: coords(ins, "from")
        val to = coords(ins, "to")
        if (primitive == "line" && from != null && to != null) {
            val mx = (from.first + to.first) / 2
            val my = (from.second + to.second) / 2
            val key = if (ins.has("from_")) "from_" else "from"
            putCoords(ins, key, mx + (from.first - mx) * k, my + (from.second - my) * k)
            putCoords(ins, "to", mx + (to.first - mx) * k, my + (to.second - my) * k)
            return ins
        }
        val position = coords(ins, "position")
        val size = coords(ins, "size")
        if (primitive in setOf("square", "triangle") && position != null && size != null) {
            val (w, h) = size
            putCoords(ins, "size", w * k, h * k)
            putCoords(ins, "position", position.first - (w * k - w) / 2, position.second - (h * k - h) / 2)
            return ins
        }
        if (ins.has("radius") && !ins.isNull("radius")) {
            ins.put("radius", ins.getDouble("radius") * k)
            return ins
        }
        if (size != null) {
            putCoords(ins, "size", size.first * k, size.second * k)
            return ins
        }
        return ins
    }

    /**
     * Turn one member by `dr` degrees, leaving every coordinate where it is.
     *
     * `rotation` is already an engine quantity and every consumer of it turns
     * the shape about its own anchor, so the anchor a member was laid out on is
     * the point it spins around -- which is why this needs none of the three
     * coordinate corrections `scaleMember` needs.
     */
    fun turnMember(ins: JSONObject, dr: Double): JSONObject {
        val current = if (ins.has("rotation") && !ins.isNull("rotation")) ins.optDouble("rotation", 0.0) else 0.0
        ins.put("rotation", current + dr)
        return ins
    }

    /**
     * Give each member of a group its own size (engine 25).
     *
     * Three groups keep their exact repetition. `grid` is the tiling whose
     * point is that the cells match; a group of one has nobody to differ from;
     * and the machine tools carry a `groupHand` of zero.
     */
    fun applySizes(items: List<JSONObject>, arr: JSONObject, memberSeed: String?): List<JSONObject> {
        if (memberSeed == null || arr.optString("layout", "horizontal") == "grid" || items.size < 2) return items
        val hand = grammar(items[0].optString("weight", "pen")).groupHand
        if (hand <= 0.0) return items
        return items.mapIndexed { i, item ->
            val k = 1 + (ServerRendererGeometry.hash01(i, memberSeed, "member-size") - 0.5) * 2 * hand
            scaleMember(item, k)
        }
    }

    /**
     * Give each member of a group its own angle (engine 26).
     *
     * The exclusion list is longer than the size rule's, and deliberately so.
     *
     * A `line` is left alone because there the angle IS what the mark says:
     * tilting the blades of grass tips the grass over. A group that states
     * `rotation` is left alone for the mirror reason -- the description has
     * already answered the question. That test is "was it stated", not "is it
     * non-zero": `rotation: 0` is an answer ("do not tilt these"), and 141
     * groups in production give exactly that answer.
     *
     * A `circle` is left alone because an angle cannot be seen on one. Turning
     * it would change no pixel and move the performance seed, which is the
     * worse half of both outcomes.
     *
     * `grid`, a group of one, and the machine tools carry over unchanged from
     * the size rule.
     */
    fun applyRotations(items: List<JSONObject>, arr: JSONObject, memberSeed: String?): List<JSONObject> {
        if (memberSeed == null || arr.optString("layout", "horizontal") == "grid" || items.size < 2) return items
        val stated = items[0]
        val primitive = stated.optString("primitive", "line")
        val statesRotation = stated.has("rotation") && !stated.isNull("rotation")
        if (primitive in setOf("line", "circle") || statesRotation) return items
        val spread = grammar(stated.optString("weight", "pen")).groupRot
        if (spread <= 0.0) return items
        return items.mapIndexed { i, item ->
            val dr = (ServerRendererGeometry.hash01(i, memberSeed, "member-rot") - 0.5) * 2 * spread
            turnMember(item, dr)
        }
    }
}
