package app.inku.mobile.data

import app.inku.mobile.data.db.productFile
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.fail
import org.junit.Test

class DdlSourceTest {
    @Test fun v2ExportUsesLocksAndV1ImportIsRefused() {
        val input = JSONObject().put("bundled_packages", JSONArray().put("Nature.leaves"))
            .put("language", "ja").put("maximum_entries", 64).put("canonical", JSONArray()).put("legacy", JSONArray())
        val answer = JSONObject(app.inku.mobile.pipeline.NativePipelineBridge.resolveMacroCatalog(input.toString().toByteArray()).decodeToString())
        val entries = answer.getJSONArray("entries"); val locks = answer.getJSONArray("locks")
        val first = entries.getJSONObject(0)
        val definitions = JSONArray().put(first.getJSONObject("definition")).put(first.getJSONObject("definition"))
            .put(entries.getJSONObject(1).getJSONObject("definition"))
        val exported = DdlExport.build("何も書かない。", "ja", definitions, JSONArray().put("first"), JSONObject(), locks = JSONArray().put(locks.getJSONObject(0)))
        assertEquals("inku.ddl-export.v2", exported.getString("schema"))
        assertEquals(1, exported.getJSONArray("plugins").length())
        assertEquals("first", exported.getJSONArray("plugins").getJSONObject(0).getString("note"))
        val imported = DdlExport.parse(exported.toString())
        assertEquals("｛若葉｝", imported.names.single())
        assertEquals("first", imported.plugins.single().summary)
        exported.put("ddl", "Draw a circle.")
        assertEquals("{young leaves}", DdlExport.parse(exported.toString()).names.single())
        exported.getJSONArray("plugins").getJSONObject(0).put("note", "")
        assertEquals("young leaves", DdlExport.parse(exported.toString()).plugins.single().summary)
        try { DdlExport.parse("""{"schema":"inku.ddl-export.v1","ddl":"x"}"""); fail("v1 must be refused") }
        catch (error: IllegalArgumentException) { assertEquals("ddl_export_requires_v2", error.message) }
    }
    @Test
    fun portableSelectionFixturesSurviveLegacyJsonAndCurrentExportWithoutRespelling() {
        val fixtures = JSONArray(productFile("persistence/fixtures/ddl-selection.json").readText())
        for (index in 0 until fixtures.length()) {
            val fixture = fixtures.getJSONObject(index)
            val selected = DdlSource.fromJson(fixture)
            assertEquals(fixture.getString("id"), fixture.opt("selected").takeUnless { it == JSONObject.NULL }, selected.ddl)
            assertEquals(fixture.opt("ddl_source_origin").takeUnless { it == JSONObject.NULL }, selected.origin)
            val oldAndroid = JSONObject(fixture.toString())
            oldAndroid.put("normalized_ddl", oldAndroid.remove("ddl"))
            assertEquals(selected, DdlSource.fromJson(oldAndroid))

            val exported = DdlExport.build(selected.ddl, "en", null, null, JSONObject(), selected.origin)
            assertFalse(exported.has("expanded_ddl"))
            assertFalse(exported.has("normalized_ddl"))
            val imported = DdlExport.parse(exported.toString())
            assertEquals(selected.ddl, imported.ddl)
            assertEquals(selected.origin, imported.ddlSourceOrigin)
            // A previous Android history JSON can be read at the file boundary.
            oldAndroid.put("schema", "inku.history_item")
            assertEquals(selected.ddl, DdlExport.parse(oldAndroid.toString()).ddl)
        }
        assertFalse(DdlSource.hasBody("\u0085\u00a0\u3000"))
    }
}
