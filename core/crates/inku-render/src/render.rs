//! Coarse portable render boundary, SVG orchestration, and render metadata.

use std::collections::BTreeSet;
use std::fmt;

use crate::accepted_fills;
use crate::arrangement::{ArrangementRequest, expand_arrangement};
use crate::checked_performance::{
    CheckedPerformanceError, CheckedPerformanceWithResourcesError, resolve_checked_performance,
    resolve_checked_performance_with_resources_and_omissions,
};
use crate::determinism::hash01;
use crate::fills::{is_noncomputer_solid_fill, solid_mottle_filter, solid_mottle_filter_id};
use crate::ground::render_ground;
use crate::layers::render_presence_layer;
use crate::marks::{
    MarkContext, MarkError, render_closed_arc_pair_fill, render_instruction_with_line_centerline,
};
use crate::materials::{
    performance_touch_filter, performance_touch_filter_on_canvas, texture_filter,
};
use crate::palette::{default_color, work_color_assignment};
use crate::performance::PerformanceRequest;
pub use crate::render_fill_scopes::CompatFillClipPolicy;
use crate::render_fill_scopes::FillPaintForest;
use crate::support::{DEFAULT_SUPPORT, support_for_ground};
use crate::surface_geometry::mark_bbox;
use crate::surfaces::render_surface;
use crate::svg::{Document, Element, format_number};
use crate::types::{
    Canvas, CanvasGroundSpec, Instruction, InstructionMode, Primitive, RenderMetadata,
    RenderOutput, RenderRequest, Score, SurfaceTexture, SurfaceTextureMetadata, SvgProfile,
};
use crate::{RENDER_ENGINE_ID, RENDER_ENGINE_VERSION};

fn canvas_ground(score: &Score) -> Option<CanvasGroundSpec> {
    match &score.canvas {
        Canvas::Spec(canvas) => canvas
            .ground
            .as_ref()
            .filter(|ground| ground.material != crate::types::GroundMaterial::Plain)
            .cloned(),
        Canvas::Id(_) => None,
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RenderError {
    Mark(MarkError),
    CheckedPerformance(CheckedPerformanceError),
    ResourceAuthority(inku_score::SavedScoreResourceError),
    NonFiniteSvg,
    /// The canvas size is not finite and positive.
    InvalidCanvas,
    /// A value that sets renderer work lies outside its `score.schema.json` range.
    InvalidScore(&'static str),
    /// One performed mark spans more than [`MAX_MARK_EXTENT`] canvas lengths.
    MarkTooLarge {
        instruction_index: usize,
    },
    /// The drawn marks and their definitions exceed the document's allowance.
    OutputTooLarge {
        allowed_bytes: usize,
    },
}

impl fmt::Display for RenderError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Mark(error) => error.fmt(formatter),
            Self::CheckedPerformance(error) => {
                write!(
                    formatter,
                    "checked performance stopped: {:?}",
                    error.diagnostics
                )
            }
            Self::ResourceAuthority(error) => {
                write!(formatter, "invalid Score resource authority: {error:?}")
            }
            Self::NonFiniteSvg => formatter.write_str("rendered SVG contains a non-finite value"),
            Self::InvalidCanvas => formatter.write_str("canvas size must be finite and positive"),
            Self::InvalidScore(reason) => write!(formatter, "invalid Score: {reason}"),
            Self::MarkTooLarge { instruction_index } => write!(
                formatter,
                "a mark of instruction {instruction_index} spans more than \
                 {MAX_MARK_EXTENT} canvas lengths"
            ),
            Self::OutputTooLarge { allowed_bytes } => write!(
                formatter,
                "drawn marks exceed the output allowance of {allowed_bytes} bytes"
            ),
        }
    }
}

impl std::error::Error for RenderError {}

impl From<MarkError> for RenderError {
    fn from(value: MarkError) -> Self {
        Self::Mark(value)
    }
}

fn owns_surface(primitive: Primitive) -> bool {
    matches!(
        primitive,
        Primitive::Circle
            | Primitive::Ellipse
            | Primitive::Square
            | Primitive::Triangle
            | Primitive::Polygon
            | Primitive::Cloudform
    )
}

/// Build the JSON-compatible render metadata carried beside the SVG.
#[must_use]
pub fn build_render_metadata(score: &Score, profile: SvgProfile) -> RenderMetadata {
    let render_surface_textures = score
        .instructions
        .iter()
        .enumerate()
        .filter_map(|(instruction_index, instruction)| {
            let surface = instruction.surface.as_ref()?;
            (owns_surface(instruction.primitive)
                && !matches!(
                    surface.texture,
                    SurfaceTexture::None | SurfaceTexture::Solid
                ))
            .then_some(SurfaceTextureMetadata {
                instruction_index,
                texture: surface.texture,
                density: surface.density,
                opacity: surface.opacity,
            })
        })
        .collect::<Vec<_>>();
    RenderMetadata {
        render_engine_id: RENDER_ENGINE_ID.to_owned(),
        render_engine_version: RENDER_ENGINE_VERSION.to_owned(),
        render_texture_version: "1".to_owned(),
        render_texture_profile: profile,
        texture_degraded: profile == SvgProfile::Compat
            && (!render_surface_textures.is_empty()
                || score
                    .instructions
                    .iter()
                    .any(|instruction| instruction.ink_spread.is_some())),
        render_canvas_ground: canvas_ground(score),
        render_surface_textures,
        execution: None,
        resource_execution: None,
    }
}

fn safe_svg_id(value: &str) -> String {
    let mut safe = String::with_capacity(value.len());
    let mut separator = false;
    for character in value.chars() {
        if character.is_ascii_alphanumeric() || matches!(character, '_' | '.' | '-') {
            safe.push(character);
            separator = false;
        } else if !separator {
            safe.push('_');
            separator = true;
        }
    }
    let safe = safe.trim_matches(['.', '_', '-']);
    let safe = if safe.is_empty() { "item" } else { safe };
    if safe.starts_with(|character: char| character.is_ascii_alphabetic() || character == '_') {
        safe.to_owned()
    } else {
        format!("inku_{safe}")
    }
}

fn instruction_id(instruction: &Instruction, index: usize) -> String {
    safe_svg_id(&format!(
        "instruction_{index:03}_{}_{}",
        instruction.primitive.as_str(),
        instruction.color.as_str()
    ))
}

fn mark_id(instruction: &Instruction, instruction_index: usize, mark_index: usize) -> String {
    safe_svg_id(&format!(
        "mark_{instruction_index:03}_{mark_index:03}_{}",
        instruction.primitive.as_str()
    ))
}

fn background_color(
    request: &RenderRequest,
    assignment: &std::collections::BTreeMap<String, String>,
) -> String {
    let name = request.score.background.as_str();
    assignment
        .get(name)
        .or_else(|| request.options.resolved_color_map.get(name))
        .cloned()
        .unwrap_or_else(|| default_color(request.score.background).to_owned())
}

fn background_rect(request: &RenderRequest, color: &str) -> Element {
    Element::new("rect")
        .attr("id", "background")
        .attr("x", "0")
        .attr("y", "0")
        .attr("width", format_number(request.options.canvas.width))
        .attr("height", format_number(request.options.canvas.height))
        .attr("fill", color)
}

fn document_metadata(profile: SvgProfile) -> (String, String) {
    match profile {
        SvgProfile::Editable => (
            "inku render (editable SVG)".to_owned(),
            "Generated by inku. Groups and IDs are included for vector editing.".to_owned(),
        ),
        SvgProfile::Compat => (
            "inku render (compat SVG)".to_owned(),
            "Generated by inku. Portable SVG output.".to_owned(),
        ),
        SvgProfile::Display => (
            "inku render (display SVG)".to_owned(),
            "Generated by inku. Portable SVG output.".to_owned(),
        ),
        SvgProfile::Live => (
            "inku render (live SVG)".to_owned(),
            "Generated by inku. Editable's groups and IDs with the display appearance, for performing the work in time.".to_owned(),
        ),
    }
}

/// The most canvas lengths one performed mark may span, after its group transform.
///
/// Fill and texture scanlines stop at 4,096 per layer, but each scanline makes
/// one stroke per span inside the contour, so a wash cloudform 4,096 canvases
/// tall drew 122,960 strokes (a 302 MB SVG). Saved marks span at most 1.7.
pub const MAX_MARK_EXTENT: f64 = 8.0;

/// Serialized bytes the drawn marks and their definitions may reach.
///
/// Every mark adds a share to a fixed base, so the limit grows with the marks
/// a host authorized. Saved works stay far below it: at most 7 MB over 12,798
/// renders, and the Server measures about 16 KB per mark.
#[derive(Clone, Copy, Debug)]
struct OutputAllowance {
    per_mark: usize,
    allowed: usize,
    spent: usize,
}

impl Default for OutputAllowance {
    fn default() -> Self {
        Self::new(16 << 20, 64 << 10)
    }
}

impl OutputAllowance {
    const fn new(base: usize, per_mark: usize) -> Self {
        Self {
            per_mark,
            allowed: base,
            spent: 0,
        }
    }

    fn add_mark(&mut self) {
        self.allowed = self.allowed.saturating_add(self.per_mark);
    }

    fn spend<'a>(
        &mut self,
        elements: impl IntoIterator<Item = &'a Element>,
    ) -> Result<(), RenderError> {
        for element in elements {
            self.spent = self.spent.saturating_add(element.unescaped_len());
        }
        if self.spent > self.allowed {
            return Err(RenderError::OutputTooLarge {
                allowed_bytes: self.allowed,
            });
        }
        Ok(())
    }
}

/// Refuse a mark whose fills and textures would grow past any saved work.
fn check_mark_extent(
    instruction: &Instruction,
    context: MarkContext<'_>,
) -> Result<(), RenderError> {
    let limit = MAX_MARK_EXTENT * context.canvas.unit();
    match mark_bbox(instruction, context) {
        Some((_, _, width, height)) if !(width.abs() <= limit && height.abs() <= limit) => {
            Err(RenderError::MarkTooLarge {
                instruction_index: context.instruction_index,
            })
        }
        _ => Ok(()),
    }
}

/// Refuse a request whose canvas or Score values no host could have produced.
///
/// Both entry points check this before any expansion, because the work of
/// several texture and ground passes grows with these values.
fn validate_request(request: &RenderRequest) -> Result<(), RenderError> {
    let canvas = request.options.canvas;
    if !(canvas.width.is_finite()
        && canvas.height.is_finite()
        && canvas.width > 0.0
        && canvas.height > 0.0)
    {
        return Err(RenderError::InvalidCanvas);
    }
    request
        .score
        .validate_work_ranges()
        .map_err(RenderError::InvalidScore)
}

/// Absolute maxima for [`render`], the entry that receives no host authority.
///
/// Its hosts coerce a legacy Score to their own limits first. The Server lets
/// an administrator raise each limit to at most 100,000 (a typo guard), so
/// marks and instructions stop there. Anchors and groups stop at 4,096, the
/// Server's maximum for anchors and transform groups in new works, because
/// scheduling compares every pair of groups with their anchor lists. Only the
/// dimensions that legacy demand counts are bounded.
fn absolute_render_policy() -> inku_score::HardResourcePolicy {
    let maximum = inku_score::ResourceDemand {
        logical_objects: u64::MAX,
        primitive_marks: 100_000,
        object_templates: 100_000,
        maximum_per_template_primitive_marks: u64::MAX,
        maximum_resolved_count: u64::MAX,
        template_nodes: u64::MAX,
        anchor_instances: 4_096,
        transform_instances: 4_096,
        placement_instances: 4_096,
        fill_instances: 4_096,
    };
    inku_score::HardResourcePolicy {
        identity: "inku.render.absolute.v1".to_owned(),
        budget: inku_score::ResourceBudget { maximum },
    }
}

/// Render a canonical Score through the complete portable request boundary.
///
/// This entry takes no host resource authority. Its hosts coerce the Score to
/// their limits first, and it refuses only what no host limit allows (an
/// arrangement count of 4.3 billion kept it computing positions for more than
/// 20 minutes). Untrusted Scores go through [`render_with_resources`].
pub fn render(request: RenderRequest) -> Result<RenderOutput, RenderError> {
    validate_request(&request)?;
    let absolute = absolute_render_policy();
    inku_score::check_legacy_resource_demand(
        &request.score,
        &absolute,
        inku_score::OperationalResourceBudget(absolute.budget),
    )
    .map_err(RenderError::ResourceAuthority)?;
    render_impl(request, None, &[], OutputAllowance::default())
}

/// Render a typed Score with independently authorized resource policies.
/// The saved snapshot is checked against these authorities before expansion.
pub fn render_with_resources(
    request: RenderRequest,
    hard_policy: &inku_score::HardResourcePolicy,
    operational_budget: inku_score::OperationalResourceBudget,
    clip_policy: CompatFillClipPolicy,
) -> Result<RenderOutput, RenderError> {
    validate_request(&request)?;
    let mut omitted = std::collections::BTreeMap::new();
    loop {
        let excluded = omitted.keys().copied().collect::<Vec<_>>();
        let mut output = render_impl(
            request.clone(),
            Some((hard_policy, operational_budget, clip_policy)),
            &excluded,
            OutputAllowance::default(),
        )?;
        let mut changed = false;
        if let Some(execution) = &mut output.metadata.execution {
            for diagnostic in &execution.diagnostics {
                if matches!(
                    diagnostic.reason,
                    inku_score::ScoreExecutionReason::FillClipUnsupported
                        | inku_score::ScoreExecutionReason::FillClipLimitExceeded
                ) && let std::collections::btree_map::Entry::Vacant(entry) =
                    omitted.entry(diagnostic.instruction_index)
                {
                    entry.insert(diagnostic.clone());
                    changed = true;
                }
            }
            if !changed {
                execution.diagnostics.extend(omitted.into_values());
                return Ok(output);
            }
        } else {
            return Ok(output);
        }
        // Each retry removes at least one complete atomic source/group. Reuse
        // the saved recipes and owner seeds to resolve relations without that
        // target, rather than leaving a prior translation toward missing paint.
    }
}

/// Perform the Score, draw every performed instruction, then assemble layers.
///
/// Performance resolves groups and relations first. Each performed
/// instruction then expands its arrangement and draws its marks; fill scopes
/// are clipped as a whole afterwards, with `omitted_instructions` excluded by
/// the caller's retry. Plate tone, presence and ground complete the layers,
/// and the document is serialized once. Every mark's extent is checked before
/// it is drawn, and what it draws is charged to `allowance`.
fn render_impl(
    request: RenderRequest,
    resources: Option<(
        &inku_score::HardResourcePolicy,
        inku_score::OperationalResourceBudget,
        CompatFillClipPolicy,
    )>,
    omitted_instructions: &[usize],
    mut allowance: OutputAllowance,
) -> Result<RenderOutput, RenderError> {
    let source_score = request.score.clone();
    let profile = request.options.svg_profile;
    let assignment = work_color_assignment(
        &request.options.resolved_color_map,
        request.options.render_seed,
        request.options.catalog_id.as_deref(),
    );
    let background = background_color(&request, &assignment);
    let performance_request = PerformanceRequest {
        score: &request.score,
        performance_seed: request.options.render_seed,
        composition_seed: request.options.composition_seed,
        canvas: Some(request.options.canvas),
    };
    let mut performance = match resources {
        Some((hard, operational, _)) => resolve_checked_performance_with_resources_and_omissions(
            performance_request,
            request.options.error_policy,
            hard,
            operational,
            omitted_instructions,
        )
        .map_err(|error| match error {
            CheckedPerformanceWithResourcesError::Resources(error) => {
                RenderError::ResourceAuthority(error)
            }
            CheckedPerformanceWithResourcesError::Performance(error) => {
                RenderError::CheckedPerformance(error)
            }
        }),
        None => resolve_checked_performance(performance_request, request.options.error_policy)
            .map_err(RenderError::CheckedPerformance),
    }?;
    let ground = canvas_ground(&performance.score);
    let support = ground.as_ref().map_or(DEFAULT_SUPPORT, |ground| {
        support_for_ground(ground.material)
    });
    let oil_fill_pass_limit = crate::fills::oil_fill_pass_limit(&performance.score.instructions);
    let mut ordered = performance
        .performed_instructions()
        .enumerate()
        .collect::<Vec<_>>();
    // Carve marks remove paint, so they follow every additive mark. The sort is
    // stable, so each part keeps its performed order.
    ordered.sort_by_key(|(_, (instruction, _))| instruction.mode_ == InstructionMode::Carve);
    let placement_seed = request
        .options
        .composition_seed
        .or(request.options.render_seed);
    let structured = profile != SvgProfile::Display;
    let mut content = Element::new("g").attr("id", "layer_10_content");
    let has_fill_scopes = !performance.fill_scopes.is_empty();
    let mut fill_forest = FillPaintForest::new(performance.fill_scopes.len());
    let mut scoped_touch_filter = None;
    let use_filters = matches!(profile, SvgProfile::Display | SvgProfile::Live);
    let mut material_definitions = Vec::new();
    if use_filters {
        for weight in [
            crate::types::Weight::Pencil,
            crate::types::Weight::Crayon,
            crate::types::Weight::Chalk,
            crate::types::Weight::BrushThick,
            crate::types::Weight::Drypoint,
        ] {
            if performance
                .score
                .instructions
                .iter()
                .any(|instruction| instruction.weight == weight)
                && let Some(filter) = texture_filter(weight, request.options.canvas)
            {
                material_definitions.push(filter);
            }
        }
        if let Some(seed) = request.options.render_seed {
            if profile == SvgProfile::Live {
                // A host draws each instruction group on its own, and a group
                // drawn alone does not inherit its ancestors' filters.
                let (filter_id, filter) =
                    performance_touch_filter_on_canvas(seed, request.options.canvas);
                scoped_touch_filter = Some(filter_id);
                material_definitions.push(filter);
            } else {
                let (filter_id, filter) = performance_touch_filter(seed, request.options.canvas);
                if has_fill_scopes {
                    scoped_touch_filter = Some(filter_id.clone());
                } else {
                    content.set_attr("filter", format!("url(#{filter_id})"));
                }
                material_definitions.push(filter);
            }
        }
    }
    if profile != SvgProfile::Compat {
        for weight in accepted_fills::BRUSH_TILE_WEIGHTS {
            if performance
                .score
                .instructions
                .iter()
                .any(|instruction| accepted_fills::uses_brush_tile(instruction, weight))
                && let Some(tile) = accepted_fills::brush_tile_definition(weight)
            {
                material_definitions.push(tile);
            }
        }
    }
    let mut surface_definitions = Vec::new();
    let mut closed_arc_pair_spread_marks = BTreeSet::new();
    for (performed_index, (instruction, performed)) in ordered {
        let instruction_index = performed.instruction_index;
        let instruction_seed_override = performed.seed_override;
        let instruction_transform = performed.transform;
        let fill_scope = performed.fill_scope_index;
        let line_centerline = performed.line_centerline.as_deref();
        let expanded = if instruction.arrangement.is_some() {
            expand_arrangement(ArrangementRequest {
                instruction,
                placement_seed,
                performance_seed: request.options.render_seed,
                canvas: Some(request.options.canvas),
            })
        } else {
            vec![instruction.clone()]
        };
        let mut instruction_group = Element::new("g");
        if structured {
            instruction_group.set_attr("id", instruction_id(instruction, instruction_index));
        }
        if expanded.len() == 1
            && let Some(follower_performed_index) = performed.closed_arc_pair_follower
            && let Some(follower) = performance.score.instructions.get(follower_performed_index)
            && let Some(follower_performed) = performance.performed.get(follower_performed_index)
            && follower.arrangement.is_none()
            && follower.mode_ == instruction.mode_
            && follower_performed.fill_scope_index == fill_scope
        {
            let first_context = MarkContext {
                canvas: request.options.canvas,
                color_map: &request.options.resolved_color_map,
                work_assignment: &assignment,
                render_seed: request.options.render_seed,
                instruction_seed_override,
                instruction_index,
                mark_index: 0,
                wild: request.options.wild,
                use_filters,
                profile,
                support,
                geometry_transform: instruction_transform.in_pixels(request.options.canvas.unit()),
                oil_fill_pass_limit,
            };
            let follower_context = MarkContext {
                instruction_seed_override: follower_performed.seed_override,
                instruction_index: follower_performed.instruction_index,
                geometry_transform: follower_performed
                    .transform
                    .in_pixels(request.options.canvas.unit()),
                ..first_context
            };
            check_mark_extent(instruction, first_context)?;
            check_mark_extent(follower, follower_context)?;
            if let Some(fill) =
                render_closed_arc_pair_fill(instruction, first_context, follower, follower_context)?
            {
                if follower.ink_spread.is_some() {
                    closed_arc_pair_spread_marks.insert(performed_index);
                    closed_arc_pair_spread_marks.insert(follower_performed_index);
                }
                let definitions_start = material_definitions.len();
                material_definitions.extend(accepted_fills::closed_contour_definitions(
                    follower,
                    follower_context,
                ));
                allowance.spend(
                    std::iter::once(&fill).chain(&material_definitions[definitions_start..]),
                )?;
                if structured || has_fill_scopes {
                    instruction_group.push(fill);
                } else {
                    content.push(fill);
                }
            }
        }
        for (mark_index, single) in expanded.iter().enumerate() {
            let context = MarkContext {
                canvas: request.options.canvas,
                color_map: &request.options.resolved_color_map,
                work_assignment: &assignment,
                render_seed: request.options.render_seed,
                instruction_seed_override,
                instruction_index,
                mark_index,
                wild: request.options.wild,
                use_filters,
                profile,
                support,
                geometry_transform: instruction_transform.in_pixels(request.options.canvas.unit()),
                oil_fill_pass_limit,
            };
            check_mark_extent(single, context)?;
            allowance.add_mark();
            let definitions_start = (material_definitions.len(), surface_definitions.len());
            if profile != SvgProfile::Compat
                && owns_surface(single.primitive)
                && is_noncomputer_solid_fill(single)
                && single.weight != crate::types::Weight::OilPaint
                && !accepted_fills::active(single)
            {
                let (filter_id, seed) = solid_mottle_filter_id(single, context);
                material_definitions.push(solid_mottle_filter(&filter_id, seed));
            }
            material_definitions.extend(accepted_fills::definitions(single, context));
            let base_mark =
                render_instruction_with_line_centerline(single, context, line_centerline)?;
            let mark = if let Some(surface) = render_surface(single, context) {
                let mut combined = Element::new("g");
                combined.push(base_mark);
                combined.push(surface.group);
                surface_definitions.extend(surface.definitions);
                combined
            } else {
                base_mark
            };
            let mut mark = if closed_arc_pair_spread_marks.contains(&performed_index) {
                mark
            } else {
                crate::ink_spread::wrap(mark, single, context)
            };
            allowance.spend(
                std::iter::once(&mark)
                    .chain(&material_definitions[definitions_start.0..])
                    .chain(&surface_definitions[definitions_start.1..]),
            )?;
            if structured || has_fill_scopes {
                if structured {
                    mark.set_attr("id", mark_id(single, instruction_index, mark_index));
                }
                instruction_group.push(mark);
            } else {
                content.push(mark);
            }
        }
        if (has_fill_scopes || structured)
            && let Some(filter_id) = &scoped_touch_filter
        {
            instruction_group.set_attr("filter", format!("url(#{filter_id})"));
        }
        if has_fill_scopes {
            fill_forest.push(
                instruction_group,
                performed_index,
                fill_scope,
                &performance.fill_scopes,
            );
        } else if structured {
            content.push(instruction_group);
        }
    }
    if has_fill_scopes {
        let (_, _, clip_policy) =
            resources.expect("typed fill requires explicit resource authority");
        let mut definitions = material_definitions.clone();
        definitions.extend(surface_definitions.iter().cloned());
        let before = definitions.len();
        let (paint, diagnostics, omitted) = fill_forest.finish(
            &performance.fill_scopes,
            profile,
            &mut definitions,
            clip_policy,
            &performance.performed,
        );
        material_definitions.extend(definitions.into_iter().skip(before));
        for element in paint {
            content.push(element);
        }
        if let Some(execution) = &mut performance.execution {
            execution.diagnostics.extend(diagnostics);
            execution
                .rendered_instruction_indices
                .retain(|index| !omitted.contains(index));
        }
    }
    let is_print = ground
        .as_ref()
        .is_some_and(|ground| ground.material == crate::types::GroundMaterial::Mezzotint)
        || performance.score.instructions.iter().any(|instruction| {
            matches!(
                instruction.weight,
                crate::types::Weight::Burin | crate::types::Weight::Drypoint
            )
        });
    if is_print && let Some(seed) = request.options.render_seed {
        let mut plate_tone = Element::new("rect")
            .attr("id", "layer_15_plate_tone")
            .attr("x", "0")
            .attr("y", "0")
            .attr("width", format_number(request.options.canvas.width))
            .attr("height", format_number(request.options.canvas.height))
            .attr("fill", "#111111")
            .attr(
                "opacity",
                format_number(0.02 + hash01(0, seed, "plate-tone") * 0.04),
            );
        // Display's whole-content touch also moves the plate tone at the canvas
        // edges, except when the touch goes on each instruction group of a fill.
        if profile == SvgProfile::Live
            && !has_fill_scopes
            && let Some(filter_id) = &scoped_touch_filter
        {
            plate_tone.set_attr("filter", format!("url(#{filter_id})"));
        }
        content.push(plate_tone);
    }
    let presence = render_presence_layer(&performance.score, request.options.canvas, &assignment);
    let ground = ground.as_ref().and_then(|ground| {
        render_ground(
            ground,
            request.options.canvas,
            &background,
            request.options.render_seed,
        )
    });
    let mut document = Document::new(request.options.canvas);
    for definition in material_definitions {
        document.push_definition(definition);
    }
    if let Some(ground) = &ground {
        for definition in &ground.definitions {
            document.push_definition(definition.clone());
        }
    }
    for definition in surface_definitions {
        document.push_definition(definition);
    }
    if structured {
        let (title, description) = document_metadata(profile);
        let mut title_node = Element::new("title");
        title_node.push_text(title);
        document.push(title_node);
        let mut description_node = Element::new("desc");
        description_node.push_text(description);
        document.push(description_node);
        let mut metadata = Element::new("metadata").attr("id", "inku_metadata");
        metadata.push_text(format!(
            "{{\"generator\":\"inku\",\"svg_profile\":\"{}\"}}",
            match profile {
                SvgProfile::Display => "display",
                SvgProfile::Editable => "editable",
                SvgProfile::Compat => "compat",
                SvgProfile::Live => "live",
            }
        ));
        document.push(metadata);
        let mut artboard = Element::new("g").attr("id", "inku_artboard");
        let mut background_layer = Element::new("g").attr("id", "layer_00_background");
        background_layer.push(background_rect(&request, &background));
        artboard.push(background_layer);
        if let Some(ground) = ground.as_ref() {
            artboard.push(ground.group.clone());
        }
        artboard.push(content);
        let mut presence_content = Element::new("g").attr("id", "layer_20_presence");
        if let Some(presence) = presence {
            presence_content.push(presence);
        }
        artboard.push(presence_content);
        document.push(artboard);
    } else {
        document.push(background_rect(&request, &background));
        if let Some(ground) = ground {
            document.push(ground.group);
        }
        if let Some(presence) = presence {
            content.push(presence);
        }
        document.push(content);
    }
    let svg = document.serialize();
    // A non-finite f64 prints as `NaN`, `inf` or `-inf`. No element name, id or
    // class contains either word, and host colors are hex, so a match is a number.
    if svg.contains("NaN") || svg.contains("inf") {
        return Err(RenderError::NonFiniteSvg);
    }
    let mut metadata = build_render_metadata(&source_score, profile);
    if let Some(demand) = performance.resource_demand {
        use crate::types::{
            RenderResourceExecution, RenderResourceFailure, RenderResourceOmission,
        };
        use inku_score::SavedScoreResourceFailure;
        let omissions = performance
            .resource_diagnostics
            .into_iter()
            .map(|diagnostic| {
                let failure = match diagnostic.failure {
                    SavedScoreResourceFailure::BudgetExceeded(exceeded) => {
                        RenderResourceFailure::BudgetExceeded { exceeded }
                    }
                    SavedScoreResourceFailure::ArithmeticOverflow(dimension) => {
                        RenderResourceFailure::ArithmeticOverflow { dimension }
                    }
                    reason => {
                        return Err(RenderError::ResourceAuthority(
                            inku_score::SavedScoreResourceError {
                                owner: diagnostic.cause_owner,
                                reason,
                            },
                        ));
                    }
                };
                Ok(RenderResourceOmission {
                    owner: diagnostic.owner,
                    cause_owner: diagnostic.cause_owner,
                    failure,
                    disposition: diagnostic.disposition,
                })
            })
            .collect::<Result<Vec<_>, RenderError>>()?;
        metadata.resource_execution = Some(RenderResourceExecution {
            accounting_id: inku_score::RESOURCE_ACCOUNTING_ID.to_owned(),
            demand,
            omissions,
            relation_omissions: performance.relation_diagnostics,
        });
    }
    metadata.execution = performance.execution;
    Ok(RenderOutput { svg, metadata })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{CanvasSize, RenderOptions};

    #[test]
    fn marks_past_the_output_allowance_are_refused() {
        // Stands in for many marks within the extent limit that together would
        // draw hundreds of megabytes; a small allowance keeps the test fast.
        let request = RenderRequest {
            score: serde_json::from_str(
                r#"{"version":"0.9.0","instructions":[{"primitive":"circle",
                "center":[0.5,0.5],"radius":0.3,"filled":true}]}"#,
            )
            .expect("Score"),
            options: RenderOptions {
                resolved_color_map: std::collections::BTreeMap::new(),
                catalog_id: None,
                canvas: CanvasSize::new(1000.0, 1000.0),
                canvas_aspect_id: "square".to_owned(),
                svg_profile: SvgProfile::Display,
                render_seed: Some(7),
                composition_seed: None,
                wild: false,
                error_policy: Default::default(),
            },
        };
        let error = render_impl(request, None, &[], OutputAllowance::new(1_000, 10)).unwrap_err();
        assert_eq!(
            error,
            RenderError::OutputTooLarge {
                allowed_bytes: 1_010
            }
        );
    }
}
