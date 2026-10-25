//! What a run that writes its DDL directly does with each answer, from an
//! image (the image tab, 2026-10-24) or from a description that is read and
//! drawn (2026-10-25).
//!
//! Each answer is compiled as the run compiles it; lines the compiler did not
//! draw as written are given back once; the DDL is shown to the model as the
//! host draws it and asked about once more; and the DDL the run is left with
//! is committed. The two routes differ in how an answer becomes a source, how
//! the requests are written and how the commit is authorized.

use serde_json::json;

use super::{
    DescriptionDdlRecord, ImageDdlRecord, PipelinePhase, PipelineRenderCanvas,
    PipelineRenderOptions, PipelineSnapshot, VisibleDocument, WrittenDdlRound, message_names,
    proposal,
};
use crate::core_boundary::{
    SerializableClipPolicy, compile_committed, render_delivery, render_delivery_with_svg_limit,
};
use crate::description_ddl::{
    DrawnFigure, parse_description_ddl_response, with_description_ddl_feedback,
};
use crate::image_ddl::{
    ImageDdlCheck, REVIEW_DRAWING_MEDIA_TYPE, check_image_document, image_ddl_source,
    parse_image_ddl_response, review_drawing_size, salvage_image_document, validate_image,
    with_image_ddl_feedback,
};
use crate::prompts::{LlmPrompt, LlmStage, PromptImage};
use crate::protocol::{PipelineEvent, ProtocolError, ProviderFailure};

/// The effect that asks the host to draw the written DDL for the model to see.
pub(super) const DRAW_IMAGE_REVIEW: &str = "draw_image_review";

/// Which run writes its DDL directly.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum Written {
    Image,
    Description,
}

impl Written {
    /// The word the route's events and failures begin with.
    fn prefix(self) -> &'static str {
        match self {
            Self::Image => "image",
            Self::Description => "description",
        }
    }

    /// Whether `stage` writes the DDL (the other stage reviews it).
    fn writes(stage: LlmStage) -> bool {
        matches!(
            stage,
            LlmStage::WriteImageDdl | LlmStage::WriteDescriptionDdl
        )
    }
}

/// The parts of a run's record each answer and drawing fills.
trait WrittenRecord {
    fn rounds(&mut self) -> &mut Vec<WrittenDdlRound>;
    fn before_review(&mut self) -> &mut Option<String>;
    fn drawing(&mut self) -> &mut Option<PromptImage>;
    fn dropped(&mut self) -> &mut Vec<String>;
}

impl WrittenRecord for ImageDdlRecord {
    fn rounds(&mut self) -> &mut Vec<WrittenDdlRound> {
        &mut self.rounds
    }
    fn before_review(&mut self) -> &mut Option<String> {
        &mut self.before_review
    }
    fn drawing(&mut self) -> &mut Option<PromptImage> {
        &mut self.drawing
    }
    fn dropped(&mut self) -> &mut Vec<String> {
        &mut self.dropped
    }
}

impl WrittenRecord for DescriptionDdlRecord {
    fn rounds(&mut self) -> &mut Vec<WrittenDdlRound> {
        &mut self.rounds
    }
    fn before_review(&mut self) -> &mut Option<String> {
        &mut self.before_review
    }
    fn drawing(&mut self) -> &mut Option<PromptImage> {
        &mut self.drawing
    }
    fn dropped(&mut self) -> &mut Vec<String> {
        &mut self.dropped
    }
}

impl PipelineSnapshot {
    fn written(&self) -> Result<Written, ProtocolError> {
        match (&self.image_ddl, &self.description_ddl) {
            (Some(_), None) => Ok(Written::Image),
            (None, Some(_)) => Ok(Written::Description),
            _ => Err(ProtocolError::InternalInvariant),
        }
    }

    fn written_record(&mut self) -> Result<&mut dyn WrittenRecord, ProtocolError> {
        if let Some(record) = self.image_ddl.as_mut() {
            return Ok(record);
        }
        match self.description_ddl.as_mut() {
            Some(record) => Ok(record),
            None => Err(ProtocolError::InternalInvariant),
        }
    }

    /// An answer's source and the figures it names.
    fn written_source(
        &self,
        written: Written,
        response: &str,
    ) -> Result<Option<(String, Vec<DrawnFigure>)>, ProtocolError> {
        let limits = self.config.prompt_limits;
        Ok(match written {
            Written::Image => parse_image_ddl_response(response, limits)
                .ok()
                .map(|ddl| {
                    self.image_canvas().map(|canvas| {
                        (
                            image_ddl_source(&ddl, canvas, self.config.language),
                            Vec::new(),
                        )
                    })
                })
                .transpose()?,
            Written::Description => parse_description_ddl_response(response, limits)
                .ok()
                .map(|(ddl, figures)| {
                    self.description_ddl_source(&ddl)
                        .map(|source| (source, figures))
                })
                .transpose()?,
        })
    }

    /// Read a DDL written or reviewed. Lines the compiler did not draw are
    /// given back once; then the DDL is kept, or, when it draws nothing, the
    /// drawable DDL kept before it.
    pub(super) fn written_ddl_response(
        &mut self,
        stage: LlmStage,
        response: &str,
        spent_ms: u64,
        total: u64,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let written = self.written()?;
        let Some((source, figures)) = self.written_source(written, response)? else {
            return self.failure(ProviderFailure::SchemaViolation, spent_ms, events);
        };
        let Ok(candidate) = self.new_document(source) else {
            return self.failure(ProviderFailure::SchemaViolation, spent_ms, events);
        };
        let Ok(check) = self.check_written(&candidate) else {
            return self.failure(ProviderFailure::SemanticViolation, spent_ms, events);
        };
        let action = self.action.as_ref().ok_or(ProtocolError::InvalidState)?;
        let asked_again = message_names(&action.payload, "compiler_feedback");
        let prompt: LlmPrompt = serde_json::from_value(action.payload["prompt"].clone())
            .map_err(|_| ProtocolError::InternalInvariant)?;
        self.written_record()?.rounds().push(WrittenDdlRound {
            stage,
            prompt_id: prompt.prompt_id.clone(),
            prompt_digest: prompt.prompt_digest.clone(),
            asked_again,
            problems: check.problems.len(),
            instructions: check.instructions,
            figures,
        });
        if !check.problems.is_empty()
            && !asked_again
            && self.ask_written_again(stage, prompt, &candidate, &check, total, events)?
        {
            return Ok(());
        }
        self.action = None;
        let usable = self.usable_written_document(&candidate, &check)?;
        let prefix = written.prefix();
        if Written::writes(stage) {
            match usable.or_else(|| self.image_fallback.take()) {
                Some(document) => self.after_written(written, document, events),
                // Nothing draws even after asking again: the run stops rather
                // than save an empty work.
                None => {
                    self.phase = PipelinePhase::Failed {
                        reason: format!("{prefix}_ddl_undrawable"),
                    };
                    self.event(
                        events,
                        "failed",
                        json!({"stage": stage, "reason": ProviderFailure::SemanticViolation, "detail": "undrawable"}),
                    )
                }
            }
        } else {
            let document = match usable {
                Some(document) => document,
                None => {
                    self.event(
                        events,
                        &format!("{prefix}_review_fallback"),
                        json!({"stage": stage, "reason": "undrawable"}),
                    )?;
                    self.image_fallback
                        .take()
                        .ok_or(ProtocolError::InternalInvariant)?
                }
            };
            self.commit_written(written, document, events)
        }
    }

    fn check_written(&self, candidate: &VisibleDocument) -> Result<ImageDdlCheck, ProtocolError> {
        check_image_document(
            &candidate.document()?,
            &self.config.definitions,
            &self.config.compiler,
        )
        .map_err(|_| ProtocolError::SemanticViolation)
    }

    /// Ask once more with the lines the compiler did not draw, within the
    /// stage's budget. A drawable candidate is kept for a failed answer.
    fn ask_written_again(
        &mut self,
        stage: LlmStage,
        prompt: LlmPrompt,
        candidate: &VisibleDocument,
        check: &ImageDdlCheck,
        total: u64,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<bool, ProtocolError> {
        let written = self.written()?;
        let attempt = self
            .action
            .as_ref()
            .ok_or(ProtocolError::InvalidState)?
            .identity
            .attempt;
        let Some(next) = self
            .retry_policy(stage)
            .next_budgeted_attempt(attempt, total)
        else {
            return Ok(false);
        };
        let limits = self.config.prompt_limits;
        let again = match written {
            Written::Image => {
                with_image_ddl_feedback(prompt, &candidate.source, &check.problems, limits)
            }
            Written::Description => {
                let read = self
                    .description_ddl
                    .as_ref()
                    .is_some_and(|record| record.reading.is_some());
                with_description_ddl_feedback(
                    prompt,
                    &candidate.source,
                    &check.problems,
                    read,
                    limits,
                )
            }
        };
        let Ok(again) = again else {
            return Ok(false);
        };
        if check.drawable {
            self.image_fallback = Some(candidate.clone());
        }
        self.reissue(stage, again, None, total, next, events)?;
        self.event(
            events,
            "retry_scheduled",
            json!({
                "identity": self.action.as_ref().unwrap().identity,
                "failure": ProviderFailure::SemanticViolation,
                "detail": format!("{}_ddl_problems", written.prefix()),
                "problems": check.problems.len(),
            }),
        )?;
        Ok(true)
    }

    /// The candidate when it draws; else the candidate without the lines
    /// that each alone stop the whole work, when what is left draws.
    fn usable_written_document(
        &mut self,
        candidate: &VisibleDocument,
        check: &ImageDdlCheck,
    ) -> Result<Option<VisibleDocument>, ProtocolError> {
        if check.drawable {
            return Ok(Some(candidate.clone()));
        }
        let Ok(Some((salvaged, dropped))) = salvage_image_document(
            &candidate.document()?,
            &self.config.definitions,
            &self.config.compiler,
        ) else {
            return Ok(None);
        };
        self.written_record()?.dropped().extend(dropped);
        Ok(Some(VisibleDocument::from_document(&salvaged)))
    }

    /// Show the written DDL's drawing to the model when the run reviews, else
    /// commit it.
    fn after_written(
        &mut self,
        written: Written,
        document: VisibleDocument,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let review = match written {
            Written::Image => self.config.image.is_some_and(|config| config.review),
            Written::Description => self
                .config
                .description_ddl
                .is_some_and(|config| config.review),
        };
        let size = review_drawing_size(self.config.compiler.host.canvas_format_id());
        let Some((width, height)) = size.filter(|_| review) else {
            return self.commit_written(written, document, events);
        };
        *self.written_record()?.before_review() = Some(document.source.clone());
        self.image_fallback = Some(document.clone());
        self.phase = PipelinePhase::AwaitingImageReviewDrawing;
        self.delivery = None;
        let payload = json!({
            "document": document,
            "canvas_format_id": self.config.compiler.host.canvas_format_id(),
            "width": width,
            "height": height,
        });
        self.issue(DRAW_IMAGE_REVIEW, payload, 0, events)
    }

    /// The host's drawing of the written DDL: ask for the review with it.
    pub(super) fn review_drawn(
        &mut self,
        drawing: PromptImage,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        if !matches!(self.phase, PipelinePhase::AwaitingImageReviewDrawing) {
            return Err(ProtocolError::StaleResult);
        }
        let action = self.action.as_ref().ok_or(ProtocolError::StaleResult)?;
        let size = (
            action.payload["width"].as_u64(),
            action.payload["height"].as_u64(),
        );
        if validate_image(&drawing).is_err()
            || drawing.media_type != REVIEW_DRAWING_MEDIA_TYPE
            || size
                != (
                    Some(u64::from(drawing.width)),
                    Some(u64::from(drawing.height)),
                )
        {
            return Err(ProtocolError::SchemaViolation);
        }
        let document = self
            .image_fallback
            .clone()
            .ok_or(ProtocolError::InternalInvariant)?;
        self.action = None;
        *self.written_record()?.drawing() = Some(drawing.clone());
        let written = self.written()?;
        let prompt = match written {
            Written::Image => self.image_prompt(Some((&drawing, &document.source))),
            Written::Description => self.description_ddl_prompt(Some((&drawing, &document.source))),
        };
        match prompt {
            Ok(prompt) => self.begin_llm(prompt, None, Vec::new(), events),
            Err(_) => {
                self.event(
                    events,
                    &format!("{}_review_skipped", written.prefix()),
                    json!({"reason": "prompt"}),
                )?;
                self.image_fallback = None;
                self.commit_written(written, document, events)
            }
        }
    }

    /// The host could not draw the written DDL: commit it without a review.
    pub(super) fn review_undrawn(
        &mut self,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        if !matches!(self.phase, PipelinePhase::AwaitingImageReviewDrawing) {
            return Err(ProtocolError::StaleResult);
        }
        self.action = None;
        let document = self
            .image_fallback
            .take()
            .ok_or(ProtocolError::InternalInvariant)?;
        let written = self.written()?;
        self.event(
            events,
            &format!("{}_review_skipped", written.prefix()),
            json!({"reason": "undrawn"}),
        )?;
        self.commit_written(written, document, events)
    }

    /// A writing or review stage whose attempts are spent: the kept DDL, or,
    /// when nothing was written, a failed run.
    pub(super) fn written_stage_failed(
        &mut self,
        stage: LlmStage,
        failure: ProviderFailure,
        detail: Option<&str>,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        let written = self.written()?;
        let prefix = written.prefix();
        let mut payload = json!({"stage": stage, "reason": failure});
        if let Some(detail) = detail {
            payload["detail"] = json!(detail);
        }
        if Written::writes(stage) {
            match self.image_fallback.take() {
                Some(document) => {
                    self.event(events, &format!("{prefix}_ddl_fallback"), payload)?;
                    self.after_written(written, document, events)
                }
                None => {
                    self.phase = PipelinePhase::Failed {
                        reason: format!("{prefix}_ddl_failed"),
                    };
                    self.event(events, "failed", payload)
                }
            }
        } else {
            let document = self
                .image_fallback
                .take()
                .ok_or(ProtocolError::InternalInvariant)?;
            self.event(events, &format!("{prefix}_review_fallback"), payload)?;
            self.commit_written(written, document, events)
        }
    }

    /// Commit the DDL a run is left with: an image's as a DDL edit, a
    /// description's as a description's work, whose description stays the
    /// work's own and can be drawn again.
    fn commit_written(
        &mut self,
        written: Written,
        document: VisibleDocument,
        events: &mut Vec<PipelineEvent>,
    ) -> Result<(), ProtocolError> {
        self.image_fallback = None;
        let revision = self.authority.revision();
        let (outcome, reason) = match written {
            Written::Image => (
                self.authority
                    .propose_committed_user_ddl_mutation(revision, true),
                "image_ddl",
            ),
            Written::Description => (
                self.authority.propose_stage1_result_commit(revision),
                "description_ddl",
            ),
        };
        let next = proposal(outcome)?.ok_or(ProtocolError::InternalInvariant)?;
        self.commit_document(document, next, reason, events)
    }

    /// The SVG a host makes the `draw_image_review` PNG from: the action's DDL
    /// compiled as the run compiles it, and drawn with the host's render
    /// options on the run's paper at the drawing's size. The host gives the
    /// options it draws the work with (its colour map for the run's catalog,
    /// its render seed); the canvas is set here.
    pub fn image_review_svg(
        &self,
        mut options: PipelineRenderOptions,
        clip: SerializableClipPolicy,
        max_svg_bytes: Option<usize>,
    ) -> Result<String, ProtocolError> {
        self.validate()?;
        let (PipelinePhase::AwaitingImageReviewDrawing, Some(action)) = (&self.phase, &self.action)
        else {
            return Err(ProtocolError::InvalidState);
        };
        let document: VisibleDocument = serde_json::from_value(action.payload["document"].clone())
            .map_err(|_| ProtocolError::InternalInvariant)?;
        let (Some(width), Some(height)) = (
            action.payload["width"].as_f64(),
            action.payload["height"].as_f64(),
        ) else {
            return Err(ProtocolError::InternalInvariant);
        };
        let delivery = compile_committed(
            document.document()?,
            &self.config.definitions,
            &self.config.compiler,
        )
        .map_err(|_| ProtocolError::SemanticViolation)?;
        options.canvas = PipelineRenderCanvas { width, height };
        options.canvas_aspect_id = self.config.compiler.host.canvas_format_id().to_owned();
        let compiler = &self.config.compiler;
        match max_svg_bytes {
            Some(maximum) => {
                render_delivery_with_svg_limit(&delivery, options.into(), compiler, clip, maximum)
            }
            None => render_delivery(&delivery, options.into(), compiler, clip),
        }
        .map(|output| output.svg)
        .map_err(|_| ProtocolError::SemanticViolation)
    }
}
