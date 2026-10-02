package app.inku.mobile.data

import app.inku.mobile.data.db.productFile
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class DdlSourceTest {
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
