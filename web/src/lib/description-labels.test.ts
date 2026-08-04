// Run with: npm run test:unit  (node:test, no test dependency)
//
// The rule exists in two languages: the server cuts, the editor greys.  If they
// disagree the author sees one thing greyed and another thing dropped, and no
// type checker would notice.  Both sides read this one corpus.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import { excludedSpans, labelSegments, pipelineDescription } from './description-labels.ts';

const here = path.dirname(new URL(import.meta.url).pathname);
const CASES_FILE = path.resolve(here, '../../../server/tests/data/description-label-cases.json');

// The server is where the rule is enforced; if its corpus is not here, this
// test has nothing to compare against and must say so rather than pass.
const corpus = JSON.parse(fs.readFileSync(CASES_FILE, 'utf8')) as {
	cases: { why: string; text: string; pipeline: string; spans: [number, number, string][] }[];
};

test('the corpus the server is measured against is readable from here', () => {
	assert.ok(corpus.cases.length >= 15, `only ${corpus.cases.length} cases were read`);
});

for (const c of corpus.cases) {
	test(`spans agree with the server: ${c.why}`, () => {
		const spans = excludedSpans(c.text).map((s) => [s.start, s.end, s.kind]);
		assert.deepEqual(spans, c.spans);
	});

	test(`the cut text agrees with the server: ${c.why}`, () => {
		assert.equal(pipelineDescription(c.text), c.pipeline);
	});
}

test('the segments rebuild the original text exactly', () => {
	for (const c of corpus.cases) {
		assert.equal(
			labelSegments(c.text)
				.map((s) => s.text)
				.join(''),
			c.text,
			c.why
		);
	}
});

test('every greyed segment is one the server would drop', () => {
	for (const c of corpus.cases) {
		const greyed = labelSegments(c.text)
			.filter((s) => s.kind !== null)
			.map((s) => s.text)
			.join('');
		for (const [start, end] of c.spans) {
			assert.ok(greyed.includes(c.text.slice(start, end)), c.why);
		}
	}
});
