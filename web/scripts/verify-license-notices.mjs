import { readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const lock = JSON.parse(readFileSync('package-lock.json', 'utf8'));
const manifest = JSON.parse(readFileSync('static/licenses/manifest.json', 'utf8'));

for (const [name, notice] of Object.entries(manifest.packages)) {
	const version = lock.packages[`node_modules/${name}`]?.version;
	if (version !== notice.version) {
		throw new Error(`${name}: notice covers ${notice.version}, lock has ${version ?? 'no entry'}`);
	}
	const path = join('static', 'licenses', notice.file);
	if (statSync(path).size === 0) throw new Error(`${name}: empty license notice: ${path}`);
}

if (statSync('static/licenses/inku-MIT.txt').size === 0) {
	throw new Error('missing inku license notice');
}
