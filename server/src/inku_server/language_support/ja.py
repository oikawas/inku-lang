"""Japanese instruction-language support."""

from __future__ import annotations

from ..composer import SYSTEM_PROMPT as STAGE2_PROMPT
from ..ddl_expander import expand_intermediate_ddl
from ..interpreter import SYSTEM_PROMPT as STAGE1_PROMPT
from .base import InstructionLanguageSupport

COERCE_MARKERS = {
    "material_weight_hints": (
        (("ロットリング",), "rotring"),
        (("鉛筆",), "pencil"),
        (("クレヨン",), "crayon"),
        (("チョーク",), "chalk"),
        (("細筆",), "brush_thin"),
        (("太筆", "厚塗り", "油絵"), "brush_thick"),
        (("水墨", "墨"), "brush_thin"),
        (("縄", "ロープ"), "rope"),
    ),
    "color_markers": (
        (("白",), "white"),
        (("黒", "闇", "影", "墨"), "black"),
        (("青", "空", "水", "湖", "海", "雨", "冷たい"), "blue"),
        (("赤",), "red"),
        (("緑", "森", "草", "苔", "竹", "庭", "香り", "芽", "落ち葉", "若葉", "木の葉", "葉っぱ", "葉脈"), "green"),
        (("灰",), "gray"),
    ),
    "negated_color_markers": {
        "green": (
            "緑には寄せず",
            "緑に寄せず",
            "緑ではなく",
            "緑を避け",
            "緑を使わず",
            "緑なし",
        ),
    },
    "shape_intent_markers": (
        (("多角形", "五角", "六角", "結晶", "鉱物", "硬い欠片", "硬い破片"), "polygon"),
        (("山", "尖", "鋭", "三角", "峰", "頂", "稜線"), "triangle"),
        (("弧", "渦", "螺旋", "波紋", "巻"), "arc"),
        (("紙片", "破片", "折", "畳", "四角"), "square"),
    ),
    "motif_intent_markers": (
        (("落ち葉", "若葉", "木の葉", "葉っぱ", "葉脈"), "leaf_cluster"),
        (("紙片", "破片", "折", "手紙"), "paper_shard"),
        (("波紋", "渦", "螺旋", "巻"), "ripple_knot"),
        (("山", "峰", "稜線"), "mountain_sign"),
    ),
    "atmospheric_effect": (
        "膜", "霞", "霧", "靄", "柔らかな光", "陽光", "日差し", "香り", "匂", "五感", "反射", "映り",
    ),
    "quiet_density": (
        "静か", "静けさ", "沈黙", "余白", "薄い", "薄く", "細い", "少しだけ", "一つ", "一滴",
        "気配", "余韻", "記憶", "忘れ", "影", "冷たい", "透明", "膜", "霞", "霧", "靄", "滲",
        "低い雲", "押し沈",
    ),
    "vertical_density": ("雨", "雪", "降", "縦", "上から下"),
    "motion": (
        "渡る", "揺", "流れ", "消え", "ほどけ", "伸び", "回", "丸ま", "帰って", "先に帰", "風", "波", "ためらう",
        "低い雲", "押し沈", "影だけ", "滲", "涙", "震える", "一滴", "残る",
        "追いかけ", "手放", "舞い降り", "飛び去", "口笛", "群れが動", "車輪", "針だけ", "鳥の列",
        "礼をする", "毎朝", "発車ベル", "明るくな", "手を伸ば", "分け合", "斜めに落ち",
    ),
    "colorful": ("祭", "色紙", "果実", "ネオン", "夕焼け", "赤", "青", "緑", "色とりどり", "多色"),
    "leaf_grain": ("落ち葉", "紅葉", "湿った土", "森"),
    "silence_layer": ("廃校", "廊下", "長い沈黙", "夕方の光"),
    "hard_edge": ("工場", "鉄骨", "錆", "錆び", "空を細かく分け"),
    "playful_motion": ("自転車", "坂道", "花びら", "色紙", "風鈴"),
    "edge_light": ("夜", "真夜中", "黒い", "暗", "灯台", "光だけ", "海", "ガラス", "ネオン"),
    "strong_edge_light": ("灯台", "光だけ", "切って", "切る", "切断", "一筋の光"),
    "vanishing_trace": ("白い息", "足跡", "消え", "消える", "消えかけ", "ほどけ", "輪郭", "記憶", "跡", "遠く"),
    "rhythm": ("リズム", "踊", "跳ね", "弾む", "反復", "交互", "楽しい", "楽しさ", "喜び", "祝祭", "明快", "靴音", "拍子"),
    "visual_event": (
        "衝突", "反転", "集中", "破裂", "弾け", "核", "一点", "転がる", "抜ける",
        "迷う", "消えかけ", "震える", "一滴", "先に帰", "丸ま", "低い雲", "押し沈", "影だけ", "滲", "涙",
        "白い息", "映", "反射", "灯台", "光だけ", "足跡", "輪郭", "ほどけ", "花びら", "ためらう",
        "祖母", "植え", "市場", "少年", "追いかけ", "手放", "カラス", "舞い降り", "見回", "口笛",
        "犬が動", "羊の群れ", "時計の針", "昨日", "車輪", "足を止め", "円になって見つめ",
        "鳥の列", "もう一つの道", "傘", "坂を上", "礼をする", "父も", "父の父", "毎朝",
        "発車ベル", "案内板", "明るくな", "前に", "同じ新聞", "手を伸ば", "分け合",
        "一言も交わさず", "高い窓", "午後の光", "読まない本", "斜めに落ち", "靴音", "同じ拍子",
    ),
    "ma_pressure": (
        "余白", "間", "空白", "気配", "押す", "避け", "離れ",
        "紙", "新聞", "手紙", "紙片", "風", "交差", "迷う", "漂う", "同じ新聞", "分け合",
        "祖母", "木", "市場", "円になって", "見つめ", "美術館", "白い部屋", "橋", "川面",
    ),
    "semantic_visual_event_hints": (
        (("発車ベル", "案内板", "明るくな", "前に"), "visual event preserved as a pre-bell light hinge"),
        (("礼をする", "父も", "父の父", "毎朝"), "visual event preserved as inherited bow sequence"),
        (("同じ新聞", "手を伸ば", "分け合", "一言も交わさず"), "visual event preserved as shared newspaper hinge"),
        (("高い窓", "午後の光", "読まない本", "斜めに落ち"), "visual event preserved as diagonal afternoon light"),
        (("靴音", "同じ拍子", "急ぐ人々"), "visual event preserved as shared footstep beat"),
    ),
    "surface_tension": ("布", "果実", "重", "影", "沈む", "沈め"),
    "intentional_large_surface": ("大き", "巨大", "広い", "広がる", "布", "幕", "壁一面", "面で", "面として"),
    "generated_background_plan": ("気配", "透明な膜", "五感", "存在", "境界が滲", "画面全体"),
    "explicit_surface": ("背景", "地色", "画面全体", "塗りつぶ", "一面", "夜空", "暗闇"),
    "sunset_sky": ("夕焼け空", "夕暮れの空"),
    "dawn": ("夜明け", "明け方", "朝焼け"),
    "night": ("夜",),
}


def expand_intermediate(ddl: str, context_text: str | None = None) -> str:
    return expand_intermediate_ddl(ddl, lang="ja", context_text=context_text)


SUPPORT = InstructionLanguageSupport(
    code="ja",
    stage1_prompt=STAGE1_PROMPT,
    stage2_prompt=STAGE2_PROMPT,
    expand_intermediate=expand_intermediate,
    coerce_markers=COERCE_MARKERS,
)
