package app.inku.mobile.pipeline

import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import app.inku.mobile.llm.ProviderWireTransport
import app.inku.mobile.llm.chatGptRequest
import app.inku.mobile.ui.camera.CameraImageDdl
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/**
 * A camera work written from its photo by the shared core (SPEC §12.6.6):
 * the production Android entry points and the native core, with a scripted
 * model in place of the provider. No device and no provider is involved.
 */
class ImageDdlPipelineTest {
    @Test
    fun sourceLabelsUseCoreScalarOffsetsIncludingEmoji() {
        val labels = descriptionSourceLabels(NativePipelineBridge, "1. 🌸花 [ 作者 ] ［本］")
        assertEquals(listOf("作者", "本"), (0 until labels.length()).map { labels.getString(it) })
    }

    @Test
    fun editedReadingIsSuppliedWithoutCallingTheReader() = runBlocking {
        val fixture = Fixture(mapOf("write_description_ddl" to """{"ddl":"中心に赤の円を1個置く。","figures":[]}"""))
        val result = fixture.pipeline.paint(PaintRequest(
            description = "赤い円", stage1Model = "anthropic:claude-opus-5-5", stage2Model = "anthropic:claude-opus-5-5",
            colorCatalogId = "default", canvasAspect = "square", autoRepair = true, renderSeed = 7,
            uiLang = "ja", sketch = SketchInput(text = "作者が直した読み"), readAndDraw = true,
        ))
        assertEquals(listOf("write_description_ddl"), fixture.requests.map { it.pipelineAction })
        assertEquals("作者が直した読み", result.sketchText)
        assertEquals("supplied", JSONObject(result.renderMetadataJson).getJSONObject("description_ddl").getString("reading_state"))
    }

    @Test
    fun compositionAndColorsAreDrivenAndSaved() = runBlocking {
        val composition = """{"thesis":"女を左上に置く","form":"one_corner","things":[{"thing":1,"what":"女の姿","role":"focal","kind":"cluster","quote":"妹"},{"thing":2,"what":"紫の影","role":"accent","kind":"cluster","quote":"紫"}],"main_law":"B1","laws":{"B1":{"targets":[{"thing":1,"at":"point_ul"}]}},"reason":"妹を左上に置く"}"""
        val written = """{"sentences":[{"thing":0,"text":"背景を白で埋める。"},{"thing":1,"text":"画面の横0.4、縦0.4の位置に、直径0.3の紫の塗りの円を1個置く。"},{"thing":2,"text":"画面の横0.6、縦0.6の位置に、幅0.2、高さ0.15の灰の薄い塗りの三角を1個置く。"}],"figures":[]}"""
        val fixture = Fixture(mapOf("compose_description" to composition, "write_description_ddl" to written,
            "review_description_ddl" to written, "choose_colors" to """{"main_law":"D5","laws":{"D5":{"hue":"blue","layer":1}},"reason":"青を軸にまとめる"}"""))
        val result = fixture.pipeline.paint(PaintRequest(
            description = "紫の妹", stage1Model = "anthropic:claude-opus-5-5", stage2Model = "anthropic:claude-opus-5-5",
            colorCatalogId = "default", canvasAspect = "square", autoRepair = true, renderSeed = 7,
            uiLang = "ja", readAndDraw = true, descriptionComposition = true, descriptionReview = true,
        ))
        assertEquals(listOf("compose_description", "write_description_ddl", "review_description_ddl", "choose_colors"), fixture.requests.map { it.pipelineAction })
        val record = JSONObject(result.renderMetadataJson).getJSONObject("description_ddl").getJSONObject("composition")
        assertEquals("used", record.getString("state"))
        assertEquals("used", record.getJSONObject("colors").getString("state"))
    }

    @Test
    fun readAndDrawReadsWritesReviewsAndKeepsItsRecord() = runBlocking {
        val fixture = Fixture(mapOf(
            "read_description" to """{"viewpoint":{"speaker":"我","speaker_quote":"我","eye":"女を見ている","addressee_quote":"妹","speaker_seen_quote":""},"core":["紫の女"],"items":[{"kind":"scene","quote":"紫の妹","image":"紫の女"}],"reading":"紫の姿を見ている。"}""",
            "write_description_ddl" to """{"ddl":"背景を黄で埋める。\n中心に赤の円を1個置く。","figures":[{"who":"addressee","what":"妹"}]}""",
            "review_description_ddl" to """{"ddl":"背景を黄で埋める。\n中心に赤の円を1個置く。","figures":[{"who":"addressee","what":"妹"}]}""",
        ))
        val result = try { fixture.pipeline.paint(PaintRequest(
            description = "紫の妹を我は見る [大海人皇子]", stage1Model = "anthropic:claude-opus-5-5",
            stage2Model = "anthropic:claude-opus-5-5", colorCatalogId = "default", canvasAspect = "square",
            autoRepair = true, renderSeed = 7, uiLang = "ja", sketch = SketchInput(requested = true),
            readAndDraw = true, descriptionReview = true,
        )) } catch (error: PipelineInteractionRequired) {
            throw AssertionError("phase=${error.view.phaseReason} failure=${error.view.providerFailure} events=${error.view.eventsJson} requests=${fixture.requests.map { it.pipelineAction }}", error)
        }
        assertEquals(listOf("read_description", "write_description_ddl", "review_description_ddl"), fixture.requests.map { it.pipelineAction })
        val metadata = JSONObject(result.renderMetadataJson)
        assertEquals("read_and_draw", metadata.getString("route"))
        assertEquals("大海人皇子", metadata.getJSONObject("description_ddl").getJSONArray("source_labels").getString(0))
        assertEquals("supplemented", result.sketchState)
        assertTrue(result.sketchText.orEmpty().isNotBlank())
        assertEquals(1, fixture.requests.last().pipelineImages!!.dataUrls.size)
        val prompts = metadata.getJSONObject("sent_system_prompts")
        assertTrue(prompts.getJSONObject("reading").getString("message").isNotBlank())
        assertTrue(prompts.getJSONObject("description_ddl").getString("message").isNotBlank())
        assertTrue(prompts.getJSONObject("description_review").getString("message").isNotBlank())
    }

    private class Fixture(private val answers: Map<String, String>) {
        val requests = mutableListOf<ModelRequest>()
        /** The Anthropic body each request would be sent as. */
        val bodies = mutableListOf<JSONObject>()
        /** The ChatGPT plan body each request would be sent as. */
        val chatGptBodies = mutableListOf<JSONObject>()
        val starts = mutableListOf<JSONObject>()
        val reviewSvgs = mutableListOf<String>()
        val binding = object : SharedPipelineBinding by NativePipelineBridge {
            override fun stepSvgLimited(snapshotBytes: ByteArray, inputEnvelopeBytes: ByteArray, maxSvgBytes: Long): NativeSvgOutput {
                val payload = JSONObject(inputEnvelopeBytes.decodeToString()).getJSONObject("payload")
                if (payload.optString("tag") == "start") starts += payload
                return NativePipelineBridge.stepSvgLimited(snapshotBytes, inputEnvelopeBytes, maxSvgBytes)
            }
        }
        private val executions = mutableMapOf<String, ByteArray>()
        val pipeline = AndroidWorkPipeline(binding, object : ModelProvider {
            override val providerId = "anthropic"
            override suspend fun generate(request: ModelRequest): ModelResponse {
                requests += request
                bodies += JSONObject(ProviderWireTransport.build("anthropic", "anthropic", "https://api.anthropic.com", request).getString("body"))
                chatGptBodies += JSONObject(chatGptRequest(request.copy(modelId = "chatgpt:gpt-6-luna")).body)
                val answer = answers[request.pipelineAction] ?: error("unexpected ${request.pipelineAction}")
                return ModelResponse(answer, request.modelId)
            }
        }, object : PipelineCommitStore {
            override suspend fun commit(ownerId: String, actionJson: String, createIfMissing: Boolean, context: AuthoringContext): String {
                val action = JSONObject(actionJson)
                val payload = action.getJSONObject("payload")
                return JSONObject().put("tag", "visible_normalized_ddl_committed").put("identity", action.getJSONObject("identity"))
                    .put("ddl_digest", payload.getString("ddl_digest"))
                    .put("revision", payload.getJSONObject("authority").getJSONObject("next_state").get("revision"))
                    .put("authority_digest", payload.getString("authority_digest")).toString()
            }
        }, object : PipelineExecutionStore {
            override suspend fun create(ownerId: String, executionId: String, variationId: String, sequence: String, stateBytes: ByteArray) {
                executions[executionId] = stateBytes.copyOf()
            }
            override suspend fun compareAndSet(ownerId: String, executionId: String, expectedSequence: String, nextSequence: String, stateBytes: ByteArray): Boolean {
                executions[executionId] = stateBytes.copyOf(); return true
            }
            override suspend fun load(ownerId: String, executionId: String) = executions[executionId]?.copyOf()
        }, { null }, bundledPluginsEnabled = { false }, imageReviewPng = { svg, _, _ ->
            reviewSvgs += svg
            REVIEW_PNG
        })
    }

    @Test
    fun aPhotoIsWrittenReviewedBesideItsDrawingAndDrawnOnTheNearestPaperWithoutForking() = runBlocking {
        val fixture = Fixture(mapOf(
            "write_image_ddl" to """{"ddl":"青の円を1個置く。"}""",
            "review_image_ddl" to """{"ddl":"赤の円を1個置く。"}""",
        ))
        val image = photo()
        val request = request(image)
        val written = fixture.pipeline.interpretImage(request, image)
        assertEquals(listOf("write_image_ddl", "review_image_ddl"), fixture.requests.map { it.pipelineAction })
        assertTrue(fixture.requests.all { it.maxTokens == IMAGE_DDL_MAX_TOKENS })
        // The photo goes with the writing, the photo then the drawing with the review.
        val (write, review) = fixture.requests
        assertEquals(listOf("data:image/jpeg"), write.pipelineImages!!.dataUrls.map { it.substringBefore(';') })
        assertEquals(listOf("data:image/jpeg", "data:image/png"), review.pipelineImages!!.dataUrls.map { it.substringBefore(';') })
        val blocks = fixture.bodies[1].getJSONArray("messages").getJSONObject(0).getJSONArray("content")
        assertEquals(listOf("image", "image", "text"), (0 until blocks.length()).map { blocks.getJSONObject(it).getString("type") })
        assertEquals("image/png", blocks.getJSONObject(1).getJSONObject("source").getString("media_type"))
        assertTrue(fixture.reviewSvgs.single().startsWith("<svg"))
        // The ChatGPT plan body carries the same images, photo then drawing.
        assertEquals(listOf(listOf("image/jpeg"), listOf("image/jpeg", "image/png")),
            fixture.chatGptBodies.map { body -> inputImages(body).map { it.substringAfter("data:").substringBefore(';') } })
        assertTrue(written.normalizedDdl, written.normalizedDdl.contains("赤"))

        val drawn = fixture.pipeline.composeFromDdl(written.normalizedDdl, request.copy(executionId = written.executionId))
        assertEquals("The drawing must use the run that wrote it", 1, fixture.starts.size)
        assertEquals("image", fixture.starts.single().getJSONObject("authoring").getString("tag"))
        assertEquals(image.nearestFormatId, JSONObject(drawn.renderMetadataJson).getString("canvas_aspect_id"))
        // A 4:3 photo's nearest paper has its ratio, so the Score needs no fit;
        // the run still draws fitted.
        assertEquals("contain", JSONObject(drawn.managedHistoryLink!!.snapshotJson).getJSONObject("config")
            .getJSONObject("compiler").getJSONObject("host").getString("canvas_fit"))
        val record = JSONObject(drawn.renderMetadataJson).getJSONObject("image_ddl")
        assertTrue(record.getString("before_review").contains("青"))
        assertEquals("image/png", record.getJSONObject("drawing").getString("media_type"))
        assertEquals(image.reference.sha256, record.getJSONObject("image").getJSONObject("sent").getString("sha256"))
        val saved = drawn.renderMetadataJson
        assertFalse("No image or SVG is kept with the work", saved.contains("base64") || saved.contains("data:image"))
        assertEquals("", drawn.originalInput)
    }

    @Test
    fun aCatalogChosenFromThePhotoIsAskedWithThePhotoAtStageOnesLimit() = runBlocking {
        val fixture = Fixture(mapOf(
            "select_image_catalog" to """{"catalog_id":"default"}""",
            "write_image_ddl" to """{"ddl":"青の円を1個置く。"}""",
            "review_image_ddl" to """{"ddl":"青の円を1個置く。"}""",
        ))
        val image = photo()
        fixture.pipeline.interpretImage(request(image).copy(colorCatalogId = "auto"), image)
        val select = fixture.requests.first()
        assertEquals("select_image_catalog", select.pipelineAction)
        assertEquals(2048, select.maxTokens)
        assertEquals(1, select.pipelineImages!!.dataUrls.size)
        assertTrue(fixture.starts.single().getJSONObject("authoring").getBoolean("auto_catalog"))
    }

    @Test
    fun aRunWhoseImageIsGoneIsCancelledWithoutSending() = runBlocking {
        val configBuilder = SharedPipelineConfigBuilder(NativePipelineBridge)
        val image = photo()
        val config = configBuilder.build(SharedPipelineConfigRequest(
            resolvedLanguage = "ja", canvasFormatId = image.nearestFormatId, catalogSelectionId = "default",
            renderSeed = 7L, canvasFit = "contain", imageReview = true,
        ))
        var sent = 0
        val executions = mutableMapOf<String, ByteArray>()
        val host = SharedPipelineHost(
            binding = NativePipelineBridge,
            providerEffect = PipelineProviderEffect { _, _ -> sent++; error("must not send") },
            commitStore = object : PipelineCommitStore {
                override suspend fun commit(ownerId: String, actionJson: String, createIfMissing: Boolean, context: AuthoringContext) =
                    error("must not commit")
            },
            executionStore = object : PipelineExecutionStore {
                override suspend fun create(ownerId: String, executionId: String, variationId: String, sequence: String, stateBytes: ByteArray) {
                    executions[executionId] = stateBytes
                }
                override suspend fun compareAndSet(ownerId: String, executionId: String, expectedSequence: String, nextSequence: String, stateBytes: ByteArray): Boolean {
                    executions[executionId] = stateBytes; return true
                }
                override suspend fun load(ownerId: String, executionId: String) = executions[executionId]
            },
            images = PipelineImageStore(),
        )
        val failure = runCatching {
            host.start(PipelineStartRequest(
                ownerId = "owner", configJson = config.configJson,
                authoring = PipelineAuthoring.Image(image.authoringJson().toString(), autoCatalog = false),
                models = PipelineModelSelection("fixture:model", "fixture:model"), context = AuthoringContext(""),
            ))
        }.exceptionOrNull()
        assertEquals("image_missing", failure?.message)
        assertEquals(0, sent)
        val state = JSONObject(executions.values.single().decodeToString())
        val snapshot = JSONObject(String(java.util.Base64.getDecoder().decode(state.getString("snapshot_base64"))))
        assertEquals("cancelled", snapshot.getJSONObject("phase").getString("tag"))
    }

    @Test
    fun onlyARemoteVisionModelTakesThePhotoRoute() {
        assertTrue(CameraImageDdl.usesImageDdl("anthropic:claude-opus-5-5"))
        assertFalse(CameraImageDdl.usesImageDdl("local-litert-lm:gemma-4-e2b-it"))
    }

    companion object {
        /** Every `input_image` URL in a Responses body, in order. */
        private fun inputImages(value: Any?): List<String> = when (value) {
            is JSONObject -> if (value.optString("type") == "input_image") listOf(value.getString("image_url"))
                else value.keys().asSequence().toList().flatMap { inputImages(value.get(it)) }
            is org.json.JSONArray -> (0 until value.length()).flatMap { inputImages(value.get(it)) }
            else -> emptyList()
        }

        private val JPEG = "not decoded by the core".encodeToByteArray()
        private val REVIEW_PNG = "a review drawing".encodeToByteArray()

        /** A 4:3 photo as [ImageDdlInputs.prepare] hands it on, sized by the core. */
        private fun photo(): PreparedImageDdlInput {
            val canvas = ImageDdlCanvas.of(NativePipelineBridge, 800, 600)
            return PreparedImageDdlInput(
                jpeg = JPEG,
                reference = PipelineImageReference.of(JPEG, "image/jpeg", canvas.sentWidth, canvas.sentHeight),
                originalWidth = 800,
                originalHeight = 600,
                nearestFormatId = canvas.nearestFormatId,
            )
        }

        private fun request(image: PreparedImageDdlInput) = PaintRequest(
            description = "", stage1Model = "anthropic:claude-opus-5-5", stage2Model = "anthropic:claude-opus-5-5",
            colorCatalogId = "default", canvasAspect = image.nearestFormatId, autoRepair = true,
            renderSeed = 7L, uiLang = "ja", renderWild = false, canvasFit = CameraImageDdl.CANVAS_FIT,
        )
    }
}
