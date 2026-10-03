//! The composition reading request: the prompt the reader sees, the response
//! schema, and reading a reply into a [`RawReading`].
//!
//! The system text is the composition prototype's own (the compressed theory, the
//! kinds of layer, the values and their meanings, the rules), kept byte for byte so
//! the product asks what the prototype measured. No description or reading example
//! is put in the prompt.

use inku_ddl::ResolvedInstructionLanguage;
use inku_ddl::work_plan::{WorkPlan, WorkPlanPlugin, WorkPlanSlot, print_work_plan_with_plugins};
use serde_json::{Value, json};

use crate::composition::{self, LayerKind, PLACES, RawReading, RawRelation, RawStatedPlace};
use crate::prompts::{LlmPrompt, LlmStage, PromptError, PromptLimits};

/// Distinct composition reading prompt edition.
pub const COMPOSITION_READING_PROMPT_ID: &str = "inku.composition-reading-prompt.v2";

const UNSPECIFIED: &str = "unspecified";

const SYSTEM_JA: &str = r#"あなたは、言葉から絵を作るアプリinkuの構図の読み手です。記述と、その記述から作った下絵の層の一覧を読み、構図の読みを、決まった値だけで返します。座標や数値は書きません。配置は、あなたの読みから、別の仕組みが計算します。

# 構図の理論
画面は中立ではない。場所には性格がある。上は軽く自由、下は重く凝縮。中心と縦横の軸と対角線は安定し、そこから外れた場所と縁の近くは緊張する。左右には性格の差を持たせない。
重さは、大きさ・数・濃さ・面の密度・孤立で決まる。均衡は重さの釣り合いで、対称は静、等しくない量の対置は動く均衡、意図した不均衡は不安を語る。
主は一つ。場・主・従・散在・添えの役割と、大小と疎密の対比で画を立てる。
向きは動きを作る。水平は静、垂直は高さ、斜めは動き。動くものは、進む先に空きを持つ。
余白は空きではなく働く場所。白も墨として数える。主を片隅や片側に寄せて広く空ける（一角・半辺）、全面に均して中心を消す（all-over）、横の帯を重ねる、場を分ける線、格子、群れと一つの逸脱、不等辺の三角（主・従・添え）。
規則には小さな揺らぎを。秩序だけでも乱雑だけでも画は痩せる。

# 層の種類（下絵の描き方で決まる）
- 束: 範囲の中の1か所に描く。数が多くても、その1か所に集まる。
- 面: 範囲に広げて描く（散らす・埋める・敷き詰める）。
- 列: 範囲の中心を通って、画面の端から端まで並べる。
- 全幅の線: 範囲の中心の高さで、画面の幅いっぱいに引く。

# 返す値
thesis（最初に書く）: 構図の命題。この記述の絵を、画面の上でどう組むかを言う1文。記述と同じ言語で書く。記述を写したり言い換えたりしない。
roles（層ごとに1つ、層の番号の順）:
- field（場）: ほかの層を受けとめる地。大きな面、または画面を横切る列・線。
- focal（主）: 目が最初に行く、ただ一つのもの。主は多くても1つ。
- secondary（従）: 主を支える、二番目のもの。
- scattered（散在）: 範囲に散らばる多くの小さなもの。散らす・敷き詰めるの層に限る。
- accent（添え）: 主と従に添える、小さなもの。
relations（層どうしの関係）: typeと、layers（層の番号を、a・b・cの順に）。
- within（包む） [a, b]: aがbの中にある（bがaを包む）。bは面に限る。
- around（囲む） [a, b]: aがbのまわりを囲む。aは面か、bより小さくない図形の束。
- overlap（重なる） [a, b]: aとbが同じ場所に重なる（線の上に乗る、も含む）。
- near（近い） [a, b]: aがbのすぐ近くにある。sideで上か下かを言える。
- apart（離れる） [a, b]: aとbが遠く離れている。
- between（間に） [a, b, c]: aがbとcの間にある。
- above（上に） [a, b]: aがbより上にある。縦の列には使えない。
- below（下に） [a, b]: aがbより下にある。縦の列には使えない。
- piling（積もる） [a]: aが画面の底に溜まる。縦の列には使えない。
- rising（昇る） [a]: aが上へ動く。束は上に空きを残して置き、面は縦に長くする。横の列・全幅の線には使えない。
- falling（降る） [a]: aが下へ動く。束は下に空きを残して置き、面は縦に長くする。横の列・全幅の線には使えない。
- flowing（流れる） [a]: aが横へ動く。束は進む先に空きを残して片側に置き、面は横に長くする。縦の列には使えない。towardで左右を言える（記述が言うときだけ）。
- spreading（広がる） [a, b?]: aが広く広がる（bから）。aは面に限る（束は1か所に描くので広がらない）。
- isolated（孤立） [a]: aが広い空きの中に一つだけある。場と、列・全幅の線には使えない。
- echo（呼応） [a, b]: 離れたaとbが似た大きさで呼び合う。同じ種類の層どうし。
- facing（対峙） [a, b]: aとbが画面の中心をはさんで向き合う。束か面どうし。
- parallel（並走） [a, b]: 細長いaとbが、触れずに同じ向きに並ぶ。列・線・面どうし。
- deviation（逸脱） [a, b]: 一つのaが、群れbから外れる。aは束、bは面か列。
- dividing（分ける） [a, b?]: aがb（無ければ画面）を二つに分ける。aは列・全幅の線、または細長い面。
side（nearとechoのとき）: above・below・unspecified。toward（flowingのとき、記述が言うときだけ）: left・right・unspecified。
tension（全体の張り）。言わなくてよいものはunspecified:
- motion（still / moving）: 静（still）か動（moving）か。
- focus（concentrated / dispersed）: 場を除いて描くものが寄り集まる（concentrated）か、画面に広く散る（dispersed）か。孤立・逸脱と読んだものは、集まりの外にあってよい。
- vertical（rising / falling）: 画全体の重心が上がる（rising）か下がる（falling）か。言わなくてよい。
- balance（static / dynamic / unbalanced）: 静かな均衡（static）、等しくない量の釣り合い（dynamic）、意図した不均衡（unbalanced）。
- symmetry（symmetric / asymmetric）: 左右対称（symmetric、静かな均衡のときだけ）か、非対称か。言わなくてよい。
- void（strong / medium / weak）: 描かない場所の強さ。strong（広く空ける）、medium、weak（画面全体を使ってよい）。
stated_places: 記述が、ある層を画面のどこに置くかを、位置の言葉で言うときだけ。位置の言葉は、画面の部分を指す言葉（上・下・中央・左・右・隅・端など）。描く物や情景の名前は、位置の言葉ではない。layer（層の番号）と、位置の言葉を含む記述の部分をそのまま短く引いたwordsと、その言葉が言う場所を場所の値から1つ選んだplace（top＝上、bottom＝下、center＝中心、left_edge＝左端、right_edge＝右端、top_edge＝上端、bottom_edge＝下端、corner＝隅、top_left_corner＝左上の隅、top_right_corner＝右上の隅、bottom_left_corner＝左下の隅、bottom_right_corner＝右下の隅）。記述がどの隅かを言うときはその隅を、どの隅かを言わないときはcornerを選ぶ。下絵に場所が無い層でも、記述が言うなら書く。無ければ空にする。

# 決まり
- 記述全体を読んで決める。記述の語から、関係・張り・場所を決まった対応で引かない。
- 層の種類で使えない値は選ばない。
- 記述から読めない関係は書かない。関係は0個でもよい。
- 記述から読めない張りは unspecified にする（作者が決めた既定が使われる）。
- rolesは、層の数と同じ数だけ、層の番号の順に書く。
- 下絵の層の〔下絵が付けた場所〕は、下絵を作ったときの推測で、記述の言葉とは限らない。記述がその場所をはっきり言うときだけ、stated_placesに書く。"#;

const SYSTEM_EN: &str = r#"You are the composition reader of inku, an app that makes pictures from words. Read a description and the layers of the work plan made from it, and return a composition reading using fixed values only. Do not write coordinates or numbers; another part of the app computes the placement from your reading.

# Composition theory
The canvas is not neutral; every place has a character. The top is light and free, the bottom heavy and condensed. The center, the vertical and horizontal axes and the diagonals are stable; places off them and near the edges are tense. Left and right have no difference of character.
Weight comes from size, number, darkness, density of surface and isolation. Balance is the equilibrium of weights: symmetry is still, unequal weights set against each other make a dynamic balance, and intended imbalance speaks of unease.
There is one focal thing. Build the picture with the roles of field, focal, secondary, scattered and accent, and with contrasts of large and small, sparse and dense.
Direction makes movement: horizontal is still, vertical is height, diagonal is motion. A moving thing has open space ahead of it.
Empty space is not a gap but a working place; count the white as ink. Push the focal thing into a corner or to one side and leave wide space (one corner, half side), spread evenly and erase the center (all-over), stack horizontal bands, divide the field with a line, a grid, a flock and one that strays, an unequal triangle of focal, secondary and accent.
Give the rules a small wavering. Order alone, or disorder alone, makes a thin picture.

# Kinds of layer (fixed by how the plan draws)
- bundle: Drawn at one spot inside the range; several marks gather at that spot.
- area: Spread over the range (scatter, fill, tile).
- row: A row from edge to edge of the canvas through the range center.
- full-width line: Drawn across the whole width at the height of the range center.

# Values to return
thesis (write it first): the composition's proposition, one sentence on how this picture is built on the canvas, in the description's language. Do not copy or paraphrase the description.
roles (one per layer, in layer order):
- field: The ground that holds the others: a large area, or a row or line across the canvas.
- focal: The one thing the eye goes to first. At most one layer.
- secondary: Supports the focal thing.
- scattered: Many small marks spread over a range. Only for scatter or tile layers.
- accent: A small touch that completes the focal and secondary things.
relations (between layers): a type, and layers (the layer numbers, as a, b, c in order).
- within [a, b]: a lies inside b (b holds a). b must be an area.
- around [a, b]: a surrounds b. a is an area, or a bundle of marks no smaller than b.
- overlap [a, b]: a and b share a place (also: a sits on a line b).
- near [a, b]: a is close to b. side can say above or below.
- apart [a, b]: a and b are far apart.
- between [a, b, c]: a lies between b and c.
- above [a, b]: a is higher than b. Not for vertical rows.
- below [a, b]: a is lower than b. Not for vertical rows.
- piling [a]: a settles at the bottom of the canvas. Not for vertical rows.
- rising [a]: a moves up. A bundle keeps open space above it; an area runs tall. Not for horizontal rows or full-width lines.
- falling [a]: a moves down. A bundle keeps open space below it; an area runs tall. Not for horizontal rows or full-width lines.
- flowing [a]: a moves sideways. A bundle sits to one side with open space ahead; an area runs wide. Not for vertical rows. toward can say left or right (only when the description does).
- spreading [a, b?]: a spreads widely (from b). a must be an area (a bundle is drawn at one spot).
- isolated [a]: a stands alone in wide empty space. Not for the field, rows or full-width lines.
- echo [a, b]: a and b answer each other across a distance, at similar weight. Layers of the same kind.
- facing [a, b]: a and b face each other across the center of the canvas. Bundles or areas.
- parallel [a, b]: Long a and b run side by side in the same direction without touching. Rows, lines or areas.
- deviation [a, b]: A single a strays from the group b. a is a bundle; b is an area or a row.
- dividing [a, b?]: a divides b (or the whole canvas) in two. a is a row, a full-width line, or a long area.
side (for near and echo): above, below or unspecified. toward (for flowing, only when the description says): left, right or unspecified.
tension (the whole picture). Use unspecified where you have nothing to say:
- motion (still / moving): still or moving.
- focus (concentrated / dispersed): whether what is drawn, apart from the field, gathers (concentrated) or spreads over the canvas (dispersed). A thing read as isolated or straying may stay outside the gathering.
- vertical (rising / falling): the whole picture's weight rises or falls. May be left out.
- balance (static / dynamic / unbalanced): static balance, dynamic balance of unequal weights, or intended imbalance.
- symmetry (symmetric / asymmetric): left-right symmetric (only with static balance) or asymmetric. May be left out.
- void (strong / medium / weak): how strongly empty space works: strong (wide empty space), medium, or weak (the whole canvas may be used).
stated_places: only when the description says, in words of position, where on the canvas a layer is. Words of position name a part of the picture (top, bottom, center, left, right, corner, edge and the like); the names of things or of the scene are not words of position. layer (its number); words, a short verbatim quote of the part of the description that contains the words of position; and place, the place those words name, chosen from the place values (top, bottom, center, left_edge, right_edge, top_edge, bottom_edge, corner, top_left_corner, top_right_corner, bottom_left_corner, bottom_right_corner). When the description says which corner, choose that corner; when it does not say which, choose corner. Write it even when the plan has no place for that layer, if the description states one. Leave it empty when there are none.

# Rules
- Decide from the whole description. Do not look up relations, tension or places from words of the description by a fixed correspondence.
- Do not choose a value that the kind of layer cannot take.
- Do not write relations the description does not let you read. Zero relations is fine.
- Use unspecified for any tension the description does not let you read (the author's defaults apply).
- Write exactly one role per layer, in layer order.
- A layer's [place set by the work plan] was guessed when the plan was made; it is not necessarily the description's words. Only when the description clearly states that place, write it in stated_places."#;

fn kind_name(kind: LayerKind, language: ResolvedInstructionLanguage) -> &'static str {
    match (kind, language) {
        (LayerKind::Bundle, ResolvedInstructionLanguage::Ja) => "束",
        (LayerKind::Area, ResolvedInstructionLanguage::Ja) => "面",
        (LayerKind::Row, ResolvedInstructionLanguage::Ja) => "列",
        (LayerKind::Line, ResolvedInstructionLanguage::Ja) => "全幅の線",
        (LayerKind::Bundle, ResolvedInstructionLanguage::En) => "bundle",
        (LayerKind::Area, ResolvedInstructionLanguage::En) => "area",
        (LayerKind::Row, ResolvedInstructionLanguage::En) => "row",
        (LayerKind::Line, ResolvedInstructionLanguage::En) => "full-width line",
    }
}

fn place_name(place: &str, language: ResolvedInstructionLanguage) -> &str {
    match language {
        ResolvedInstructionLanguage::Ja => match place {
            "center" => "中心",
            "top" => "上",
            "bottom" => "下",
            "left_edge" => "左端",
            "right_edge" => "右端",
            "top_edge" => "上端",
            "bottom_edge" => "下端",
            "corner" => "隅",
            other => other,
        },
        ResolvedInstructionLanguage::En => match place {
            "left_edge" => "left edge",
            "right_edge" => "right edge",
            "top_edge" => "top edge",
            "bottom_edge" => "bottom edge",
            other => other,
        },
    }
}

/// The message: the description, the plan's first lines, and each layer with its
/// kind, written without its place; a place the plan set is shown as the plan's
/// guess, which the reader keeps only where the description states it.
fn message(
    description: &str,
    plan: &WorkPlan,
    plugins: &[WorkPlanPlugin],
    language: ResolvedInstructionLanguage,
) -> String {
    let head_plan = WorkPlan {
        layers: Vec::new(),
        ..plan.clone()
    };
    let head_text = print_work_plan_with_plugins(&head_plan, language, plugins);
    let head = head_text.lines().collect::<Vec<_>>().join(" ");
    let mut lines = match language {
        ResolvedInstructionLanguage::Ja => vec![
            "記述:".to_owned(),
            description.to_owned(),
            String::new(),
            format!("下絵のはじめの行: {head}"),
            String::new(),
            "下絵の層（番号（種類）: 指示）:".to_owned(),
        ],
        ResolvedInstructionLanguage::En => vec![
            "Description:".to_owned(),
            description.to_owned(),
            String::new(),
            format!("First lines of the work plan: {head}"),
            String::new(),
            "Layers of the work plan (number (kind): instruction):".to_owned(),
        ],
    };
    for (index, layer) in plan.layers.iter().enumerate() {
        let mut bare = layer.clone();
        let place = bare.attributes.remove(&WorkPlanSlot::Position);
        let one = WorkPlan {
            layers: vec![bare],
            ..WorkPlan::default()
        };
        let mut text = print_work_plan_with_plugins(&one, language, plugins);
        let kind = kind_name(composition::layer_kind(layer), language);
        if let Some(place) = place {
            let name = place_name(&place, language);
            text.push_str(&match language {
                ResolvedInstructionLanguage::Ja => format!("〔下絵が付けた場所: {name}〕"),
                ResolvedInstructionLanguage::En => format!(" [place set by the work plan: {name}]"),
            });
        }
        lines.push(match language {
            ResolvedInstructionLanguage::Ja => format!("{index}（{kind}）: {text}"),
            ResolvedInstructionLanguage::En => format!("{index} ({kind}): {text}"),
        });
    }
    lines.join("\n")
}

/// The response schema for a plan of `layer_count` layers: fixed values only.
///
/// Each object names its property order (`propertyOrdering`), the order the
/// prototype wrote and measured: the thesis is written first. JSON values here
/// keep no key order, so a transport that orders properties reads it from there.
fn response_schema(layer_count: usize) -> Value {
    let optional = |values: &[&str]| {
        let mut values: Vec<&str> = values.to_vec();
        values.push(UNSPECIFIED);
        json!({"type": "string", "enum": values})
    };
    let mut tension = serde_json::Map::new();
    for (axis, values) in composition::TENSION {
        tension.insert(axis.to_owned(), optional(values));
    }
    let axes: Vec<&str> = composition::TENSION.iter().map(|(axis, _)| *axis).collect();
    json!({
        "type": "object",
        "propertyOrdering": ["thesis", "roles", "relations", "tension", "stated_places"],
        "properties": {
            "thesis": {"type": "string"},
            "roles": {
                "type": "array",
                "items": {"type": "string", "enum": composition::ROLE_NAMES},
                "minItems": layer_count,
                "maxItems": layer_count
            },
            "relations": {"type": "array", "items": {
                "type": "object",
                "propertyOrdering": ["type", "layers", "side", "toward"],
                "properties": {
                    "type": {"type": "string", "enum": composition::RELATION_NAMES},
                    "layers": {"type": "array", "items": {"type": "integer", "minimum": 0}, "minItems": 1, "maxItems": 3},
                    "side": optional(&composition::SIDES),
                    "toward": optional(&composition::TOWARD)
                },
                "required": ["type", "layers", "side", "toward"]
            }},
            "tension": {"type": "object", "propertyOrdering": axes, "properties": tension, "required": axes},
            "stated_places": {"type": "array", "items": {
                "type": "object",
                "propertyOrdering": ["layer", "words", "place"],
                "properties": {
                    "layer": {"type": "integer", "minimum": 0},
                    "words": {"type": "string"},
                    "place": {"type": "string", "enum": PLACES}
                },
                "required": ["layer", "words", "place"]
            }}
        },
        "required": ["thesis", "roles", "relations", "tension", "stated_places"]
    })
}

/// Build the `read_composition` request for a settled work plan.
pub fn build_composition_reading_prompt(
    description: &str,
    plan: &WorkPlan,
    plugins: &[WorkPlanPlugin],
    language: ResolvedInstructionLanguage,
    limits: PromptLimits,
) -> Result<LlmPrompt, PromptError> {
    crate::prompts::require_nonempty("description", description)?;
    crate::prompts::require_within("description", description.len(), limits.max_source_bytes)?;
    let system = match language {
        ResolvedInstructionLanguage::Ja => SYSTEM_JA,
        ResolvedInstructionLanguage::En => SYSTEM_EN,
    }
    .to_owned();
    crate::prompts::finish_prompt(LlmPrompt {
        schema_id: crate::prompts::LLM_PROMPT_SCHEMA_ID.to_owned(),
        prompt_id: COMPOSITION_READING_PROMPT_ID.to_owned(),
        stage: LlmStage::ReadComposition,
        action_name: LlmStage::ReadComposition.action_name().to_owned(),
        instruction_language: language,
        system,
        message: message(description, plan, plugins, language),
        response_schema: response_schema(plan.layers.len()),
        prompt_digest: String::new(),
        saijiki_asset_id: None,
        saijiki_asset_digest: None,
        macro_catalog_digest: None,
        base_source_digest: None,
        base_compiler_lock_digest: None,
    })
}

/// A reply read into the check's input, with the reading's one-sentence thesis.
#[derive(Clone, Debug)]
pub struct ParsedReading {
    pub reading: RawReading,
    pub thesis: String,
}

fn not_unspecified(value: Option<&Value>) -> Option<Value> {
    value
        .filter(|value| !value.is_null() && value.as_str() != Some(UNSPECIFIED))
        .cloned()
}

/// The key a stated place is filed under: its layer number as the reply wrote it.
fn layer_key(value: Option<&Value>) -> String {
    match value {
        None | Some(Value::Null) => "None".to_owned(),
        Some(Value::String(text)) => text.clone(),
        Some(other) => other.to_string(),
    }
}

/// Read a composition reply. It fails when the reply is not the requested shape:
/// not JSON, no role list of the plan's length, a relation or tension that is not an
/// object, or layer numbers that are not a list.
pub fn parse_composition_reading_response(
    response_text: &str,
    layer_count: usize,
    limits: PromptLimits,
) -> Result<ParsedReading, PromptError> {
    let value: Value = crate::prompts::parse_bounded(response_text, limits)?;
    let unreadable = || PromptError::InvalidJson;
    let roles = value
        .get("roles")
        .and_then(Value::as_array)
        .ok_or_else(unreadable)?;
    if roles.len() != layer_count {
        return Err(unreadable());
    }
    let roles = roles
        .iter()
        .map(|role| role.as_str().map(str::to_owned).ok_or_else(unreadable))
        .collect::<Result<Vec<_>, _>>()?;
    let mut relations = Vec::new();
    for relation in value
        .get("relations")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let relation = relation.as_object().ok_or_else(unreadable)?;
        let kind = relation.get("type").cloned();
        let names = kind
            .as_ref()
            .and_then(Value::as_str)
            .and_then(composition::RelationKind::parse)
            .map(composition::RelationKind::arg_names)
            .unwrap_or_default();
        let indices = match relation.get("layers") {
            None | Some(Value::Null) => Vec::new(),
            Some(Value::Array(indices)) => indices.clone(),
            Some(_) => return Err(unreadable()),
        };
        let mut raw = RawRelation {
            kind,
            side: not_unspecified(relation.get("side")),
            toward: not_unspecified(relation.get("toward")),
            ..RawRelation::default()
        };
        for (name, index) in names.into_iter().zip(indices) {
            match name {
                "a" => raw.a = Some(index),
                "b" => raw.b = Some(index),
                _ => raw.c = Some(index),
            }
        }
        relations.push(raw);
    }
    let mut tension = Vec::new();
    match value.get("tension") {
        None | Some(Value::Null) => {}
        Some(Value::Object(axes)) => {
            for (axis, value) in axes {
                if let Some(value) = not_unspecified(Some(value)) {
                    tension.push((axis.clone(), value));
                }
            }
        }
        Some(_) => return Err(unreadable()),
    }
    let mut stated_places: Vec<(String, RawStatedPlace)> = Vec::new();
    for entry in value
        .get("stated_places")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let entry = entry.as_object().ok_or_else(unreadable)?;
        let key = layer_key(entry.get("layer"));
        let place = entry
            .get("place")
            .and_then(Value::as_str)
            .filter(|place| PLACES.contains(place))
            .map(str::to_owned);
        let stated = RawStatedPlace {
            words: entry
                .get("words")
                .and_then(Value::as_str)
                .map(str::to_owned),
            place,
        };
        match stated_places
            .iter_mut()
            .find(|(existing, _)| *existing == key)
        {
            Some(slot) => slot.1 = stated,
            None => stated_places.push((key, stated)),
        }
    }
    let thesis = value
        .get("thesis")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_owned();
    Ok(ParsedReading {
        reading: RawReading {
            roles,
            relations,
            tension,
            stated_places,
        },
        thesis,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn limits() -> PromptLimits {
        PromptLimits {
            max_catalog_entries: 8,
            max_summary_bytes: 1024,
            max_catalog_serialized_bytes: 8192,
            max_source_bytes: 16_384,
            max_response_bytes: 65_536,
        }
    }

    #[test]
    fn a_reply_reads_into_the_check_input() {
        let reply = r#"{"thesis":"t","roles":["field","focal"],
            "relations":[{"type":"within","layers":[1,0],"side":"unspecified","toward":"unspecified"},
                         {"type":"near","layers":[1,0],"side":"below","toward":"unspecified"}],
            "tension":{"motion":"still","focus":"unspecified","vertical":"unspecified","balance":"dynamic",
                       "symmetry":"unspecified","void":"strong"},
            "stated_places":[{"layer":1,"words":"下に","place":"bottom"},{"layer":0,"words":"x","place":"nowhere"}]}"#;
        let parsed = parse_composition_reading_response(reply, 2, limits()).expect("readable");
        let reading = parsed.reading;
        assert_eq!(reading.roles, ["field", "focal"]);
        assert_eq!(reading.relations.len(), 2);
        assert_eq!(reading.relations[0].a, Some(json!(1)));
        assert_eq!(reading.relations[0].b, Some(json!(0)));
        assert_eq!(reading.relations[0].side, None);
        assert_eq!(reading.relations[1].side, Some(json!("below")));
        let axes: Vec<&str> = reading
            .tension
            .iter()
            .map(|(axis, _)| axis.as_str())
            .collect();
        assert_eq!(axes, ["balance", "motion", "void"]);
        assert_eq!(reading.stated_places[0].0, "1");
        assert_eq!(reading.stated_places[0].1.place.as_deref(), Some("bottom"));
        assert_eq!(reading.stated_places[1].1.place, None);
        assert_eq!(parsed.thesis, "t");
    }

    #[test]
    fn a_reply_with_the_wrong_number_of_roles_is_unreadable() {
        let reply =
            r#"{"thesis":"t","roles":["field"],"relations":[],"tension":{},"stated_places":[]}"#;
        assert!(parse_composition_reading_response(reply, 2, limits()).is_err());
    }

    #[test]
    fn the_system_text_is_the_prototype_text() {
        assert!(SYSTEM_JA.starts_with("あなたは、言葉から絵を作るアプリinkuの構図の読み手です。"));
        assert!(SYSTEM_EN.starts_with("You are the composition reader of inku"));
        assert!(SYSTEM_JA.contains("stated_places"));
    }
}
