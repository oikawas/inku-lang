# inku.ddl3d.v1

Same-origin `postMessage`, with an exact `targetOrigin`. Parent checks `source === iframe.contentWindow`; child checks `source === parent`. Both check the fixed protocol and iframe mount ID. Each parent mount has an independent monotonic positive integer request ID. Old-source, old-mount and old-request messages cannot update the active work.

Parent → child: `load-work {mountId,requestId,inputJson,locale,theme,viewState?}` and `dispose`. `inputJson` is at most 16 MiB of UTF-8. Locale is `ja|en`; theme is `light|dark`. No URLs or credentials are obtained from Score data.

Child → parent: `ready` (request 0), `rendered {inputDigest,objectCount,triangles,bytes,preparationMs}`, `diagnostic {diagnostics}`, `failed {reason}`, `view-state {viewState}`, `return-2d`. The child computes SHA-256 over the exact input JSON in WASM. Stale-result protection uses request/mount identity and does not require WebCrypto on HTTP LAN hosts.

`viewState` contains finite three-element `position`/`target`, positive bounded `zoom`, `projection`, `depth` (solid thickness, 0.1–3), `orthoHeight`, and optional `layerSpacing` (0–3; defaults to 1). Older states remain valid. It is accepted only for the current request and cached with the exact input JSON. No storage API is used.

The child validates size/types before starting a new Worker and terminates the previous Worker/scene. Preparation timeout is 10 seconds. The bridge waits at most 15 seconds for ready/rendered, then provides retry and return-to-2D controls. The bridge and experiment own small copies of this contract so removing the experiment cannot break a Web import.
