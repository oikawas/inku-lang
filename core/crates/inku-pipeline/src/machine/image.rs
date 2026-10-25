//! A work written from an image (the image tab, 2026-10-24).
//!
//! The run chooses the catalog from the image when asked, has a Vision model
//! write the DDL and gives the compiler's findings back once, shows the
//! model the drawing of that DDL beside the image and asks once more, and
//! commits the DDL it is left with as a DDL edit (`written`). The DDL declares
//! the image's ratio and is fitted into the run's paper. The core holds no
//! image: each request names its images by reference, and the host draws the
//! drawing and keeps both images for the requests it sends.

use inku_score::CanvasFit;
use serde_json::json;

use super::{ImageDdlRecord, ImageInput, PipelineSnapshot, proposal};
use crate::core_boundary::CatalogMode;
use crate::image_ddl::{
    ImageCanvas, ImageCatalogCandidate, ImageDdlContext, ImageDdlLimits,
    build_image_catalog_selection_prompt, build_image_ddl_prompt, build_image_ddl_review_prompt,
    validate_image,
};
use crate::prompts::{LlmPrompt, LlmStage, PromptImage, parse_catalog_selection_response};
use crate::protocol::{PipelineEvent, ProtocolError, ProviderFailure};

impl PipelineSnapshot {
    /// Start a work from an image.
    pub(super) fn image(
        &mut self,
        image: ImageInput,
        auto_catalog: bool,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        if self.config.image.is_none() {
            return Err(ProtocolError::InvalidPolicy);
        }
        // A work from an image chooses its catalog only when asked to, as a
        // direct DDL does not.
        if !auto_catalog
            && matches!(
                self.config.compiler.host.catalog_mode(),
                CatalogMode::AutoSelected | CatalogMode::AutoFallbackDefault
            )
        {
            return Err(ProtocolError::InvalidPolicy);
        }
        // The run commits its DDL as a DDL edit.
        let _ = proposal(
            self.authority
                .propose_committed_user_ddl_mutation(self.authority.revision(), true),
        )?;
        validate_image(&image.sent).map_err(|_| ProtocolError::SchemaViolation)?;
        let canvas = ImageCanvas::of(
            (image.original_width, image.original_height),
            (image.sent.width, image.sent.height),
        )
        .ok_or(ProtocolError::SchemaViolation)?;
        self.fit_image_canvas();
        let catalog_prompt = if auto_catalog {
            if !self
                .config
                .catalogs
                .iter()
                .any(|candidate| candidate.prompt.catalog_id == "default")
            {
                return Err(ProtocolError::InvalidPolicy);
            }
            let candidates = self
                .config
                .catalogs
                .iter()
                .map(|candidate| ImageCatalogCandidate {
                    entry: &candidate.prompt,
                    palette: candidate.resolved.palette(),
                })
                .collect::<Vec<_>>();
            Some(
                build_image_catalog_selection_prompt(
                    &image.sent,
                    &candidates,
                    self.config.language,
                    self.config.prompt_limits,
                )
                .map_err(|_| ProtocolError::SchemaViolation)?,
            )
        } else {
            None
        };
        self.image_ddl = Some(ImageDdlRecord {
            image,
            declared_ratio: canvas.declared_ratio,
            nearest_format_id: canvas.nearest_format_id.to_owned(),
            rounds: Vec::new(),
            before_review: None,
            drawing: None,
            dropped: Vec::new(),
        });
        match catalog_prompt {
            Some(prompt) => self.begin_llm(prompt, None, Vec::new(), events),
            None => self.write_image_ddl(events),
        }
    }

    /// A DDL declaring the image's ratio is fitted into the run's paper. The
    /// catalog chosen from the image brings its own options, so the fit is
    /// set again after it.
    fn fit_image_canvas(&mut self) {
        self.config.compiler.host = self
            .config
            .compiler
            .host
            .clone()
            .with_canvas_fit(Some(CanvasFit::Contain));
    }

    fn image_record(&self) -> Result<&ImageDdlRecord, ProtocolError> {
        self.image_ddl
            .as_ref()
            .ok_or(ProtocolError::InternalInvariant)
    }

    pub(super) fn image_canvas(&self) -> Result<ImageCanvas, ProtocolError> {
        let image = &self.image_record()?.image;
        ImageCanvas::of(
            (image.original_width, image.original_height),
            (image.sent.width, image.sent.height),
        )
        .ok_or(ProtocolError::InternalInvariant)
    }

    /// The request that writes the DDL, or with a drawing and the DDL it was
    /// drawn from, the request that reviews it.
    pub(super) fn image_prompt(
        &self,
        review: Option<(&PromptImage, &str)>,
    ) -> Result<LlmPrompt, ProtocolError> {
        let record = self.image_record()?;
        let context = ImageDdlContext {
            image: &record.image.sent,
            canvas: self.image_canvas()?,
            palette: self.config.compiler.host.palette(),
            limits: ImageDdlLimits::of(&self.config.compiler),
        };
        match review {
            None => {
                build_image_ddl_prompt(&context, self.config.language, self.config.prompt_limits)
            }
            Some((drawing, current)) => build_image_ddl_review_prompt(
                &context,
                drawing,
                current,
                self.config.language,
                self.config.prompt_limits,
            ),
        }
        .map_err(|_| ProtocolError::SchemaViolation)
    }

    fn write_image_ddl(&mut self, events: &mut Vec<PipelineEvent>) -> Result<(), ProtocolError> {
        let prompt = self.image_prompt(None)?;
        self.begin_llm(prompt, None, Vec::new(), events)
    }

    /// Read the catalog chosen from the image and write the DDL with it.
    pub(super) fn image_catalog_response(
        &mut self,
        response: &str,
        spent_ms: u64,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let Ok(selected) = parse_catalog_selection_response(response, self.config.prompt_limits)
        else {
            return self.failure(ProviderFailure::SchemaViolation, spent_ms, events);
        };
        if self
            .select_catalog(&selected.catalog_id, CatalogMode::AutoSelected)
            .is_err()
        {
            return self.failure(ProviderFailure::SchemaViolation, spent_ms, events);
        }
        self.fit_image_canvas();
        self.write_image_ddl(events)
    }

    /// An image stage whose attempts are spent: the default catalog, or what
    /// a writing or review stage leaves (`written`).
    pub(super) fn image_stage_failed(
        &mut self,
        stage: LlmStage,
        failure: ProviderFailure,
        detail: Option<&str>,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        if stage != LlmStage::SelectImageCatalog {
            return self.written_stage_failed(stage, failure, detail, events);
        }
        self.select_catalog("default", CatalogMode::AutoFallbackDefault)?;
        self.fit_image_canvas();
        self.event(
            events,
            "catalog_fallback",
            json!({"catalog_id": "default", "catalog_mode": "auto_fallback_default", "failure": failure}),
        )?;
        self.write_image_ddl(events)
    }
}

#[cfg(test)]
mod tests {
    use inku_ddl::ResolvedInstructionLanguage;
    use inku_score::{CANVAS_FORMAT_REGISTRY_ID, CanvasFit, Color, canvas_format_registry_digest};
    use serde_json::{Value, json};

    use super::*;
    use crate::authority::VariationAuthorityState;
    use crate::core_boundary::{ClipPolicy, ResolvedHostOptions};
    use crate::focused_flow::{ack, config, envelope, event, run, run_error, tags};
    use crate::image_ddl::tests::{a4_compiler, palette};
    use crate::machine::written::DRAW_IMAGE_REVIEW;
    use crate::machine::{
        AuthoringInput, CatalogCandidate, ImageConfig, PipelineConfig, PipelineInput,
        PipelinePhase, PipelineRenderCanvas, PipelineRenderOptions, StepOutput,
    };
    use crate::prompts::DescriptionCatalogEntry;
    use crate::protocol::{DecimalU64, EffectResult};

    const GOOD: &str =
        "背景を黄で埋める。\n画面の横0.3、縦0.7の位置に、直径0.1の赤の塗りの円を1個置く。";
    const UNREAD: &str = "画面の横0.5、縦0.5の位置に、中くらいの赤い円を置く。";
    /// From the 2026-10-24 probe: a surface word written as a shape. The
    /// compile leaves the sentence out; until DDL engine 71 it stopped the work.
    const HEADLESS: &str =
        "画面の横0.0〜0.3、縦0.0〜1.0の範囲に、直径0.05の黒の薄い粒を30個散らす。";
    const REVIEWED: &str = "背景を黄で埋める。\n画面の横0.3、縦0.7の位置に、直径0.1の赤の塗りの円を1個置く。\n画面の横0.6、縦0.3の位置に、直径0.2の青の塗りの円を1個置く。";

    fn declared(ddl: &str) -> String {
        format!("画面比883:1277。\n{ddl}")
    }

    /// W003 as a host sends it: small enough to go at its own size.
    fn w003() -> ImageInput {
        ImageInput {
            sent: PromptImage {
                media_type: "image/jpeg".into(),
                width: 883,
                height: 1277,
                sha256: "a".repeat(64),
                byte_len: 300_000,
            },
            original_width: 883,
            original_height: 1277,
        }
    }

    /// A run on A4, the paper nearest W003, with the default catalog.
    fn image_config(review: bool) -> PipelineConfig {
        let mut pipeline_config = config();
        pipeline_config.language = ResolvedInstructionLanguage::Ja;
        pipeline_config.compiler = a4_compiler();
        pipeline_config.image = Some(ImageConfig { review });
        pipeline_config
    }

    fn start(pipeline_config: PipelineConfig, auto_catalog: bool) -> StepOutput {
        run(
            None,
            &envelope(
                None,
                PipelineInput::Start {
                    variation_id: "image".into(),
                    authoring_nonce: "image-1".into(),
                    config: Box::new(pipeline_config),
                    authority: VariationAuthorityState::new_direct_ddl(),
                    authoring: AuthoringInput::Image {
                        image: w003(),
                        auto_catalog,
                    },
                },
            ),
        )
    }

    fn reply(state: &PipelineSnapshot, result: EffectResult) -> StepOutput {
        run(
            Some(state),
            &envelope(Some(state), PipelineInput::EffectResult { result }),
        )
    }

    fn answer(state: &PipelineSnapshot, ddl: &str) -> StepOutput {
        let action = state.action.as_ref().unwrap();
        let identity = action.identity.clone();
        let response = json!({ "ddl": ddl }).to_string();
        let elapsed_ms = DecimalU64::new(20);
        let result = match action.tag.as_str() {
            "write_image_ddl" => EffectResult::ImageDdlWritten {
                identity,
                response,
                elapsed_ms,
            },
            "review_image_ddl" => EffectResult::ImageDdlReviewed {
                identity,
                response,
                elapsed_ms,
            },
            tag => panic!("no DDL is asked for by {tag}"),
        };
        reply(state, result)
    }

    fn drawing(width: u32, height: u32) -> PromptImage {
        PromptImage {
            media_type: "image/png".into(),
            width,
            height,
            sha256: "d".repeat(64),
            byte_len: 90_000,
        }
    }

    fn drawn(state: &PipelineSnapshot, drawing: PromptImage) -> EffectResult {
        let action = state.action.as_ref().unwrap();
        assert_eq!(action.tag, DRAW_IMAGE_REVIEW);
        EffectResult::ImageReviewDrawn {
            identity: action.identity.clone(),
            drawing,
        }
    }

    fn failed(state: &PipelineSnapshot) -> StepOutput {
        let identity = state.action.as_ref().unwrap().identity.clone();
        reply(
            state,
            EffectResult::ProviderFailed {
                identity,
                failure: ProviderFailure::TransportTimeout,
                elapsed_ms: DecimalU64::new(20),
            },
        )
    }

    fn rounds(state: &PipelineSnapshot) -> Vec<(LlmStage, bool, usize)> {
        state
            .image_ddl
            .as_ref()
            .unwrap()
            .rounds
            .iter()
            .map(|round| (round.stage, round.asked_again, round.problems))
            .collect()
    }

    fn committed_source(state: &PipelineSnapshot) -> &str {
        let action = state.action.as_ref().unwrap();
        assert_eq!(action.tag, "commit_visible_normalized_ddl");
        assert_eq!(action.payload["reason"], "image_ddl");
        action.payload["document"]["source"].as_str().unwrap()
    }

    #[test]
    fn a_work_from_an_image_is_reviewed_beside_its_drawing_and_committed_as_an_edit() {
        let state = start(image_config(true), false).snapshot;
        let action = state.action.as_ref().unwrap();
        assert_eq!(action.tag, "write_image_ddl");
        assert_eq!(action.payload["prompt"]["images"], json!([w003().sent]));
        assert_eq!(
            state.config.compiler.host.canvas_fit(),
            Some(CanvasFit::Contain)
        );

        let state = answer(&state, GOOD).snapshot;
        let action = state.action.as_ref().unwrap();
        assert_eq!(action.tag, DRAW_IMAGE_REVIEW);
        assert_eq!(
            (&action.payload["width"], &action.payload["height"]),
            (&json!(724), &json!(1024))
        );
        assert_eq!(action.payload["document"]["source"], declared(GOOD));
        assert!(matches!(
            state.phase,
            PipelinePhase::AwaitingImageReviewDrawing
        ));

        let state = reply(&state, drawn(&state, drawing(724, 1024))).snapshot;
        let action = state.action.as_ref().unwrap();
        assert_eq!(action.tag, "review_image_ddl");
        assert_eq!(
            action.payload["prompt"]["images"],
            json!([w003().sent, drawing(724, 1024)])
        );
        let message: Value =
            serde_json::from_str(action.payload["prompt"]["message"].as_str().unwrap()).unwrap();
        assert_eq!(message["current_ddl"], declared(GOOD));

        let reviewing = state;
        let state = answer(&reviewing, REVIEWED).snapshot;
        assert_eq!(committed_source(&state), declared(REVIEWED));
        let done = run(Some(&state), &envelope(Some(&state), ack(&state))).snapshot;
        // Every snapshot names the images and holds neither them nor a drawing.
        for snapshot in [&reviewing, &state, &done] {
            let saved = serde_json::to_string(snapshot).unwrap();
            for held in ["data:image", "base64", "<svg"] {
                assert!(!saved.contains(held), "{held}");
            }
        }
        assert!(
            matches!(done.phase, PipelinePhase::ScoreReady),
            "{:?}",
            done.phase
        );
        assert_eq!(
            rounds(&done),
            [
                (LlmStage::WriteImageDdl, false, 0),
                (LlmStage::ReviewImageDdl, false, 0)
            ]
        );
        let record = done.image_ddl.as_ref().unwrap();
        assert_eq!(record.nearest_format_id, "a4");
        assert_eq!(
            record.before_review.as_deref(),
            Some(declared(GOOD).as_str())
        );
        assert_eq!(record.drawing, Some(drawing(724, 1024)));
        assert!(done.image_fallback.is_none());
    }

    #[test]
    fn lines_the_compiler_did_not_draw_are_given_back_once() {
        let state = start(image_config(false), false).snapshot;
        let returned = answer(&state, &format!("{GOOD}\n{UNREAD}"));
        assert!(tags(&returned).contains(&"retry_scheduled"));
        let state = returned.snapshot;
        let action = state.action.as_ref().unwrap();
        assert_eq!(
            (action.tag.as_str(), action.identity.attempt),
            ("write_image_ddl", 2)
        );
        let message: Value =
            serde_json::from_str(action.payload["prompt"]["message"].as_str().unwrap()).unwrap();
        assert_eq!(message["compiler_feedback"]["problems"][0]["line"], UNREAD);
        assert!(state.provider_attempt().unwrap().unwrap().asked_again);
        assert!(state.image_fallback.is_some());

        // The answer to that request is not asked about again.
        let state = answer(&state, &format!("{GOOD}\n{UNREAD}")).snapshot;
        assert_eq!(
            committed_source(&state),
            declared(&format!("{GOOD}\n{UNREAD}"))
        );
        assert_eq!(
            rounds(&state),
            [
                (LlmStage::WriteImageDdl, false, 1),
                (LlmStage::WriteImageDdl, true, 1)
            ]
        );
        // Nor is the unread line completed without the image once committed.
        let done = run(Some(&state), &envelope(Some(&state), ack(&state))).snapshot;
        assert!(
            matches!(done.phase, PipelinePhase::ScoreReady),
            "{:?}",
            done.phase
        );
        assert!(done.action.is_none());
    }

    #[test]
    fn a_sentence_without_a_shape_is_asked_about_once_and_left_out_by_the_compile() {
        let ddl = format!("{GOOD}\n{HEADLESS}");
        let state = start(image_config(false), false).snapshot;
        let state = answer(&state, &ddl).snapshot;
        assert_eq!(state.action.as_ref().unwrap().identity.attempt, 2);
        assert!(state.image_fallback.is_some());
        let state = answer(&state, &ddl).snapshot;
        assert_eq!(committed_source(&state), declared(&ddl));
        assert!(state.image_ddl.as_ref().unwrap().dropped.is_empty());
        let done = run(Some(&state), &envelope(Some(&state), ack(&state))).snapshot;
        assert!(
            matches!(done.phase, PipelinePhase::ScoreReady),
            "{:?}",
            done.phase
        );
    }

    #[test]
    fn a_ddl_that_draws_nothing_after_asking_again_stops_the_run() {
        let state = start(image_config(true), false).snapshot;
        let state = answer(&state, HEADLESS).snapshot;
        assert_eq!(state.action.as_ref().unwrap().identity.attempt, 2);
        let output = answer(&state, HEADLESS);
        assert!(matches!(
            &output.snapshot.phase,
            PipelinePhase::Failed { reason } if reason == "image_ddl_undrawable"
        ));
        assert_eq!(event(&output, "failed").unwrap()["detail"], "undrawable");
        assert!(output.snapshot.action.is_none());
    }

    #[test]
    fn a_review_that_fails_commits_the_ddl_shown_beside_the_image() {
        let state = start(image_config(true), false).snapshot;
        let state = answer(&state, GOOD).snapshot;
        let state = reply(&state, drawn(&state, drawing(724, 1024))).snapshot;
        let state = failed(&state).snapshot;
        assert_eq!(state.action.as_ref().unwrap().identity.attempt, 2);
        let output = failed(&state);
        assert!(event(&output, "image_review_fallback").is_some());
        assert_eq!(committed_source(&output.snapshot), declared(GOOD));
    }

    #[test]
    fn a_drawing_the_host_could_not_make_commits_the_ddl_as_written() {
        let state = start(image_config(true), false).snapshot;
        let state = answer(&state, GOOD).snapshot;
        let identity = state.action.as_ref().unwrap().identity.clone();
        let output = reply(&state, EffectResult::ImageReviewUndrawn { identity });
        assert_eq!(
            event(&output, "image_review_skipped"),
            Some(&json!({"reason": "undrawn"}))
        );
        assert_eq!(committed_source(&output.snapshot), declared(GOOD));
    }

    #[test]
    fn a_drawing_of_another_size_or_type_is_refused() {
        let state = start(image_config(true), false).snapshot;
        let state = answer(&state, GOOD).snapshot;
        for wrong in [
            drawing(1024, 1024),
            PromptImage {
                media_type: "image/jpeg".into(),
                ..drawing(724, 1024)
            },
        ] {
            let error = run_error(
                Some(&state),
                &envelope(
                    Some(&state),
                    PipelineInput::EffectResult {
                        result: drawn(&state, wrong),
                    },
                ),
            );
            assert_eq!(error["payload"]["code"], "schema_violation");
        }
    }

    #[test]
    fn a_host_without_the_image_stages_cannot_start_one() {
        let mut pipeline_config = image_config(true);
        pipeline_config.image = None;
        let error = run_error(
            None,
            &envelope(
                None,
                PipelineInput::Start {
                    variation_id: "image".into(),
                    authoring_nonce: "image-1".into(),
                    config: Box::new(pipeline_config),
                    authority: VariationAuthorityState::new_direct_ddl(),
                    authoring: AuthoringInput::Image {
                        image: w003(),
                        auto_catalog: false,
                    },
                },
            ),
        );
        assert_eq!(error["payload"]["code"], "invalid_policy");
    }

    fn candidate(catalog_id: &str) -> CatalogCandidate {
        let mode = if catalog_id == "default" {
            CatalogMode::Default
        } else {
            CatalogMode::Explicit
        };
        CatalogCandidate {
            prompt: DescriptionCatalogEntry {
                catalog_id: catalog_id.into(),
                label: catalog_id.into(),
                description: format!("the {catalog_id} catalog"),
            },
            resolved: ResolvedHostOptions::new(
                "a4",
                CANVAS_FORMAT_REGISTRY_ID,
                canvas_format_registry_digest().unwrap(),
                catalog_id,
                mode,
                Color::White,
                palette(),
            )
            .unwrap(),
        }
    }

    #[test]
    fn the_catalog_chosen_from_the_image_keeps_the_drawing_fitted() {
        let mut pipeline_config = image_config(false);
        pipeline_config.catalogs = vec![candidate("default"), candidate("night")];
        let state = start(pipeline_config, true).snapshot;
        let action = state.action.as_ref().unwrap();
        assert_eq!(action.tag, "select_image_catalog");
        assert_eq!(action.payload["prompt"]["images"], json!([w003().sent]));
        let identity = action.identity.clone();
        let state = reply(
            &state,
            EffectResult::ImageCatalogSelected {
                identity,
                response: json!({"catalog_id": "night"}).to_string(),
                elapsed_ms: DecimalU64::new(20),
            },
        )
        .snapshot;
        assert_eq!(state.action.as_ref().unwrap().tag, "write_image_ddl");
        let host = &state.config.compiler.host;
        assert_eq!(host.resolved_catalog_id(), "night");
        assert_eq!(host.catalog_mode(), CatalogMode::AutoSelected);
        assert_eq!(host.canvas_fit(), Some(CanvasFit::Contain));
    }

    fn render_request() -> Value {
        let compiler = a4_compiler();
        let options = PipelineRenderOptions {
            resolved_color_map: inku_render::palette::default_color_map(),
            catalog_id: Some("default".into()),
            // The core draws at the drawing's size whatever a host gives.
            canvas: PipelineRenderCanvas {
                width: 1.0,
                height: 1.0,
            },
            canvas_aspect_id: "square".into(),
            svg_profile: inku_render::types::SvgProfile::Display,
            render_seed: Some(DecimalU64::new(7)),
            composition_seed: compiler.composition_seed,
            wild: false,
            error_policy: compiler.error_policy,
        };
        let clip = ClipPolicy {
            tolerance_pixels: 0.1,
            max_nodes: DecimalU64::new(50_000),
            max_path_elements: DecimalU64::new(200_000),
            max_flattened_points: DecimalU64::new(200_000),
            max_work: DecimalU64::new(10_000_000),
            max_output_vertices: DecimalU64::new(200_000),
        };
        json!({"options": options, "clip": clip})
    }

    fn review_svg(state: &PipelineSnapshot, request: &Value) -> Value {
        let answer = crate::byte_envelope::image_review_svg_owned(
            &serde_json::to_vec(state).unwrap(),
            &serde_json::to_vec(request).unwrap(),
        );
        serde_json::from_slice(&answer).unwrap()
    }

    #[test]
    fn the_host_draws_the_review_from_the_snapshot_at_the_drawing_size() {
        let started = start(image_config(true), false).snapshot;
        let state = answer(&started, GOOD).snapshot;
        let first = review_svg(&state, &render_request());
        let svg = first["svg"].as_str().unwrap();
        assert!(svg.starts_with("<svg"), "{first}");
        let head = &svg[..svg.find('>').unwrap()];
        assert!(head.contains("724") && head.contains("1024"), "{head}");
        assert_eq!(review_svg(&state, &render_request()), first);
        assert_eq!(
            review_svg(&started, &render_request()),
            json!({"error": "invalid_state"})
        );
        assert_eq!(
            review_svg(&state, &json!({"options": {}})),
            json!({"error": "invalid_request"})
        );
    }
}
