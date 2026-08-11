# inku-cli

Command line client for controlling an inku API server.

## Signing in, and when it is not needed

Most commands need a session: run `inku-cli login` once and it is stored.

A server in single-user mode (`INKU_SINGLE_USER=1`) belongs to one person and
answers an unauthenticated request as them, so every command works there
without logging in at all. Against any other server the commands still ask you
to log in first, and say so.

## Save generated drawings to normal history

Use `--save-history` with `paint` or `batch` when benchmark outputs should be
available later through the regular server history UI/API:

```sh
inku-cli paint "緑の弧を右上に置く" --save-history
```

To render from already-normalized DDL, bypass Stage 1 and send the text directly
through Stage 2/rendering:

```sh
inku-cli paint "白い背景に黒い線を一本引く。" --input-mode ddl --save-history
```

## List history, with or without the drawings

`history` returns each work's whole SVG by default, which is what makes it
usable for anything that needs the picture. A listing of 21 works is about
23.5 MB that way, and about 1.0 MB without them, so pass `--no-svg` when the
listing is being read for its metadata:

```sh
inku-cli history --limit 21                 # every work carries its drawing
inku-cli history --limit 21 --no-svg        # svg comes back as an empty string
```

The `svg` key is present either way. `--no-svg` empties it rather than removing
it, so a reader that expects the field still finds it.

## Share one work with someone else

By default a work is visible to whoever made it. What an admin or a group leader
can reach beyond that is decided by their permission group; anything else has to
be given away one work at a time:

```sh
inku-cli history share <item_id> --to-user <user_id> --permission read
inku-cli history share <item_id> --to-group <group_id> --permission write
inku-cli history unshare <item_id> --to-user <user_id>
inku-cli history acl <item_id>
inku-cli history peers                     # the members of your own organisation, with their IDs
```

`read` lets them open the work; `write` also lets them star, trash and delete it.
Only the owner and an admin may share — being able to read a work is not
permission to hand it on. Sharing takes an ID; `history peers` is where to find
one, and it answers with your own organisation only. The full member directory
stays where it was, readable by a member manager.

A work you can read can be varied, and the variation keeps the connection rather
than copying anything: `inku-cli refine perform <their_item_id> …` records their
work as your work's parent. In `inku-cli lineage show`, a parent you cannot read
prints as `[Private]` rather than `[Deleted]` — it still exists, and its owner
can still give it to you.

## Hand a single-user server to a different account

On a server in single-user mode, one account is the one it opens as. It can be
moved, and the move takes effect at the next automatic login rather than
throwing out the session doing the moving:

```sh
inku-cli single-user show          # who it opens as, and who else could
inku-cli single-user set <user_id> # move it; the account must hold `admins`
```

## Export saved history by render hash

`history-export` selects drawings stored in the server history DB by render hash suffix and writes a review bundle:

```sh
inku-cli history-export F3DE HH45 --out-dir cli/out/review-set
inku-cli history-export --from F3DE --to HH45 --out-dir cli/out/review-set
```

The output directory contains:

- `contact-sheet.png`: a PNG contact sheet for visual review.
- `summary.json`: aggregate metrics and `ai_evaluation.items` for AI-assisted evaluation.
- `items/*.json`: one full history JSON per selected drawing.
- `items/*.svg` and `items/*.png`: per-drawing source SVG and rendered PNG.

Hash suffixes are matched against `render_hash_short` or the trailing characters of `render_hash`. If a suffix is ambiguous, use more characters.

## Adjust the render limits

Nine numbers decide how many marks a work may carry. They are not performance
tuning — they decide how many lines get drawn, so they change the picture. They
are stored on the server, so `config` reads and writes them:

```sh
inku-cli config show
inku-cli config update --limit-literal-count-threshold 480
inku-cli config update --limit-max-expanded-primitives 900 --limit-max-expanded-per-instruction 480
inku-cli config update --limits-reset
```

Only the flags given are sent; the server merges them over what is stored. A set
that contradicts itself is **rounded down, not rejected** — asking for a
represented band above the literal threshold lowers the band — and the response
is the set that actually took effect, so read it rather than assuming the
request was honoured.

Three families, in the order `config show` reports them:

| flag | what changes |
|---|---|
| `--limit-max-expanded-primitives` | marks per work; past it the whole work is scaled down |
| `--limit-max-expanded-per-instruction` | marks one instruction may expand to |
| `--limit-max-instructions` | instructions per work; the list is truncated past it |
| `--limit-literal-count-threshold` | below it a stated number is drawn as stated; at or above it the group is shown as a band |
| `--limit-represented-count-min` / `-max` | the two ends of that band |
| `--limit-ddl-count-max` | ceiling on a numeral read out of the description, and the top of the density bands Stage 1 is told to use |
| `--limit-ddl-count-max-grid` | the same ceiling for a literal grid |
| `--limit-schema-count-max` | the only bound checked on Stage 2's own output |

The effective values are written into the Stage 1 and Stage 2 prompts, so the
model is told the rule the pipeline will actually apply, and `stage2_prompt_digest`
moves with them. They are also recorded on every work in `history.render_limits`,
so a drawing made under one configuration can still be told apart from the same
description drawn under another. A work saved before this column existed carries
no value at all, which is not the same as carrying the defaults.

## Command Line Help Reference

<!-- HELP_START -->

### `inku-cli`

```
usage: inku-cli [-h]
                {login,logout,me,models,paint,batch,contact-sheet,rasterize,analyze,ddl-compare,vision-review,render-score,demo-instruction,history,unread-words,history-export,api,plugin,reference,version,lineage,colophon,refine,inspect,review,user,single-user,group,config}
                ...

Control an inku API server from the command line

positional arguments:
  {login,logout,me,models,paint,batch,contact-sheet,rasterize,analyze,ddl-compare,vision-review,render-score,demo-instruction,history,unread-words,history-export,api,plugin,reference,version,lineage,colophon,refine,inspect,review,user,single-user,group,config}
    login               log in and store an API session
    logout              log out and clear the stored session
    me                  show the current logged-in user
    models              show or set CLI default LLM and Vision models
    paint               generate one drawing
    batch               generate drawings from a prompt list
    contact-sheet       create a contact sheet from PNG files in a directory
    rasterize           rasterize a directory of SVG files to PNG
    analyze             analyze generated PNG/JSON outputs
    ddl-compare         compare normalized DDL artifacts side by side
    vision-review       use the configured NIM vision model as a read-only
                        visual mirror
    render-score        render a Score JSON object without Stage 1 or Stage 2
    demo-instruction    generate one demo prompt from a seed phrase
    history             list history items
    unread-words        report words the interpreter could not confidently
                        read
    history-export      export history items by hash for benchmark review
    api                 call any public inku HTTP API endpoint with the stored
                        session
    plugin              inspect and reload declarative DDL plugins
    reference           dump implementation vocabulary and constant tables
                        (read-only mirror)
    version             show CLI and server version/build information
    lineage             show or control the lineage of a work
    colophon            recite one root-to-target lineage branch as an append-
                        only reading
    refine              refine an existing work
    inspect             parallel model inspection comparison
    review              evaluate drawings and submit feedback
    user                manage user accounts
    single-user         show or move the account this server opens as
    group               manage user groups
    config              manage system settings

options:
  -h, --help            show this help message and exit

```

### `inku-cli login`

```
usage: inku-cli login [-h] [--base-url BASE_URL]
                      [--timeout-seconds TIMEOUT_SECONDS] --username USERNAME
                      [--password PASSWORD]

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --username USERNAME, -u USERNAME
  --password PASSWORD, -p PASSWORD

```

### `inku-cli logout`

```
usage: inku-cli logout [-h] [--base-url BASE_URL]
                       [--timeout-seconds TIMEOUT_SECONDS]

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)

```

### `inku-cli me`

```
usage: inku-cli me [-h] [--base-url BASE_URL]
                   [--timeout-seconds TIMEOUT_SECONDS]

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)

```

### `inku-cli models`

```
usage: inku-cli models [-h] [--base-url BASE_URL]
                       [--timeout-seconds TIMEOUT_SECONDS]
                       [--stage1-provider {nvidia,anthropic,local}]
                       [--stage1-model STAGE1_MODEL]
                       [--stage2-provider {nvidia,anthropic,local}]
                       [--stage2-model STAGE2_MODEL]
                       [--vision-provider {nvidia,anthropic,local}]
                       [--vision-model VISION_MODEL]
                       [--color-catalog COLOR_CATALOG]

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --stage1-provider {nvidia,anthropic,local}
                        save the default Stage 1 provider
  --stage1-model STAGE1_MODEL
                        save the default Stage 1 model for paint and batch
  --stage2-provider {nvidia,anthropic,local}
                        save the default Stage 2 provider
  --stage2-model STAGE2_MODEL
                        save the default Stage 2 LLM model for paint and batch
  --vision-provider {nvidia,anthropic,local}
                        save the default Vision provider
  --vision-model VISION_MODEL
                        save the default Vision model for image-reading
                        operations
  --color-catalog COLOR_CATALOG
                        save the default server color catalog for paint and
                        batch

```

### `inku-cli paint`

```
usage: inku-cli paint [-h] [--base-url BASE_URL]
                      [--timeout-seconds TIMEOUT_SECONDS] [--file FILE]
                      [--out-dir OUT_DIR] [--prefix PREFIX] [--png]
                      [--svg-profile {display,editable,compat}]
                      [--input-mode {paint,ddl}]
                      [--stage1-provider {nvidia,anthropic,local}]
                      [--stage1-model STAGE1_MODEL]
                      [--stage2-provider {nvidia,anthropic,local}]
                      [--stage2-model STAGE2_MODEL]
                      [--history-input HISTORY_INPUT]
                      [--catalog-id CATALOG_ID]
                      [--color-catalog COLOR_CATALOG]
                      [--canvas-aspect {square,golden,a4,b4,pillar,oban,wide,byobu,vertical}]
                      [--render-seed RENDER_SEED]
                      [--composition-seed COMPOSITION_SEED]
                      [--seed-text SEED_TEXT] [--sketch]
                      [--sketch-grain {fine,coarse}]
                      [--sketch-text SKETCH_TEXT]
                      [--variation-amplitude {small,medium,large}]
                      [--variation-seed VARIATION_SEED] [--wild]
                      [--catalog-mode {fixed,auto,random}]
                      [--interpretation-seed INTERPRETATION_SEED]
                      [--instruction-lang {auto,ja,en}] [--ui-lang UI_LANG]
                      [--include-thinking] [--save-history]
                      [--save-artifacts | --no-save-artifacts] [--no-progress]
                      [--trace] [--full-json]
                      [text]

positional arguments:
  text                  the description to draw

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --file FILE, -f FILE  read the description from a UTF-8 file, or '-'
  --out-dir OUT_DIR, -o OUT_DIR
                        directory for JSON/SVG/PNG outputs
  --prefix PREFIX       output filename prefix
  --png                 also render PNG output when --out-dir is set
  --svg-profile {display,editable,compat}
                        SVG output profile for saved files
  --input-mode {paint,ddl}
                        paint: a natural-language description through Stage 1;
                        ddl: normalized DDL directly through Stage 2/render
  --stage1-provider {nvidia,anthropic,local}
  --stage1-model STAGE1_MODEL
  --stage2-provider {nvidia,anthropic,local}
  --stage2-model STAGE2_MODEL
  --history-input HISTORY_INPUT
  --catalog-id CATALOG_ID
                        color catalog id (legacy alias)
  --color-catalog COLOR_CATALOG
                        server color catalog id for renderer and benchmark
                        tracing
  --canvas-aspect {square,golden,a4,b4,pillar,oban,wide,byobu,vertical}
                        canvas aspect id for paint, compose, and history
  --render-seed RENDER_SEED
                        renderer performance seed for reproducible replay
  --composition-seed COMPOSITION_SEED
                        seed for where the marks are placed; without it the
                        placement follows --render-seed
  --seed-text SEED_TEXT
                        explicit text used only to derive the renderer
                        performance seed
  --sketch              run the description through the sketch-from-life layer
                        (Stage 0.5) before Stage 1, so the later stages read
                        the sketch instead of the description; server default
                        is off, the web UI default is fine
  --sketch-grain {fine,coarse}
                        how finely Stage 0.5 breaks the description apart:
                        fine (server default) or coarse
  --sketch-text SKETCH_TEXT
                        use this sketch text instead of calling Stage 0.5
                        (replay of a saved or hand-edited sketch)
  --variation-amplitude {small,medium,large}
                        how far the variation layer moves the expansion axes;
                        takes effect only together with --variation-seed
  --variation-seed VARIATION_SEED
                        which axes the variation layer moves and in which
                        direction; takes effect only together with
                        --variation-amplitude
  --wild                remove the amplitude ceiling on the stroke
                        performance, letting the renderer swing further
  --catalog-mode {fixed,auto,random}
                        how the color catalog is chosen: fixed (use --color-
                        catalog), auto (the server reads the description and
                        picks), random (draw one other than --color-catalog)
  --interpretation-seed INTERPRETATION_SEED
                        ask Stage 1 for an explicit re-interpretation under
                        this identifier instead of reusing the previous
                        reading
  --instruction-lang {auto,ja,en}
  --ui-lang UI_LANG
  --include-thinking
  --save-history
  --save-artifacts, --no-save-artifacts
  --no-progress         disable elapsed-time progress animation
  --trace               request RAW per-layer intermediates and save them as
                        <prefix>-trace.json; in --input-mode ddl this is the
                        only way to read what Stage 2 wrote before coerce
                        repaired it
  --full-json           print the full paint response

```

### `inku-cli batch`

```
usage: inku-cli batch [-h] [--base-url BASE_URL]
                      [--timeout-seconds TIMEOUT_SECONDS] --file FILE
                      [--out-dir OUT_DIR] [--prefix PREFIX] [--png]
                      [--svg-profile {display,editable,compat}]
                      [--input-mode {paint,ddl}]
                      [--stage1-provider {nvidia,anthropic,local}]
                      [--stage1-model STAGE1_MODEL]
                      [--stage2-provider {nvidia,anthropic,local}]
                      [--stage2-model STAGE2_MODEL]
                      [--history-input HISTORY_INPUT]
                      [--catalog-id CATALOG_ID]
                      [--color-catalog COLOR_CATALOG]
                      [--canvas-aspect {square,golden,a4,b4,pillar,oban,wide,byobu,vertical}]
                      [--render-seed RENDER_SEED]
                      [--composition-seed COMPOSITION_SEED]
                      [--seed-text SEED_TEXT] [--sketch]
                      [--sketch-grain {fine,coarse}]
                      [--sketch-text SKETCH_TEXT]
                      [--variation-amplitude {small,medium,large}]
                      [--variation-seed VARIATION_SEED] [--wild]
                      [--catalog-mode {fixed,auto,random}]
                      [--interpretation-seed INTERPRETATION_SEED]
                      [--instruction-lang {auto,ja,en}] [--ui-lang UI_LANG]
                      [--include-thinking] [--save-history]
                      [--save-artifacts | --no-save-artifacts] [--no-progress]
                      [--trace] [--continue-on-error]
                      [--summary-json SUMMARY_JSON]
                      [--composition-count COMPOSITION_COUNT]

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --file FILE, -f FILE  UTF-8 text file; one description per non-empty line,
                        or '-'
  --out-dir OUT_DIR, -o OUT_DIR
                        directory for JSON/SVG/PNG outputs
  --prefix PREFIX       output filename prefix
  --png                 also render PNG output when --out-dir is set
  --svg-profile {display,editable,compat}
                        SVG output profile for saved files
  --input-mode {paint,ddl}
                        paint: a natural-language description through Stage 1;
                        ddl: normalized DDL directly through Stage 2/render
  --stage1-provider {nvidia,anthropic,local}
  --stage1-model STAGE1_MODEL
  --stage2-provider {nvidia,anthropic,local}
  --stage2-model STAGE2_MODEL
  --history-input HISTORY_INPUT
  --catalog-id CATALOG_ID
                        color catalog id (legacy alias)
  --color-catalog COLOR_CATALOG
                        server color catalog id for renderer and benchmark
                        tracing
  --canvas-aspect {square,golden,a4,b4,pillar,oban,wide,byobu,vertical}
                        canvas aspect id for paint, compose, and history
  --render-seed RENDER_SEED
                        renderer performance seed for reproducible replay
  --composition-seed COMPOSITION_SEED
                        seed for where the marks are placed; without it the
                        placement follows --render-seed
  --seed-text SEED_TEXT
                        explicit text used only to derive the renderer
                        performance seed
  --sketch              run the description through the sketch-from-life layer
                        (Stage 0.5) before Stage 1, so the later stages read
                        the sketch instead of the description; server default
                        is off, the web UI default is fine
  --sketch-grain {fine,coarse}
                        how finely Stage 0.5 breaks the description apart:
                        fine (server default) or coarse
  --sketch-text SKETCH_TEXT
                        use this sketch text instead of calling Stage 0.5
                        (replay of a saved or hand-edited sketch)
  --variation-amplitude {small,medium,large}
                        how far the variation layer moves the expansion axes;
                        takes effect only together with --variation-seed
  --variation-seed VARIATION_SEED
                        which axes the variation layer moves and in which
                        direction; takes effect only together with
                        --variation-amplitude
  --wild                remove the amplitude ceiling on the stroke
                        performance, letting the renderer swing further
  --catalog-mode {fixed,auto,random}
                        how the color catalog is chosen: fixed (use --color-
                        catalog), auto (the server reads the description and
                        picks), random (draw one other than --color-catalog)
  --interpretation-seed INTERPRETATION_SEED
                        ask Stage 1 for an explicit re-interpretation under
                        this identifier instead of reusing the previous
                        reading
  --instruction-lang {auto,ja,en}
  --ui-lang UI_LANG
  --include-thinking
  --save-history
  --save-artifacts, --no-save-artifacts
  --no-progress         disable elapsed-time progress animation
  --trace               request RAW per-layer intermediates and save them as
                        <prefix>-trace.json; in --input-mode ddl this is the
                        only way to read what Stage 2 wrote before coerce
                        repaired it
  --continue-on-error
  --summary-json SUMMARY_JSON
                        write batch summary JSON to this path (default:
                        OUT_DIR/analysis-summary.json)
  --composition-count COMPOSITION_COUNT
                        generate N Stage 1.5 variations per description

```

### `inku-cli contact-sheet`

```
usage: inku-cli contact-sheet [-h] [--output OUTPUT] [--columns COLUMNS]
                              [--thumb-size THUMB_SIZE]
                              [--order {name,similarity}]
                              input_dir

positional arguments:
  input_dir             directory containing PNG outputs

options:
  -h, --help            show this help message and exit
  --output OUTPUT, -o OUTPUT
                        output PNG path (default: INPUT_DIR/contact-sheet.png)
  --columns COLUMNS
  --thumb-size THUMB_SIZE
  --order {name,similarity}

```

### `inku-cli rasterize`

```
usage: inku-cli rasterize [-h] --in INPUT_DIR --out OUTPUT_DIR [--width WIDTH]
                          [--workers WORKERS]

options:
  -h, --help         show this help message and exit
  --in INPUT_DIR     directory to read .svg files from
  --out OUTPUT_DIR   directory to write .png files to, created if absent
  --width WIDTH      render at this pixel width instead of the width each SVG
                     declares
  --workers WORKERS  rasterize this many files at once; each file still gets
                     its own process

```

### `inku-cli analyze`

```
usage: inku-cli analyze [-h] [--base-url BASE_URL]
                        [--timeout-seconds TIMEOUT_SECONDS] [--diversity]
                        [--census] [--history] [--output OUTPUT]
                        [--replay REPLAY] [--replay-limit REPLAY_LIMIT]
                        [--canvas-aspect {square,golden,a4,b4,pillar,oban,wide,byobu,vertical}]
                        [--catalog-id CATALOG_ID]
                        [--color-catalog COLOR_CATALOG]
                        [input_dir]

positional arguments:
  input_dir             directory containing PNG and JSON outputs

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --diversity           compute diversity metrics and write diversity-
                        summary.json
  --census              report frequent mechanical motif signatures with
                        thumbnail examples
  --history             run --census over the current user history instead of
                        a directory
  --output OUTPUT, -o OUTPUT
                        summary JSON path (default: INPUT_DIR/diversity-
                        summary.json)
  --replay REPLAY       render each sampled score 2N times: N varying
                        composition_seed (composition_distance) and N varying
                        render_seed (performance_distance), each pinning the
                        other seed
  --replay-limit REPLAY_LIMIT
                        maximum score artifacts to replay
  --canvas-aspect {square,golden,a4,b4,pillar,oban,wide,byobu,vertical}
  --catalog-id CATALOG_ID
                        color catalog id (legacy alias)
  --color-catalog COLOR_CATALOG
                        server color catalog id for replay rendering

```

### `inku-cli ddl-compare`

```
usage: inku-cli ddl-compare [-h] [--output OUTPUT] input_dirs [input_dirs ...]

positional arguments:
  input_dirs            two or more artifact directories

options:
  -h, --help            show this help message and exit
  --output OUTPUT, -o OUTPUT

```

### `inku-cli vision-review`

```
usage: inku-cli vision-review [-h] [--vision-model VISION_MODEL]
                              [--model MODEL] [--output OUTPUT]
                              input_dir

positional arguments:
  input_dir

options:
  -h, --help            show this help message and exit
  --vision-model VISION_MODEL
                        Vision model (defaults to the CLI Vision setting)
  --model MODEL         compatibility alias for --vision-model
  --output OUTPUT, -o OUTPUT

```

### `inku-cli render-score`

```
usage: inku-cli render-score [-h] [--base-url BASE_URL]
                             [--timeout-seconds TIMEOUT_SECONDS] [--file FILE]
                             [--ddl-text DDL_TEXT] [--ddl-file PATH]
                             [--out-dir OUT_DIR] [--prefix PREFIX] [--png]
                             [--svg-profile {display,editable,compat}]
                             [--canvas-aspect CANVAS_ASPECT]
                             [--render-seed RENDER_SEED]
                             [--composition-seed COMPOSITION_SEED]
                             [--catalog-id CATALOG_ID]
                             [--color-catalog COLOR_CATALOG]
                             [--from-work WORK_ID] [--full-json]
                             [score]

positional arguments:
  score                 Score JSON text

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --file FILE, -f FILE  read Score JSON from a file, or '-'
  --ddl-text DDL_TEXT   hand this DDL to coerce, so DDL-driven repairs run as
                        they do in paint
  --ddl-file PATH       hand DDL from a file, or '-' for standard input, to
                        coerce so DDL-driven repairs run
  --out-dir OUT_DIR, -o OUT_DIR
                        directory for JSON/SVG/PNG outputs
  --prefix PREFIX       output filename prefix
  --png                 also render PNG output when --out-dir is set
  --svg-profile {display,editable,compat}
  --canvas-aspect CANVAS_ASPECT
  --render-seed RENDER_SEED
                        renderer performance seed for reproducible replay
  --composition-seed COMPOSITION_SEED
                        seed for where the marks are placed; without it the
                        placement follows --render-seed
  --catalog-id CATALOG_ID
                        color catalog id (legacy alias)
  --color-catalog COLOR_CATALOG
                        server color catalog id
  --from-work WORK_ID   draw in the colors that work was drawn in, not in
                        today's definition of its catalog; a renamed or
                        retired catalog still draws
  --full-json           print SVG and Score as well

```

### `inku-cli demo-instruction`

```
usage: inku-cli demo-instruction [-h] [--base-url BASE_URL]
                                 [--timeout-seconds TIMEOUT_SECONDS]
                                 [--model MODEL]
                                 [--instruction-lang {auto,ja,en}]
                                 [--ui-lang UI_LANG]
                                 seed_phrase

positional arguments:
  seed_phrase

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --model MODEL
  --instruction-lang {auto,ja,en}
  --ui-lang UI_LANG

```

### `inku-cli history`

```
usage: inku-cli history [-h] [--base-url BASE_URL]
                        [--timeout-seconds TIMEOUT_SECONDS] [--offset OFFSET]
                        [--limit LIMIT] [--query QUERY] [--starred]
                        [--for-revision]
                        {share,unshare,acl,peers} ...

positional arguments:
  {share,unshare,acl,peers}
    share               let another member see or change one work
    unshare             take one member's access to a work away again
    acl                 show who else may see or change one work
    peers               list the members of your own organisation, to share a
                        work with

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --offset OFFSET
  --limit LIMIT
  --query QUERY, -q QUERY
  --starred
  --for-revision

```

### `inku-cli history share`

```
usage: inku-cli history share [-h] (--to-user TO_USER | --to-group TO_GROUP)
                              [--permission {read,write}]
                              item_id

positional arguments:
  item_id               the work to share

options:
  -h, --help            show this help message and exit
  --to-user TO_USER     user ID to share it with
  --to-group TO_GROUP   organisation group ID to share it with
  --permission {read,write}
                        read lets them open it; write also lets them star,
                        trash and delete it

```

### `inku-cli history unshare`

```
usage: inku-cli history unshare [-h] (--to-user TO_USER | --to-group TO_GROUP)
                                item_id

positional arguments:
  item_id              the work to stop sharing

options:
  -h, --help           show this help message and exit
  --to-user TO_USER    user ID to remove
  --to-group TO_GROUP  organisation group ID to remove

```

### `inku-cli history acl`

```
usage: inku-cli history acl [-h] item_id

positional arguments:
  item_id     the work to inspect

options:
  -h, --help  show this help message and exit

```

### `inku-cli history peers`

```
usage: inku-cli history peers [-h]

options:
  -h, --help  show this help message and exit

```

### `inku-cli unread-words`

```
usage: inku-cli unread-words [-h] [--base-url BASE_URL]
                             [--timeout-seconds TIMEOUT_SECONDS] [--all]
                             [--limit LIMIT]

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --all                 admin-only aggregate across users
  --limit LIMIT

```

### `inku-cli history-export`

```
usage: inku-cli history-export [-h] [--base-url BASE_URL]
                               [--timeout-seconds TIMEOUT_SECONDS]
                               [--from FROM_HASH] [--to TO_HASH] --out-dir
                               OUT_DIR [--columns COLUMNS]
                               [--thumb-size THUMB_SIZE] [--query QUERY]
                               [--starred] [--for-revision]
                               [hashes ...]

positional arguments:
  hashes                individual 4+ character history hash suffixes

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --from FROM_HASH      start hash suffix for an inclusive history-order range
  --to TO_HASH          end hash suffix for an inclusive history-order range
  --out-dir OUT_DIR, -o OUT_DIR
                        output directory for contact sheet and JSON files
  --columns COLUMNS
  --thumb-size THUMB_SIZE
  --query QUERY, -q QUERY
                        filter history before resolving hashes
  --starred             filter history to starred items before resolving
                        hashes
  --for-revision        filter history to items marked for revision before
                        resolving hashes

```

### `inku-cli api`

```
usage: inku-cli api [-h] [--base-url BASE_URL]
                    [--timeout-seconds TIMEOUT_SECONDS] [--data DATA]
                    [--file FILE] [--query KEY=VALUE] [--header KEY=VALUE]
                    [--no-auth] [--output OUTPUT]
                    {GET,POST,PUT,PATCH,DELETE} path

positional arguments:
  {GET,POST,PUT,PATCH,DELETE}
  path                  relative endpoint path, for example
                        /api/lineage/NODE_ID

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --data DATA           JSON request body
  --file FILE, -f FILE  read JSON request body from a UTF-8 file, or '-'
  --query KEY=VALUE
  --header KEY=VALUE
  --no-auth             omit the stored session for public endpoints
  --output OUTPUT, -o OUTPUT
                        write the raw response body to a file

```

### `inku-cli plugin`

```
usage: inku-cli plugin [-h] [--base-url BASE_URL]
                       [--timeout-seconds TIMEOUT_SECONDS]
                       {list,validate,reload} ...

positional arguments:
  {list,validate,reload}
    list                list loaded and rejected plugin documents
    validate            validate one local plugin document on the server
    reload              reload the server plugin directory without restart

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)

```

### `inku-cli plugin list`

```
usage: inku-cli plugin list [-h]

options:
  -h, --help  show this help message and exit

```

### `inku-cli plugin validate`

```
usage: inku-cli plugin validate [-h] file

positional arguments:
  file        UTF-8 .inku-plugin.md file

options:
  -h, --help  show this help message and exit

```

### `inku-cli plugin reload`

```
usage: inku-cli plugin reload [-h]

options:
  -h, --help  show this help message and exit

```

### `inku-cli reference`

```
usage: inku-cli reference [-h] [--base-url BASE_URL]
                          [--timeout-seconds TIMEOUT_SECONDS] [--md | --json]
                          [--output OUTPUT]

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --md                  Markdown output (default)
  --json                JSON output
  --output OUTPUT, -o OUTPUT
                        write to FILE instead of stdout

```

### `inku-cli version`

```
usage: inku-cli version [-h] [--base-url BASE_URL]
                        [--timeout-seconds TIMEOUT_SECONDS]

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)

```

### `inku-cli lineage`

```
usage: inku-cli lineage [-h] [--base-url BASE_URL]
                        [--timeout-seconds TIMEOUT_SECONDS]
                        {show,promote} ...

positional arguments:
  {show,promote}
    show                show lineage tree for a work
    promote             promote a lineage-only node to regular history

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)

```

### `inku-cli lineage show`

```
usage: inku-cli lineage show [-h] [--depth DEPTH] [--limit LIMIT] [--json]
                             item_id

positional arguments:
  item_id        history item ID or lineage node ID

options:
  -h, --help     show this help message and exit
  --depth DEPTH  descendant search depth
  --limit LIMIT  max nodes to load
  --json         output raw JSON

```

### `inku-cli lineage promote`

```
usage: inku-cli lineage promote [-h] node_id

positional arguments:
  node_id     lineage node ID to promote

options:
  -h, --help  show this help message and exit

```

### `inku-cli colophon`

```
usage: inku-cli colophon [-h] [--base-url BASE_URL]
                         [--timeout-seconds TIMEOUT_SECONDS]
                         [--vision-model VISION_MODEL] [--model MODEL]
                         [--language {ja,en}] [--dry-run] [--json]
                         [--output OUTPUT]
                         target

positional arguments:
  target                history item ID or lineage node ID

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --vision-model VISION_MODEL
                        Vision reader model (defaults to CLI/server Vision
                        setting)
  --model MODEL         compatibility alias for --vision-model
  --language {ja,en}
  --dry-run             generate and print without saving
  --json                print the complete response as JSON
  --output OUTPUT, -o OUTPUT
                        also write the recitation body to a UTF-8 file

```

### `inku-cli refine`

```
usage: inku-cli refine [-h] [--base-url BASE_URL]
                       [--timeout-seconds TIMEOUT_SECONDS]
                       {perform,save} ...

positional arguments:
  {perform,save}
    perform             perform a refinement from an existing work
    save                save a candidate score into history connected to a
                        parent

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)

```

### `inku-cli refine perform`

```
usage: inku-cli refine perform [-h] --kind {touch,layout,reading,color}
                               [--description DESCRIPTION] [--save-history]
                               [--no-save] [-o OUT_DIR] [--png]
                               item_id

positional arguments:
  item_id               target history item ID to refine

options:
  -h, --help            show this help message and exit
  --kind {touch,layout,reading,color}
                        refinement element type
  --description DESCRIPTION
                        override the description for layout/reading variations
  --save-history        automatically save the result to history
  --no-save             do not save the result to history
  -o OUT_DIR, --out-dir OUT_DIR
                        save outputs (svg/json) to this directory
  --png                 perform PNG rendering in output directory

```

### `inku-cli refine generate`

```
usage: inku-cli refine generate [-h] --kind {touch,layout,reading,color}
                                [--description DESCRIPTION] [--save-history]
                                [--no-save] [-o OUT_DIR] [--png]
                                item_id

positional arguments:
  item_id               target history item ID to refine

options:
  -h, --help            show this help message and exit
  --kind {touch,layout,reading,color}
                        refinement element type
  --description DESCRIPTION
                        override the description for layout/reading variations
  --save-history        automatically save the result to history
  --no-save             do not save the result to history
  -o OUT_DIR, --out-dir OUT_DIR
                        save outputs (svg/json) to this directory
  --png                 perform PNG rendering in output directory

```

### `inku-cli refine save`

```
usage: inku-cli refine save [-h] --kind {touch,layout,reading,color} --file
                            FILE [--svg-file SVG_FILE] --input-text INPUT_TEXT
                            [--ddl-text DDL_TEXT]
                            [--visibility {normal,lineage_only}]
                            parent_node_id

positional arguments:
  parent_node_id        parent lineage node ID

options:
  -h, --help            show this help message and exit
  --kind {touch,layout,reading,color}
                        derivation kind
  --file FILE           path to Score JSON file
  --svg-file SVG_FILE   path to SVG file
  --input-text INPUT_TEXT
                        original user text
  --ddl-text DDL_TEXT   normalized DDL text
  --visibility {normal,lineage_only}
                        history visibility

```

### `inku-cli inspect`

```
usage: inku-cli inspect [-h] [--base-url BASE_URL]
                        [--timeout-seconds TIMEOUT_SECONDS] --models MODELS -o
                        OUT_DIR [--png]
                        text

positional arguments:
  text                  input text to translate and draw

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --models MODELS       comma-separated list of models to inspect
  -o OUT_DIR, --out-dir OUT_DIR
                        directory to save comparison files
  --png                 generate PNG renderings

```

### `inku-cli review`

```
usage: inku-cli review [-h] [--base-url BASE_URL]
                       [--timeout-seconds TIMEOUT_SECONDS]
                       {evaluate,unread} ...

positional arguments:
  {evaluate,unread}
    evaluate            evaluate drawing visual quality via Vision NIM
    unread              submit an unread word feedback to server

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)

```

### `inku-cli review evaluate`

```
usage: inku-cli review evaluate [-h] [--vision-model VISION_MODEL]
                                [--model MODEL] [--prompt PROMPT]
                                png_file

positional arguments:
  png_file              path to PNG image file of the drawing

options:
  -h, --help            show this help message and exit
  --vision-model VISION_MODEL
                        Vision model (defaults to the CLI Vision setting)
  --model MODEL         compatibility alias for --vision-model
  --prompt PROMPT       override vision review prompt

```

### `inku-cli review unread`

```
usage: inku-cli review unread [-h] --context CONTEXT word

positional arguments:
  word               the word that failed interpretation

options:
  -h, --help         show this help message and exit
  --context CONTEXT  surrounding sentence or prompt context

```

### `inku-cli user`

```
usage: inku-cli user [-h] [--base-url BASE_URL]
                     [--timeout-seconds TIMEOUT_SECONDS]
                     {list,create,update,delete} ...

positional arguments:
  {list,create,update,delete}
    list                list user accounts
    create              create a user account
    update              update a user account
    delete              delete a user account

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)

```

### `inku-cli user list`

```
usage: inku-cli user list [-h]

options:
  -h, --help  show this help message and exit

```

### `inku-cli user create`

```
usage: inku-cli user create [-h] [--permission-group {users,leaders,admins}]
                            [--group-id GROUP_ID]
                            username email password

positional arguments:
  username              new username
  email                 email address
  password              password (min 8 chars)

options:
  -h, --help            show this help message and exit
  --permission-group {users,leaders,admins}
                        what the new member may do; repeat to grant several
                        (default: users)
  --group-id GROUP_ID   assign to a group ID

```

### `inku-cli user update`

```
usage: inku-cli user update [-h] [--username USERNAME] [--email EMAIL]
                            [--password PASSWORD]
                            [--permission-group {users,leaders,admins}]
                            [--group-id GROUP_ID]
                            user_id

positional arguments:
  user_id               target user ID

options:
  -h, --help            show this help message and exit
  --username USERNAME   update username
  --email EMAIL         update email
  --password PASSWORD   update password
  --permission-group {users,leaders,admins}
                        replace what the member may do; repeat to grant
                        several
  --group-id GROUP_ID   update group ID

```

### `inku-cli user delete`

```
usage: inku-cli user delete [-h] [--cascade] user_id

positional arguments:
  user_id     target user ID

options:
  -h, --help  show this help message and exit
  --cascade   cascade delete user's generation history

```

### `inku-cli single-user`

```
usage: inku-cli single-user [-h] [--base-url BASE_URL]
                            [--timeout-seconds TIMEOUT_SECONDS]
                            {show,set} ...

positional arguments:
  {show,set}
    show                show which account the app opens as, and who else
                        could
    set                 hand the server to another account from the next
                        automatic login on

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)

```

### `inku-cli single-user show`

```
usage: inku-cli single-user show [-h]

options:
  -h, --help  show this help message and exit

```

### `inku-cli single-user set`

```
usage: inku-cli single-user set [-h] user_id

positional arguments:
  user_id     the account to open as; it must hold the admins permission group

options:
  -h, --help  show this help message and exit

```

### `inku-cli group`

```
usage: inku-cli group [-h] [--base-url BASE_URL]
                      [--timeout-seconds TIMEOUT_SECONDS]
                      {list,create,update,delete} ...

positional arguments:
  {list,create,update,delete}
    list                list user groups
    create              create a user group
    update              update a user group
    delete              delete a user group

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)

```

### `inku-cli group list`

```
usage: inku-cli group list [-h]

options:
  -h, --help  show this help message and exit

```

### `inku-cli group create`

```
usage: inku-cli group create [-h] name

positional arguments:
  name        new group name

options:
  -h, --help  show this help message and exit

```

### `inku-cli group update`

```
usage: inku-cli group update [-h] group_id name

positional arguments:
  group_id    target group ID
  name        new name

options:
  -h, --help  show this help message and exit

```

### `inku-cli group delete`

```
usage: inku-cli group delete [-h] group_id

positional arguments:
  group_id    target group ID

options:
  -h, --help  show this help message and exit

```

### `inku-cli config`

```
usage: inku-cli config [-h] [--base-url BASE_URL]
                       [--timeout-seconds TIMEOUT_SECONDS]
                       {show,update} ...

positional arguments:
  {show,update}
    show                show current system configurations
    update              update system configurations

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)

```

### `inku-cli config show`

```
usage: inku-cli config show [-h]

options:
  -h, --help  show this help message and exit

```

### `inku-cli config update`

```
usage: inku-cli config update [-h] [--google-auth {true,false}]
                              [--local-auth {true,false}]
                              [--backup-interval BACKUP_INTERVAL]
                              [--backup-generations BACKUP_GENERATIONS]
                              [--log-retention-days LOG_RETENTION_DAYS]
                              [--log-retention-enabled {true,false}]
                              [--log-compress {true,false}]
                              [--limit-max-expanded-primitives LIMIT_MAX_EXPANDED_PRIMITIVES]
                              [--limit-max-expanded-per-instruction LIMIT_MAX_EXPANDED_PER_INSTRUCTION]
                              [--limit-max-instructions LIMIT_MAX_INSTRUCTIONS]
                              [--limit-literal-count-threshold LIMIT_LITERAL_COUNT_THRESHOLD]
                              [--limit-represented-count-min LIMIT_REPRESENTED_COUNT_MIN]
                              [--limit-represented-count-max LIMIT_REPRESENTED_COUNT_MAX]
                              [--limit-ddl-count-max LIMIT_DDL_COUNT_MAX]
                              [--limit-ddl-count-max-grid LIMIT_DDL_COUNT_MAX_GRID]
                              [--limit-schema-count-max LIMIT_SCHEMA_COUNT_MAX]
                              [--limits-reset]

options:
  -h, --help            show this help message and exit
  --google-auth {true,false}
                        enable/disable Google auth
  --local-auth {true,false}
                        enable/disable local auth
  --backup-interval BACKUP_INTERVAL
                        DB backup interval in days
  --backup-generations BACKUP_GENERATIONS
                        DB backup retention generations
  --log-retention-days LOG_RETENTION_DAYS
                        log retention days
  --log-retention-enabled {true,false}
                        enable/disable log retention
  --log-compress {true,false}
                        compress log files

render limits:
  How many marks a work may carry. Raising these draws more; the effective
  values are written into the Stage 1/2 prompts and recorded on every work.

  --limit-max-expanded-primitives LIMIT_MAX_EXPANDED_PRIMITIVES
                        marks per work; above this the whole work is scaled
                        down to fit
  --limit-max-expanded-per-instruction LIMIT_MAX_EXPANDED_PER_INSTRUCTION
                        marks one instruction may expand to; a larger group is
                        thinned
  --limit-max-instructions LIMIT_MAX_INSTRUCTIONS
                        instructions per work; the list is truncated past this
  --limit-literal-count-threshold LIMIT_LITERAL_COUNT_THRESHOLD
                        below this a stated number is drawn as stated; at or
                        above it the group is shown as a band
  --limit-represented-count-min LIMIT_REPRESENTED_COUNT_MIN
                        low end of the band a too-large group is drawn as
  --limit-represented-count-max LIMIT_REPRESENTED_COUNT_MAX
                        high end of that band; rounded down to the literal
                        threshold
  --limit-ddl-count-max LIMIT_DDL_COUNT_MAX
                        ceiling on a numeral read out of the description, and
                        the top of the density bands Stage 1 is told to use
  --limit-ddl-count-max-grid LIMIT_DDL_COUNT_MAX_GRID
                        the same ceiling for a literal grid, which may go
                        higher than an ordinary arrangement
  --limit-schema-count-max LIMIT_SCHEMA_COUNT_MAX
                        the only bound checked on Stage 2's own output; a
                        larger count is clamped to it
  --limits-reset        put every render limit back to its default, ignoring
                        the other --limit-* flags

```

<!-- HELP_END -->
