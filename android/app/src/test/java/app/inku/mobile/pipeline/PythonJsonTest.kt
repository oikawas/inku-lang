package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class PythonJsonTest {
    /** The expected text is `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))`. */
    @Test
    fun aHashedScoreIsWrittenAsPythonWritesIt() {
        val value = JSONObject()
            .put("s", "a/b あ\n\"q\"\\\u0001")
            .put("w", 0.5)
            .put("x", 1e-05)
            .put("y", 1e16)
            .put("z", 0.0001)
            .put("i", 7)
            .put("big", java.math.BigInteger("18446744073709551615"))
            .put("neg", -2.5e-07)
            .put("f", 123456.789)
            .put("t", true)
            .put("n", JSONObject.NULL)
            .put("a", JSONArray().put(1.0).put(2).put("/"))

        assertEquals(
            """{"a":[1.0,2,"/"],"big":18446744073709551615,"f":123456.789,"i":7,"n":null,"neg":-2.5e-07,""" +
                """"s":"a/b あ\n\"q\"\\\u0001","t":true,"w":0.5,"x":1e-05,"y":1e+16,"z":0.0001}""",
            PythonJson.canonical(value),
        )
    }
}
