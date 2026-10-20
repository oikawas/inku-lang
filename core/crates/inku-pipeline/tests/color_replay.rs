//! The answers the color stage's prototype recorded, painted again by the
//! core: each line of the JSON Lines file `INKU_COLOR_REPLAY_INPUT` names a
//! work's Score before the colors (its layer and plugin counts with it), its
//! nine paints and their names, its canvas and render seed, its description
//! and language, the main layer and the layers whose colors the laws stage
//! decided, and the prototype's answer. The Score the core paints with the
//! answer, its refusal, or that the run would not ask for the colors (no law
//! can be the main one), is written one line per work to
//! `INKU_COLOR_REPLAY_OUTPUT`. The prototype's Scores carry no printed plan,
//! so each layer stands for one printed sentence and nothing is printed. Its
//! records stay out of the repository.

use std::fmt::Write as _;

use inku_ddl::ResolvedInstructionLanguage;
use inku_ddl::work_plan::{WorkPlan, WorkPlanLayer, WorkPlanPluginCall};
use inku_pipeline::appearance::Seeds;
use inku_pipeline::colors::{
    ColorsContext, ColorsInput, LawsHandoff, PrintedPlan, build_colors_prompt, paint_colors,
};
use inku_pipeline::core_boundary::{ResolvedPaletteColorDto, ResolvedPaletteDto};
use inku_pipeline::prompts::PromptLimits;
use inku_score::{Color, Score, ScoreErrorPolicy};
use serde_json::{Value, json};

/// Limits wide enough for any of the prototype's descriptions.
const LIMITS: PromptLimits = PromptLimits {
    max_catalog_entries: 16,
    max_summary_bytes: 1024,
    max_catalog_serialized_bytes: 32768,
    max_source_bytes: 8192,
    max_response_bytes: 16384,
};

fn count(item: &Value, key: &str) -> usize {
    usize::try_from(item[key].as_u64().expect("a count")).expect("a small count")
}

#[test]
#[ignore = "reads the prototype's records from outside the repository"]
fn paints_the_recorded_answers_again() {
    let input = std::env::var("INKU_COLOR_REPLAY_INPUT").expect("an input file");
    let output = std::env::var("INKU_COLOR_REPLAY_OUTPUT").expect("an output file");
    let mut lines = String::new();
    for line in std::fs::read_to_string(input)
        .expect("readable input")
        .lines()
    {
        if line.trim().is_empty() {
            continue;
        }
        let item: Value = serde_json::from_str(line).expect("a JSON line");
        let score: Score = serde_json::from_value(item["score"].clone()).expect("a Score");
        let paint = |color: Color| {
            let code = item["colors"][color.as_str()].as_str().expect("a paint");
            let channel = |k: usize| u8::from_str_radix(&code[k..k + 2], 16).expect("hex");
            // The color stage reads the observed sRGB only.
            ResolvedPaletteColorDto {
                abstract_color: color,
                concrete_rgb: [channel(1), channel(3), channel(5)],
                oklch_lightness: 0.0,
            }
        };
        let observations: Vec<ResolvedPaletteColorDto> =
            Color::ALL.iter().map(|color| paint(*color)).collect();
        let palette = ResolvedPaletteDto {
            background: paint(score.background),
            black: paint(Color::Black),
            white: paint(Color::White),
            observations: Some(observations.try_into().expect("nine paints")),
            paints: Some(
                Color::ALL
                    .iter()
                    .map(|color| item["paints"][color.as_str()].as_str().map(str::to_owned))
                    .collect(),
            ),
        };
        let plugins = count(&item, "plugins");
        let layers = count(&item, "layers") - plugins;
        let printed = PrintedPlan {
            plan: WorkPlan {
                plugins: vec![WorkPlanPluginCall::default(); plugins],
                layers: vec![WorkPlanLayer::default(); layers],
                ..WorkPlan::default()
            },
            ranges: vec![None; layers],
            joints: vec![None; layers],
            numeric: vec![None; layers],
        };
        let handoff = LawsHandoff {
            main_layer: item["main_layer"]
                .as_u64()
                .map(|layer| usize::try_from(layer).expect("a layer")),
            fixed: item["fixed"]
                .as_object()
                .into_iter()
                .flatten()
                .map(|(layer, law)| {
                    (
                        layer.parse().expect("a layer"),
                        law.as_str().expect("a law").to_owned(),
                    )
                })
                .collect(),
        };
        let seeds = Seeds {
            render: item["render_seed"]
                .as_str()
                .map(|seed| seed.parse().expect("a seed")),
            composition: None,
        };
        let description = item["description"].as_str().expect("a description");
        let language = match item["language"].as_str() {
            Some("ja") => ResolvedInstructionLanguage::Ja,
            _ => ResolvedInstructionLanguage::En,
        };
        let context = ColorsContext::new(ColorsInput {
            score: &score,
            printed: &printed,
            handoff: &handoff,
            palette: &palette,
            canvas_format_id: item["canvas_format_id"].as_str().expect("a canvas"),
            seeds,
            error_policy: ScoreErrorPolicy::OmitAndContinue,
            description,
        });
        let row = match context {
            None => json!({"id": item["id"], "state": "no_context"}),
            // No law can be the main one: the run commits the document as it is.
            Some(context)
                if build_colors_prompt(description, &context, language, LIMITS).is_err() =>
            {
                json!({"id": item["id"], "state": "no_request"})
            }
            Some(context) => match paint_colors(&item["answer"], &context) {
                Ok((painted, notes)) => {
                    json!({"id": item["id"], "state": "painted", "score": painted, "notes": notes})
                }
                Err(refusal) => json!({
                    "id": item["id"], "state": "refused", "code": refusal.code, "reason": refusal.en
                }),
            },
        };
        writeln!(lines, "{row}").expect("a line");
    }
    std::fs::write(output, lines).expect("writable output");
}
