package app.inku.mobile.pipeline

import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.ManagedHistoryRead
import app.inku.mobile.data.refinement.*
import app.inku.mobile.llm.*
import app.inku.mobile.render.RenderResult
import app.inku.mobile.render.SvgRenderer
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ToolChangeRequestTest {
    @Test fun aMissingSeedColumnUsesTheFrozenParentSeedAndNeverAllocatesAnother() = runBlocking {
        val type = Class.forName("app.inku.mobile.pipeline.SharedPipelineHostTest\$ScriptedBinding")
        val delegate = type.getDeclaredConstructor(Boolean::class.javaPrimitiveType)
            .apply { isAccessible = true }.newInstance(false) as SharedPipelineBinding
        val rendered = mutableListOf<JSONObject>()
        val binding = object : SharedPipelineBinding by delegate {
            override fun savedVariants(inputBytes: ByteArray): ByteArray {
                val asked = JSONObject(inputBytes.toString(Charsets.UTF_8))
                assertEquals("tool_render", asked.getString("action"))
                return """{"schema":"inku.saved-variants.v1","outcome":"ok","ddl":"place one chalk circle.","score":{"instructions":[{"weight":"chalk","arrangement":{"resolved":{"owner":{"kind":"source_instruction","instruction_index":0}}}}]},"derivation_metadata":{"tool_mode":"uniform","tools":{"0":"chalk"},"changes":[{"index":0,"from":"pen","to":"chalk"}]}}""".encodeToByteArray()
            }
            override fun renderSaved(inputBytes: ByteArray): ByteArray {
                rendered += JSONObject(inputBytes.toString(Charsets.UTF_8))
                return """{"svg":"<svg/>","metadata":{}}""".encodeToByteArray()
            }
            override fun renderSavedSvgLimited(inputBytes: ByteArray, maxSvgBytes: Long) = NativeSvgOutput(renderSaved(inputBytes), null)
        }
        val config = SharedPipelineConfigBuilder(binding).build(SharedPipelineConfigRequest(
            resolvedLanguage = "en", canvasFormatId = "square", catalogSelectionId = "default",
            compositionSeed = 77L, bundledPluginsEnabled = false,
        ))
        val score = """{"instructions":[{"weight":"pen","arrangement":{"resolved":{"owner":{"kind":"source_instruction","instruction_index":0}}}}]}"""
        val parent = HistoryItemEntity(
            id="parent",createdAt=1,updatedAt=1,originalInput="parent",normalizedDdl="place one pen circle.",
            scoreJson=score,displaySvg="<svg/>",stage1Model=null,stage2Model=null,renderMetadataJson="{}",
            renderHash="hash",renderHashShort="PPPP",colorCatalogId="default",canvasAspect="square",
            starred=false,trashed=false,elapsedMs=null,tokenMetadataJson=null,renderSeed=null,compositionSeed=null,
        )
        val diagnostics = JSONObject()
        for (key in listOf("upstream_diagnostics","downstream_diagnostics","resource_omissions","relation_omissions")) diagnostics.put(key,JSONArray())
        val context = JSONObject().put("config",JSONObject(config.configJson))
            .put("color_maps",JSONObject(config.renderColorMaps.mapValues { JSONObject(it.value) }))
            .put("macro_catalog",JSONObject().put("definition_locks",JSONArray()).put("diagnostics",JSONArray()))
            .put("host_options",JSONObject().put("render_seed","14859340650796947346"))
            .put("pipeline_diagnostics",diagnostics)
        var stored = ManagedHistoryRead(parent,"ddl_authoritative",variationId="parent-variation",forkContextJson=context.toString())
        val pipeline = AndroidWorkPipeline(
            binding=binding,
            modelProvider=object:ModelProvider{
                override val providerId="none"
                override suspend fun generate(request:ModelRequest):ModelResponse=error("No model call expected")
            },
            commitStore=object:PipelineCommitStore{
                override suspend fun commit(ownerId:String,actionJson:String,createIfMissing:Boolean,context:AuthoringContext):String=error("No commit expected")
            },
            executionStore=object:PipelineExecutionStore{
                override suspend fun create(ownerId:String,executionId:String,variationId:String,sequence:String,stateBytes:ByteArray)=error("No execution write expected")
                override suspend fun compareAndSet(ownerId:String,executionId:String,expectedSequence:String,nextSequence:String,stateBytes:ByteArray):Boolean=error("No execution write expected")
                override suspend fun load(ownerId:String,executionId:String):ByteArray?=error("No execution load expected")
            },
            readHistory={ stored },
            legacyRenderer=object:SvgRenderer{
                override fun render(request:RenderRequest):RenderResult=error("No legacy render expected")
            },
            bundledPluginsEnabled={false},
        )
        val source = ToolChangeSource(parent.normalizedDdl!!,score,config.configJson,
            listOf(TouchTool("pen","ペン","pen"),TouchTool("chalk","チョーク","chalk")),mapOf(0 to "pen"), binding)
        val option=ToolChangeOption(source,ToolChangeMode.Uniform,mapOf(0 to "chalk"))
        val request=PaintRequest("parent",stage1Model="fixture",stage2Model="fixture",colorCatalogId="default",
            canvasAspect="square",autoRepair=false,parentHistoryId=parent.id,saveHistory=false)
        val result=requireNotNull(pipeline.renderToolChange(option,request))
        val options=rendered.single().getJSONObject("request").getJSONObject("options")
        assertEquals("14859340650796947346",options.get("render_seed").toString())
        assertEquals("77",options.get("composition_seed").toString())
        assertEquals("14859340650796947346",java.lang.Long.toUnsignedString(result.renderSeed!!))
        assertEquals(77L,result.compositionSeed)
        stored=ManagedHistoryRead(parent,"legacy_unknown")
        assertTrue(runCatching{pipeline.renderToolChange(option,request)}.isFailure)
        assertEquals("No guessed seed reaches the renderer",1,rendered.size)
    }
}
