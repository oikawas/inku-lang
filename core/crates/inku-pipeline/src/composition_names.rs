//! The names the hosts show for a composition's record (2026-11-13): the
//! forms, the laws with a one-line summary for the author, the color laws,
//! the roles and kinds of thing, the places of the proportion laws and the
//! places of the cards.
//!
//! The table is for the screens, not for the requests: the request texts
//! (`THING_LAWS`, the laws' and colors' `LAW_TEXTS`) stay as they are, and a
//! summary here is a law's sentence without what speaks to the model (key
//! names, what the tool computes). The shared fixture
//! `server/tests/data/composition-names-v1.json` is this table's output; the
//! Web reads a module generated from it (`gen_composition_names_ts.py`).

use serde::Serialize;

use crate::colors::{COLOR_LAWS, color_law_words};
use crate::description_composition::{FORMS, KINDS, ROLES};
use crate::laws::{LAWS, law_words};

/// The names table's schema.
pub const COMPOSITION_NAMES_SCHEMA_ID: &str = "inku.composition-names.v1";

/// Each form's short name and description (ja, en), as the hosts' form
/// choices show them (`compositionFormNames`, `compositionFormDescriptions`).
const FORM_WORDS: [(&str, [&str; 2], [&str; 2]); 7] = [
    (
        "one_corner",
        ["一角", "One corner"],
        [
            "主を片隅や片側に寄せて広く空ける",
            "Push the focal thing to one side and leave wide space",
        ],
    ),
    (
        "all_over",
        ["全面", "All over"],
        [
            "全面に均して中心を消す",
            "Spread evenly and erase the center",
        ],
    ),
    (
        "bands",
        ["帯", "Bands"],
        ["横の帯を重ねる", "Stack horizontal bands"],
    ),
    (
        "dividing_line",
        ["分ける線", "Dividing line"],
        ["場を分ける線", "Divide the field with a line"],
    ),
    ("grid", ["格子", "Grid"], ["格子", "Grid"]),
    (
        "flock_and_stray",
        ["群れと逸れ", "Flock and stray"],
        ["群れと一つの逸脱", "A flock and one that strays"],
    ),
    (
        "unequal_triangle",
        ["不等辺の三角", "Unequal triangle"],
        [
            "主・従・添えの不等辺の三角",
            "An unequal triangle of focal, secondary and accent",
        ],
    ),
];

/// Each law's one-line summary for the author (ja, en).
const LAW_SUMMARIES: [(&str, [&str; 2]); 19] = [
    (
        "B1",
        [
            "画面の辺を 0.382 : 0.618 で分ける線と、その 4 つの交点に、主な物と線を置く。",
            "Place the main things and lines on the lines that divide the canvas's sides 0.382 : 0.618 and on their four crossings.",
        ],
    ),
    (
        "B2",
        [
            "辺を 1 : √2 で分ける線（0.414・0.586）と交点に置く。",
            "Place on the lines that divide the sides 1 : √2 (0.414 and 0.586) and on their crossings.",
        ],
    ),
    (
        "B3",
        [
            "辺を三つに分ける線（1/3・2/3）と交点に置く。",
            "Place on the lines that divide the sides in three (1/3 and 2/3) and on their crossings.",
        ],
    ),
    (
        "B4",
        [
            "辺を音の協和の比 2:3（0.4・0.6）か 3:4（0.429・0.571）で分ける線と交点に置く。",
            "Place on the lines that divide the sides by a consonant ratio of sound, 2:3 (0.4 and 0.6) or 3:4 (0.429 and 0.571), and on their crossings.",
        ],
    ),
    (
        "B5",
        [
            "画面の対角線・中心の縦の線・中心の横の線を骨組みにして、線の物と、いくつかの形を並べた物を、その上に置く。",
            "Take the canvas's diagonals, its central vertical line and its central horizontal line as the armature, and place line things and things of several shapes in a row on them.",
        ],
    ),
    (
        "B6",
        [
            "基準の物を一つ選び、従と添えの物の大きさを、基準を 1 として 0.618・0.382 にする。",
            "Choose one base thing; the secondary and accent things are 0.618 and 0.382 of the base's size.",
        ],
    ),
    (
        "B7",
        [
            "大きな相手は中心寄りに、小さな物は中心をはさんだ反対側の遠くに置き、重さ×距離を釣り合わせる。",
            "Keep a large partner near the center and place a small thing far away on the other side of the center, balancing weight × distance.",
        ],
    ),
    (
        "B8",
        [
            "中心線に対して対に置く。物の中心を軸に置き、二つでなる物は軸の両側に鏡に置く。",
            "Place in pairs about a central line. The thing's center goes on the axis, and a thing of two parts is mirrored on either side of it.",
        ],
    ),
    (
        "B9",
        [
            "同じ形を同じ間隔で並べる。",
            "Repeat the same shape at equal intervals.",
        ],
    ),
    (
        "B10",
        [
            "物の形を一つずつの列にし、大きさか間隔を、隣どうし同じ比で変える。",
            "Line the thing's shapes up one by one and change their size or their spacing by the same ratio between neighbours.",
        ],
    ),
    (
        "B12",
        [
            "物の形を 2・3・4 個ずつの群にして、群の間に間をおいて列に並べる。",
            "Group the thing's shapes by 2, 3 or 4 and line them up with a rest between the groups.",
        ],
    ),
    (
        "B15",
        [
            "遠くの物を、地との明るさの差が小さい寒色か灰に替え、小さくする。",
            "Turn distant things to the cool color or gray closest to the ground in lightness and make them smaller.",
        ],
    ),
    (
        "B21",
        [
            "法則が位置・間隔・大きさ・色を決め、手の揺らぎはその規則を壊さない幅に収める。主の法則にはしない。",
            "The laws decide places, spacing, sizes and colors, and the hand's sway stays within what keeps their rules. Never the main law.",
        ],
    ),
    (
        "C1",
        [
            "画面の中に、物が隙間なく詰まる密の所を一つ作り、ほかを大きく空ける。",
            "Make one dense place in the picture where things crowd without a gap, and leave the rest wide open.",
        ],
    ),
    (
        "C2",
        [
            "一つの単位の形を、規則で敷き詰める（青海波・七宝・市松・鱗・亀甲）。",
            "Tile the canvas with one unit shape by a rule (seigaiha, shippo, ichimatsu, uroko, kikko).",
        ],
    ),
    (
        "C3",
        [
            "二つの声部を、同じ長さに違う数で等間隔に並べて重ねる。",
            "Lay two voices over each other, each lined up at equal spacing along the same length with a different count.",
        ],
    ),
    (
        "C4",
        [
            "一つの形（動機）を、大きさ・向き・鏡映・ずらした重ねを順に変えながら繰り返す。",
            "Repeat one shape (the motif), changing its size, its turn, its mirror image and a staggered overlap in turn.",
        ],
    ),
    (
        "C5",
        [
            "一つの流れを三段にする。まばら→変化→密になる。",
            "Make one flow in three stages: from sparse to changing to dense.",
        ],
    ),
    (
        "C6",
        [
            "同じ形を、厳格（真）・半ば崩す（行）・自在（草）の三つの度合いで描き分ける。",
            "Draw the same shape in three degrees: strict (shin), half loosened (gyo) and free (so).",
        ],
    ),
];

/// The law that is never a main law.
const NOT_MAIN: &str = "B21";

/// Each role's name (ja, en).
const ROLE_WORDS: [(&str, [&str; 2]); 5] = [
    ("field", ["場", "field"]),
    ("focal", ["主", "focal"]),
    ("secondary", ["従", "secondary"]),
    ("scattered", ["散在", "scattered"]),
    ("accent", ["添え", "accent"]),
];

/// Each kind's name (ja, en).
const KIND_WORDS: [(&str, [&str; 2]); 4] = [
    ("cluster", ["1か所の形", "cluster"]),
    ("row", ["列", "row"]),
    ("surface", ["面", "surface"]),
    ("line", ["線", "line"]),
];

/// The proportion laws' places (`at`), as a screen's label: the Japanese is
/// the request's word, the English a label rather than the request's phrase.
const AT_LABELS: [(&str, [&str; 2]); 8] = [
    ("point_ul", ["左上の交点", "Upper left crossing"]),
    ("point_ur", ["右上の交点", "Upper right crossing"]),
    ("point_ll", ["左下の交点", "Lower left crossing"]),
    ("point_lr", ["右下の交点", "Lower right crossing"]),
    ("line_left", ["左の縦の線", "Left vertical line"]),
    ("line_right", ["右の縦の線", "Right vertical line"]),
    ("line_top", ["上の横の線", "Upper horizontal line"]),
    ("line_bottom", ["下の横の線", "Lower horizontal line"]),
];

/// The cards' places (`spot`), as a screen's label (`keep` is no place).
const PLACE_LABELS: [(&str, [&str; 2]); 9] = [
    (
        "golden_ul",
        [
            "黄金分割・左上の交点",
            "Golden section, upper left crossing",
        ],
    ),
    (
        "golden_ur",
        [
            "黄金分割・右上の交点",
            "Golden section, upper right crossing",
        ],
    ),
    (
        "golden_ll",
        [
            "黄金分割・左下の交点",
            "Golden section, lower left crossing",
        ],
    ),
    (
        "golden_lr",
        [
            "黄金分割・右下の交点",
            "Golden section, lower right crossing",
        ],
    ),
    (
        "third_left",
        ["三分割・左の縦の線", "Rule of thirds, left vertical line"],
    ),
    (
        "third_right",
        ["三分割・右の縦の線", "Rule of thirds, right vertical line"],
    ),
    (
        "third_top",
        [
            "三分割・上の横の線",
            "Rule of thirds, upper horizontal line",
        ],
    ),
    (
        "third_bottom",
        [
            "三分割・下の横の線",
            "Rule of thirds, lower horizontal line",
        ],
    ),
    ("center", ["中心", "Center"]),
];

#[derive(Serialize)]
struct Bilingual {
    ja: &'static str,
    en: &'static str,
}

impl From<[&'static str; 2]> for Bilingual {
    fn from([ja, en]: [&'static str; 2]) -> Self {
        Self { ja, en }
    }
}

#[derive(Serialize)]
struct FormEntry {
    id: &'static str,
    name: Bilingual,
    description: Bilingual,
}

#[derive(Serialize)]
struct LawEntry {
    code: &'static str,
    name: Bilingual,
    family: Bilingual,
    summary: Bilingual,
    main: bool,
}

#[derive(Serialize)]
struct ColorLawEntry {
    code: &'static str,
    name: Bilingual,
    family: Bilingual,
}

#[derive(Serialize)]
struct NamedEntry {
    id: &'static str,
    name: Bilingual,
}

#[derive(Serialize)]
struct Names {
    schema: &'static str,
    forms: Vec<FormEntry>,
    laws: Vec<LawEntry>,
    color_laws: Vec<ColorLawEntry>,
    roles: Vec<NamedEntry>,
    kinds: Vec<NamedEntry>,
    at: Vec<NamedEntry>,
    places: Vec<NamedEntry>,
}

fn lookup<T: Copy>(table: &[(&str, T)], key: &str) -> T {
    table
        .iter()
        .find(|(found, _)| *found == key)
        .map(|(_, value)| *value)
        .unwrap_or_else(|| panic!("the names table has {key}"))
}

fn named(table: &[(&'static str, [&'static str; 2])]) -> Vec<NamedEntry> {
    table
        .iter()
        .map(|(id, name)| NamedEntry {
            id,
            name: (*name).into(),
        })
        .collect()
}

fn names() -> Names {
    Names {
        schema: COMPOSITION_NAMES_SCHEMA_ID,
        forms: FORMS
            .into_iter()
            .map(|id| {
                let (_, name, description) = FORM_WORDS
                    .iter()
                    .find(|(found, _, _)| *found == id)
                    .unwrap_or_else(|| panic!("the names table has {id}"));
                FormEntry {
                    id,
                    name: (*name).into(),
                    description: (*description).into(),
                }
            })
            .collect(),
        laws: LAWS
            .into_iter()
            .map(|code| {
                let (name, family, _, _) =
                    law_words(code).unwrap_or_else(|| panic!("the laws name {code}"));
                LawEntry {
                    code,
                    name: name.into(),
                    family: family.into(),
                    summary: lookup(&LAW_SUMMARIES, code).into(),
                    main: code != NOT_MAIN,
                }
            })
            .collect(),
        color_laws: COLOR_LAWS
            .into_iter()
            .map(|code| {
                let (name, family) =
                    color_law_words(code).unwrap_or_else(|| panic!("the colors name {code}"));
                ColorLawEntry {
                    code,
                    name: name.into(),
                    family: family.into(),
                }
            })
            .collect(),
        roles: ROLES
            .into_iter()
            .map(|id| NamedEntry {
                id,
                name: lookup(&ROLE_WORDS, id).into(),
            })
            .collect(),
        kinds: KINDS
            .into_iter()
            .map(|id| NamedEntry {
                id,
                name: lookup(&KIND_WORDS, id).into(),
            })
            .collect(),
        at: named(&AT_LABELS),
        places: named(&PLACE_LABELS),
    }
}

/// The names table as JSON, for the hosts' display of a composition's record:
/// `schema`, then `forms`, `laws`, `color_laws`, `roles`, `kinds`, `at` and
/// `places`, each entry with its id (or code) and its words in both languages.
#[must_use]
pub fn composition_names_json() -> String {
    serde_json::to_string(&names()).expect("the names table serializes")
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    fn table() -> Value {
        serde_json::from_str(&composition_names_json()).expect("the names table is JSON")
    }

    fn ids(table: &Value, list: &str, key: &str) -> Vec<String> {
        table[list]
            .as_array()
            .expect("a list")
            .iter()
            .map(|entry| entry[key].as_str().expect("an id").to_owned())
            .collect()
    }

    #[test]
    fn every_id_and_code_has_a_name() {
        let table = table();
        assert_eq!(ids(&table, "forms", "id"), FORMS);
        assert_eq!(ids(&table, "laws", "code"), LAWS);
        assert_eq!(ids(&table, "color_laws", "code"), COLOR_LAWS);
        assert_eq!(ids(&table, "roles", "id"), ROLES);
        assert_eq!(ids(&table, "kinds", "id"), KINDS);
        let at: Vec<&str> = crate::description_composition::AT_WORDS
            .iter()
            .map(|(id, _, _)| *id)
            .collect();
        assert_eq!(ids(&table, "at", "id"), at);
        let places: Vec<&str> = crate::chunk_moves::AT
            .iter()
            .map(|(id, _, _)| *id)
            .filter(|id| *id != "keep")
            .collect();
        assert_eq!(ids(&table, "places", "id"), places);
    }

    #[test]
    fn the_names_are_the_requests_names() {
        let table = table();
        for (entry, code) in table["laws"].as_array().unwrap().iter().zip(LAWS) {
            let (name, family, _, _) = law_words(code).unwrap();
            assert_eq!(entry["name"]["ja"], name[0]);
            assert_eq!(entry["family"]["en"], family[1]);
            assert_eq!(entry["main"], code != "B21");
        }
        for (entry, (id, ja, _)) in table["at"]
            .as_array()
            .unwrap()
            .iter()
            .zip(crate::description_composition::AT_WORDS)
        {
            assert_eq!(entry["id"], id);
            assert_eq!(entry["name"]["ja"], ja);
        }
    }

    #[test]
    fn the_shared_fixture_is_this_table() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../../../server/tests/data/composition-names-v1.json"
        ))
        .expect("the fixture is JSON");
        assert_eq!(table(), fixture);
    }
}
