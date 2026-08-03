"""Independent versions for deterministic DDL layers and the DDL language."""

# 5 (2026-08-03): `thinness` moved to sit immediately before `surface`, giving the
# last declaration slot back to `surface`. The deterministic layers behave exactly
# as before -- this is the declaration-order condition, the one the frozen corpora
# cannot catch, so ddl-engine-5 is byte-identical to ddl-engine-4 by design.
DDL_ENGINE_VERSION = "5"
# 4 (2026-07-30): yellow, orange, and purple become abstract Score colors, and
# coerce recognizes the corresponding Japanese and English DDL markers.
# 3 (2026-07-30): 黄 / 橙 / 紫 joined the saijiki color words, so an author can write
# them and Stage 1 offers them. This follows the same rule version 2 followed for the
# thinness word: the language version rises when its vocabulary grows, not when its
# grammar changes. Works saved earlier keep the version they were written under.
DDL_VERSION = "3"
