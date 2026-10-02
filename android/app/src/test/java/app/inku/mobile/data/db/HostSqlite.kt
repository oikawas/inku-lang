package app.inku.mobile.data.db

import android.database.Cursor
import androidx.sqlite.db.SupportSQLiteDatabase
import java.io.File
import java.lang.reflect.Proxy
import java.util.Base64
import java.util.concurrent.TimeUnit
import org.json.JSONArray
import org.json.JSONObject

internal fun productFile(path: String): File = generateSequence(File(".").canonicalFile) { it.parentFile }
    .first { File(it, "persistence/contract.json").isFile }.resolve(path)

/** Runs the production SQLite calls against a private Python stdlib SQLite connection. */
internal class HostSqlite : AutoCloseable {
    private val process = ProcessBuilder("python3", "-u", "-c", PYTHON).start()
    private val input = process.outputStream.bufferedWriter()
    private val output = process.inputStream.bufferedReader()
    private var transactionSuccessful = false

    val db: SupportSQLiteDatabase = Proxy.newProxyInstance(
        SupportSQLiteDatabase::class.java.classLoader,
        arrayOf(SupportSQLiteDatabase::class.java),
    ) { _, method, args ->
        when (method.name) {
            "query" -> cursor(request(args!![0] as String, args.getOrNull(1) as? Array<*>))
            "execSQL" -> { request(args!![0] as String, args.getOrNull(1) as? Array<*>); null }
            "beginTransaction" -> { request("BEGIN"); transactionSuccessful = false; null }
            "setTransactionSuccessful" -> { transactionSuccessful = true; null }
            "endTransaction" -> { request(if (transactionSuccessful) "COMMIT" else "ROLLBACK"); null }
            else -> error("Unused host SQLite method: ${method.name}")
        }
    } as SupportSQLiteDatabase

    fun request(sql: String, args: Array<*>? = null): JSONObject {
        val encodedArgs = JSONArray()
        args.orEmpty().forEach { value ->
            encodedArgs.put(if (value is ByteArray) JSONObject().put("blob", Base64.getEncoder().encodeToString(value)) else value ?: JSONObject.NULL)
        }
        input.write(JSONObject().put("sql", sql).put("args", encodedArgs).toString())
        input.newLine()
        input.flush()
        val answer = JSONObject(checkNotNull(output.readLine()) { "Host SQLite process ended" })
        check(!answer.has("error")) { answer.optString("error") }
        return answer
    }

    fun createSchema(version: Int): List<JSONObject> {
        val schema = JSONObject(productFile("android/app/schemas/app.inku.mobile.data.db.InkuDatabase/$version.json").readText())
            .getJSONObject("database")
        val entities = schema.getJSONArray("entities")
        return (0 until entities.length()).map { index ->
            val entity = entities.getJSONObject(index)
            val table = entity.getString("tableName")
            fun substitute(sql: String) = sql.replace("\u0024{TABLE_NAME}", table)
            db.execSQL(substitute(entity.getString("createSql")))
            val indexes = entity.optJSONArray("indices") ?: JSONArray()
            for (i in 0 until indexes.length()) db.execSQL(substitute(indexes.getJSONObject(i).getString("createSql")))
            entity
        }.also { db.execSQL("PRAGMA user_version = $version") }
    }

    fun rows(sql: String): String = request(sql).getJSONArray("rows").toString()

    private fun cursor(answer: JSONObject): Cursor {
        val rows = answer.getJSONArray("rows")
        val columns = answer.getJSONArray("columns").let { list -> (0 until list.length()).map { list.getString(it) } }
        var position = -1
        fun value(index: Int): Any? = rows.getJSONArray(position).opt(index).takeUnless { it == JSONObject.NULL }
        return Proxy.newProxyInstance(Cursor::class.java.classLoader, arrayOf(Cursor::class.java)) { _, method, args ->
            when (method.name) {
                "moveToNext" -> { position++; position < rows.length() }
                "moveToFirst" -> { position = 0; rows.length() > 0 }
                "getCount" -> rows.length()
                "getColumnNames" -> columns.toTypedArray()
                "getColumnName" -> columns[args!![0] as Int]
                "getColumnIndex", "getColumnIndexOrThrow" -> columns.indexOf(args!![0] as String).also {
                    check(it >= 0 || method.name == "getColumnIndex") { "Unknown column" }
                }
                "isNull" -> value(args!![0] as Int) == null
                "getString" -> value(args!![0] as Int)?.toString()
                "getLong" -> (value(args!![0] as Int) as Number).toLong()
                "getInt" -> (value(args!![0] as Int) as Number).toInt()
                "getBlob" -> Base64.getDecoder().decode((value(args!![0] as Int) as JSONObject).getString("blob"))
                "close" -> null
                else -> error("Unused host cursor method: ${method.name}")
            }
        } as Cursor
    }

    override fun close() {
        input.close()
        if (!process.waitFor(5, TimeUnit.SECONDS)) process.destroyForcibly()
        output.close()
    }

    companion object {
        private val PYTHON = """
            import base64, json, sqlite3, sys
            db = sqlite3.connect(':memory:', isolation_level=None)
            def encode(value):
                return {'blob': base64.b64encode(value).decode()} if isinstance(value, bytes) else value
            for line in sys.stdin:
                try:
                    command = json.loads(line)
                    args = [base64.b64decode(v['blob']) if isinstance(v, dict) and 'blob' in v else v for v in command['args']]
                    cursor = db.execute(command['sql'], args)
                    result = {'columns': [v[0] for v in cursor.description] if cursor.description else [],
                              'rows': [[encode(v) for v in row] for row in cursor.fetchall()]}
                except Exception as error:
                    result = {'error': str(error)}
                print(json.dumps(result, ensure_ascii=True), flush=True)
            db.close()
        """.trimIndent()
    }
}
