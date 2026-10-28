import { readFileSync } from 'node:fs';
import { configureModelReferences, loadModelReferences } from '../src/lib/modelReferences.ts';
const fixture = JSON.parse(readFileSync(new URL('../src/lib/model-reference-test-fixtures.json', import.meta.url), 'utf8'));
const key = (q) => JSON.stringify([q.action, q.ref, q.provider ?? '', q.default_provider ?? '']);
const answers = new Map(fixture.queries.map((query, i) => [key(query), fixture.results[i]]));
configureModelReferences(async (_path, init) => {
  const { queries } = JSON.parse(String(init.body));
  const results = queries.map((query) => answers.get(key(query)) ?? {outcome:'refused', reason:'not_in_fixture'});
  return Response.json({ results });
});
await loadModelReferences(fixture.queries);
