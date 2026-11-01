package app.inku.mobile.data

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class DdlExportSaijikiTest {
    @Test fun exportEditionAndLegacyImport() {
        val export = DdlExport.build("赤いガッシュの線。", "ja", null, null, JSONObject())
        assertEquals("inku.saijiki.v3", export.getString("saijiki"))
        assertEquals("赤いガッシュの線。", DdlExport.parse(export.toString()).ddl)
        assertEquals(0, DdlExport.parse(export.toString()).migratedChanges)
        for (schema in listOf(DdlExport.SCHEMA, "inku.history_item")) {
            val file = JSONObject().put("schema", schema).put("ddl", "青の細筆の線を3個引く。").put("language", "ja")
            val result = DdlExport.parse(file.toString())
            assertEquals("青のガッシュの線を3個引く。", result.ddl)
            assertEquals(1, result.migratedChanges)
        }
    }
    @Test fun otherEditionsAndInvalidDefinitionsAreRefused() {
        val file = JSONObject().put("schema", DdlExport.SCHEMA).put("ddl", "赤い円。")
        try { DdlExport.parse(file.put("saijiki", "inku.saijiki.v4").toString()); fail() } catch (_: IllegalArgumentException) { }
        file.remove("saijiki")
        file.put("plugins", org.json.JSONArray().put(JSONObject().put("definition", JSONObject())))
        try { DdlExport.parse(file.toString()); fail() } catch (_: IllegalArgumentException) { }
        assertEquals("細筆の線。", DdlExport.parse("細筆の線。").ddl)
    }
}
