import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync, readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve, join } from 'node:path';
import { createHash } from 'node:crypto';

const root = fileURLToPath(new URL('..', import.meta.url));
const product = resolve(root, '../..');
const adapter = join(root, 'score-adapter');
const output = join(root, 'public/wasm');
const run = (command, args) => execFileSync(command, args, { cwd: product, stdio: 'inherit' });
run(join(product, 'scripts/rust-toolchain.sh'), ['build', '--manifest-path', join(adapter, 'Cargo.toml'), '--target', 'wasm32-unknown-unknown', '--release', '--locked']);
mkdirSync(output, { recursive: true });
run(process.env.WASM_BINDGEN || 'wasm-bindgen', [join(adapter, 'target/wasm32-unknown-unknown/release/inku_ddl_3d_adapter.wasm'), '--target', 'web', '--out-name', 'score_adapter', '--out-dir', output]);
const git = (...args) => execFileSync('git', ['-C', product, ...args], { encoding: 'utf8' });
const diff = git('diff', 'HEAD', '--', 'core');
const source = createHash('sha256');
for (const path of git('ls-files', '--cached', '--others', '--exclude-standard', '--', 'core').trim().split('\n').sort()) {
  source.update(path + '\0'); source.update(readFileSync(join(product, path))); source.update('\0');
}
writeFileSync(join(output, 'provenance.json'), JSON.stringify({
  adapterVersion: '0.1.0', mappingVersion: 'solid-mapping-v1',
  coreBaseSha: git('rev-parse', 'HEAD').trim(), coreTrackedDiffSha256: createHash('sha256').update(diff).digest('hex'),
  coreHasLocalChanges: !!git('status', '--porcelain', '--', 'core').trim(),
  coreSourceSha256: source.digest('hex'),
}, null, 2) + '\n');

const notices = ['Third-party software in the DDL 3D experiment\n', readFileSync(join(product, 'LICENSE'), 'utf8')];
function licenses(directory, heading) {
  const files = readdirSync(directory).filter(name => /^(LICENSE|LICENCE|COPYING|NOTICE)([-_.]|$)/i.test(name));
  if (!files.length) throw new Error(`Missing license texts: ${heading}`);
  for (const name of files) notices.push(`\n===== ${heading} / ${name} =====\n`, readFileSync(join(directory, name), 'utf8'));
}
for (const name of ['three', 'three-bvh-csg', 'three-mesh-bvh']) {
  const directory = join(root, 'node_modules', name), info = JSON.parse(readFileSync(join(directory, 'package.json'), 'utf8'));
  licenses(directory, `${name} ${info.version} (${info.license})`);
}
const metadata = JSON.parse(execFileSync(join(product, 'scripts/rust-toolchain.sh'), ['metadata', '--manifest-path', join(adapter, 'Cargo.toml'), '--locked', '--offline', '--format-version', '1'], { encoding: 'utf8', maxBuffer: 16 << 20 }));
for (const pkg of metadata.packages.filter(p => p.source)) {
  licenses(resolve(pkg.manifest_path, '..'), `${pkg.name} ${pkg.version} (${pkg.license})`);
}
writeFileSync(join(root, 'public/THIRD_PARTY_NOTICES.txt'), notices.join('\n'));
