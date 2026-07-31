#!/usr/bin/env node
// i18n-lint — guards the English UI vocabulary defined in src/lib/i18n/GLOSSARY.md.
//
//   npm run lint:i18n            report
//   npm run lint:i18n -- --list  also print every allowed exception it matched
//
// It reads the four channels the English UI actually lives in:
//   1. src/lib/i18n/en.ts               (the i18n pack; values only, never key names)
//   2. isJapanese ? '…' : '…'           (ternaries inside components)
//   3. getLang() === 'ja' ? '…' : '…'   (branches in +page.svelte and friends)
//   4. 日本語 / English                  (bilingual labels in component markup)
//
// Every rule below has its prose counterpart in GLOSSARY.md. When you change one,
// change the other in the same commit — the file and this script are one pair.

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const WEB = join(dirname(fileURLToPath(import.meta.url)), '..');
const SRC = join(WEB, 'src');
const EN = join(SRC, 'lib/i18n/en.ts');
const JA = join(SRC, 'lib/i18n/ja.ts');
const listMode = process.argv.includes('--list');

// ── the dictionary the UI must hold to ────────────────────────────────────
// Fixed English for the five refinement operations and the variation amplitudes.
// These are the labels the author ruled on; drift here is a real regression.
const FIXED = {
	canvasVaryPerformance: 'Another performance',
	canvasVaryComposition: 'Another composition',
	canvasVaryInterpretation: 'Another reading',
	canvasVaryColor: 'Another catalog',
	variationTitle: 'Variation',
	variationSmall: 'Subtle',
	variationMedium: 'Moderate',
	variationLarge: 'Sweeping',
	submitBtn: 'Paint',
	wildButton: 'Wild',
};

// Words that must never appear in an English display string, whatever the context.
// Each carries the word to use instead.
const NEVER = [
	[/\bpalettes?\b/i, 'palette', 'use "color catalog" — palette is a different concept in inku'],
	[/\bartworks?\b/i, 'artwork', 'use "work" (the art register)'],
	[/\bfluctuations?\b/i, 'fluctuation', 'use "sway"'],
	[/\bjitter\b/i, 'jitter', 'use "sway"'],
	[/ai-powered/i, 'AI-powered', 'drop it — the whole tool contains AI'],
	[/\bmagic/i, 'magic', 'drop it — no advertising register'],
	[/\bokugaki\b/i, 'okugaki', 'use "colophon" — romaji is only for Saijiki and inku'],
];

// Words allowed only in the listed places. Anywhere else they are the AI-industry
// register the glossary bans. Keys are en.ts keys; texts are exact strings from the
// component channels (line numbers move, so the text itself is the anchor).
const RESTRICTED = [
	{
		word: 'generat', re: /generat/i, instead: 'the sense "produce a work" is paint / perform / make',
		keys: [
			'aiRefineVisionModeHint', 'aiRefineDirectionRandomHint', 'aiRefineGensLabel',
			'settingsDbBackupMaxGenerations', 'okugakiDescription', 'okugakiBranchConfirm',
			'okugakiProgress', 'svgExportDisplayUse', 'svgExportEditableFeature', 'svgExportCompatFeature',
			'provenanceLabelGeneration', 'provenanceHintGeneration', 'historyGenerationTitle',
			'settingsDbBackupListGeneration', 'settingsDbBackupEstimatedDiskHint',
		],
		texts: [],
	},
	{
		word: 'prompt', re: /prompt/i, instead: 'the author\'s text is a "description"',
		keys: [
			'tabPrompts', 'tooltipCanvasTabPrompts', 'promptStage1System', 'promptStage2System',
			'provenanceLabelStage1PromptDigest', 'provenanceLabelStage1PromptBaseDigest',
			'provenanceLabelStage2PromptDigest', 'provenanceHintStage1PromptDigest',
			'provenanceHintStage1PromptBaseDigest', 'provenanceHintStage2PromptDigest',
		],
		texts: ['Show the provenance, prompts, and JSON of the chosen work'],
	},
	{
		word: 'creat', re: /\bcreat/i, instead: 'buttons use New / Paint / Make',
		keys: ['appInfoCreatorTitle', 'settingsDbBackupRunDone', 'bootstrapAdminNote', 'historyCreatedAtHeader'],
		texts: ['Created'],
	},
	{
		word: 'image', re: /\bimages?\b/i, instead: 'use "work" or "picture"',
		keys: ['modelSelectionVisionHint', 'aiRefineVisionModeHint', 'aiRefineVisionReading', 'aiRefineVisionSourceError'],
		texts: [],
	},
	{
		word: 'render', re: /render/i, instead: 'the act the user sees is a "performance"',
		keys: [
			'canvasSeedSummary', 'settingsRenderConcurrencyTitle', 'settingsRenderConcurrencyServer',
			'settingsRenderConcurrencyServerHelp', 'settingsRenderConcurrencyClientHelp',
			'settingsRenderConcurrencySaved', 'historyReplayMissingSeed', 'replayComparisonTitle',
		],
		texts: [],
	},
	{
		// The romaji gloss is allowed once, in the vocabulary dialog that teaches the term.
		word: 'kotobagaki', re: /\bkotobagaki\b/i, instead: 'use "headnote"',
		keys: ['appInfoVocabRows'],
		texts: [],
	},
	{
		// One word, one sense: Moderate is the middle variation amplitude and nothing else.
		word: 'Moderate', re: /\bmoderate\b/i, instead: 'for speed use Medium',
		keys: ['variationMedium', 'variationTooltipLarge'],
		texts: [],
	},
];

// Proper nouns and tokens that may keep their capitals mid-sentence (§ style rules).
const PROPER = new Set([
	'Saijiki', 'DDL', 'JSON', 'Score', 'SVG', 'PNG', 'API', 'DB', 'LLM', 'AI', 'Vision', 'URL', 'ID', 'IDs',
	'Stage', 'Gen', 'OK', 'NG', 'GitHub', 'Illustrator', 'Affinity', 'Qwen3', 'Base', 'Y-axis', 'Editable',
	'Display', 'Compatibility', 'Standard', 'Square', 'Web', 'Vary', 'Another', 'Requires', 'Copy',
]);

// ── read the three channels ───────────────────────────────────────────────
function pack(file) {
	const out = [];
	let cur = null;
	for (const line of readFileSync(file, 'utf8').split('\n')) {
		const m = /^\t([A-Za-z0-9_]+):(.*)$/.exec(line);
		if (m) {
			if (cur) out.push(cur);
			cur = { key: m[1], text: m[2] };
		} else if (cur) {
			if (/^};?$/.test(line)) { out.push(cur); cur = null; }
			else cur.text += ' ' + line.trim();
		}
	}
	if (cur) out.push(cur);
	return out;
}

function walk(dir, acc = []) {
	for (const name of readdirSync(dir)) {
		const p = join(dir, name);
		if (statSync(p).isDirectory()) walk(p, acc);
		else if (/\.(svelte|ts)$/.test(p)) acc.push(p);
	}
	return acc;
}

const TERNARY = /isJapanese \? '((?:[^'\\]|\\.)*)' : '((?:[^'\\]|\\.)*)'/g;
const GETLANG = /getLang\(\) === 'ja'\s*\n?\s*\? '((?:[^'\\]|\\.)*)'\s*\n?\s*: '((?:[^'\\]|\\.)*)'/g;
const BILINGUAL_LABEL = />\s*([^<>\n]*[\u3040-\u30ff\u3400-\u9fff][^<>\n]*?)\s+\/\s+([A-Za-z][^<>\n]*?)\s*</g;

const strings = [];
for (const e of pack(EN)) strings.push({ where: `en.ts ${e.key}`, key: e.key, text: e.text });
for (const file of walk(SRC)) {
	if (file === EN || file === JA) continue;
	const body = readFileSync(file, 'utf8');
	for (const re of [TERNARY, GETLANG, BILINGUAL_LABEL]) {
		re.lastIndex = 0;
		let m;
		while ((m = re.exec(body)) !== null) {
			const line = body.slice(0, m.index).split('\n').length;
			strings.push({ where: `${relative(SRC, file)}:${line}`, key: null, text: m[2] });
		}
	}
}

// ── rules ─────────────────────────────────────────────────────────────────
const errors = [];
const warnings = [];
const allowed = [];

// 1. en.ts and ja.ts must carry exactly the same keys.
{
	const en = pack(EN).map((e) => e.key);
	const ja = pack(JA).map((e) => e.key);
	for (const k of en) if (!ja.includes(k)) errors.push(`key present in en.ts but not ja.ts: ${k}`);
	for (const k of ja) if (!en.includes(k)) errors.push(`key present in ja.ts but not en.ts: ${k}`);
}

// 2. The ruled labels must be exactly the ruled words.
for (const [key, want] of Object.entries(FIXED)) {
	const got = strings.find((s) => s.key === key);
	if (!got) { errors.push(`ruled key is missing from en.ts: ${key}`); continue; }
	const m = /^\s*'((?:[^'\\]|\\.)*)'/.exec(got.text);
	if (!m || m[1] !== want) errors.push(`${key}: must read '${want}', found ${got.text.trim().slice(0, 60)}`);
}

// 3–4. Banned words, and restricted words outside their allowed places.
for (const s of strings) {
	for (const [re, word, instead] of NEVER) {
		if (re.test(s.text)) errors.push(`${s.where}: "${word}" — ${instead}\n      ${s.text.trim().slice(0, 120)}`);
	}
	for (const r of RESTRICTED) {
		if (!r.re.test(s.text)) continue;
		const ok = (s.key && r.keys.includes(s.key)) || r.texts.some((t) => s.text.includes(t));
		if (ok) allowed.push(`${s.where}: "${r.word}" (allowed)`);
		else errors.push(`${s.where}: "${r.word}" — ${r.instead}\n      ${s.text.trim().slice(0, 120)}`);
	}
	// 5. One ellipsis character, never three dots.
	if (/\.\.\./.test(s.text)) errors.push(`${s.where}: use the ellipsis character "…", not "..."`);
	// 6. No exclamation marks in the quiet register.
	if (/!['"]/.test(s.text)) errors.push(`${s.where}: no exclamation marks`);
}

// 7. Sentence case (warning only — proper nouns are hard to enumerate).
// Only labels are checked: a literal carrying sentence punctuation is prose, where a
// capital after a full stop is correct. Labels are split on / — ; so that each clause
// gets its own leading capital.
const CASE_SKIP = new Set(['appInfoCreatorName', 'appInfoCreatorBody']);
for (const s of strings) {
	if (s.key && CASE_SKIP.has(s.key)) continue;
	for (const m of s.text.matchAll(/'((?:[^'\\]|\\.)*)'/g)) {
		if (/[.!?\n]|\\n/.test(m[1])) continue;
		for (const clause of m[1].split(/\s+[/—;:]\s+|\\u2014/)) {
			const words = clause.split(/[\s(]+/).filter(Boolean);
			if (words.length < 2) continue;
			const offenders = words.slice(1).filter((w) => /^[A-Z][a-z]{2,}$/.test(w) && !PROPER.has(w));
			if (offenders.length) warnings.push(`${s.where}: possible Title Case — ${offenders.join(', ')} in "${m[1].slice(0, 70)}"`);
		}
	}
}

// ── report ────────────────────────────────────────────────────────────────
if (listMode) for (const a of allowed) console.log(`allow  ${a}`);
for (const w of warnings) console.log(`WARN   ${w}`);
for (const e of errors) console.log(`ERROR  ${e}`);
console.log(
	`\ni18n-lint: ${strings.length} English strings, ${allowed.length} allowed exceptions, ` +
	`${warnings.length} warnings, ${errors.length} errors`
);
console.log('rules and rationale: src/lib/i18n/GLOSSARY.md');
process.exit(errors.length ? 1 : 0);
