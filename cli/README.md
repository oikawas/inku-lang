# inku-cli

Command line client for controlling an inku API server.

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

## Command Line Help Reference

<!-- HELP_START -->

### `inku-cli`

```
usage: inku-cli [-h]
                {login,logout,me,models,paint,batch,contact-sheet,analyze,ddl-compare,vision-review,render-score,demo-instruction,history,unread-words,history-export,api,version,lineage,refine,inspect,review,user,group,config}
                ...

Control an inku API server from the command line

positional arguments:
  {login,logout,me,models,paint,batch,contact-sheet,analyze,ddl-compare,vision-review,render-score,demo-instruction,history,unread-words,history-export,api,version,lineage,refine,inspect,review,user,group,config}
    login               log in and store an API session
    logout              log out and clear the stored session
    me                  show the current logged-in user
    models              show or set CLI default Stage 1 / Stage 2 models
    paint               generate one drawing
    batch               generate drawings from a prompt list
    contact-sheet       create a contact sheet from PNG files in a directory
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
    version             show CLI and server version/build information
    lineage             show or control artwork lineage
    refine              generate refined options from an existing work
    inspect             parallel model inspection comparison
    review              evaluate drawings and submit feedback
    user                manage user accounts
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
                        save the default Stage 2 model for paint and batch
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
                      [--original-text ORIGINAL_TEXT]
                      [--history-input HISTORY_INPUT]
                      [--catalog-id CATALOG_ID]
                      [--color-catalog COLOR_CATALOG]
                      [--canvas-aspect {square,golden,a4,b4,pillar,oban,wide,byobu,vertical}]
                      [--render-seed RENDER_SEED] [--vary-seed VARY_SEED]
                      [--seed-text SEED_TEXT]
                      [--instruction-lang {auto,ja,en}] [--ui-lang UI_LANG]
                      [--include-thinking] [--save-history]
                      [--save-artifacts | --no-save-artifacts] [--no-progress]
                      [--full-json]
                      [text]

positional arguments:
  text                  prompt text

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --file FILE, -f FILE  read prompt text from a UTF-8 file, or '-'
  --out-dir OUT_DIR, -o OUT_DIR
                        directory for JSON/SVG/PNG outputs
  --prefix PREFIX       output filename prefix
  --png                 also render PNG output when --out-dir is set
  --svg-profile {display,editable,compat}
                        SVG output profile for saved files
  --input-mode {paint,ddl}
                        paint: natural-language prompt through Stage 1; ddl:
                        normalized DDL directly through Stage 2/render
  --stage1-provider {nvidia,anthropic,local}
  --stage1-model STAGE1_MODEL
  --stage2-provider {nvidia,anthropic,local}
  --stage2-model STAGE2_MODEL
  --original-text ORIGINAL_TEXT
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
  --vary-seed VARY_SEED
                        Stage 1.5 composition variation seed
  --seed-text SEED_TEXT
                        explicit text used only to derive the renderer
                        performance seed
  --instruction-lang {auto,ja,en}
  --ui-lang UI_LANG
  --include-thinking
  --save-history
  --save-artifacts, --no-save-artifacts
  --no-progress         disable elapsed-time progress animation
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
                      [--original-text ORIGINAL_TEXT]
                      [--history-input HISTORY_INPUT]
                      [--catalog-id CATALOG_ID]
                      [--color-catalog COLOR_CATALOG]
                      [--canvas-aspect {square,golden,a4,b4,pillar,oban,wide,byobu,vertical}]
                      [--render-seed RENDER_SEED] [--vary-seed VARY_SEED]
                      [--seed-text SEED_TEXT]
                      [--instruction-lang {auto,ja,en}] [--ui-lang UI_LANG]
                      [--include-thinking] [--save-history]
                      [--save-artifacts | --no-save-artifacts] [--no-progress]
                      [--continue-on-error] [--summary-json SUMMARY_JSON]
                      [--vary VARY]

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --file FILE, -f FILE  UTF-8 text file; one prompt per non-empty line, or '-'
  --out-dir OUT_DIR, -o OUT_DIR
                        directory for JSON/SVG/PNG outputs
  --prefix PREFIX       output filename prefix
  --png                 also render PNG output when --out-dir is set
  --svg-profile {display,editable,compat}
                        SVG output profile for saved files
  --input-mode {paint,ddl}
                        paint: natural-language prompt through Stage 1; ddl:
                        normalized DDL directly through Stage 2/render
  --stage1-provider {nvidia,anthropic,local}
  --stage1-model STAGE1_MODEL
  --stage2-provider {nvidia,anthropic,local}
  --stage2-model STAGE2_MODEL
  --original-text ORIGINAL_TEXT
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
  --vary-seed VARY_SEED
                        Stage 1.5 composition variation seed
  --seed-text SEED_TEXT
                        explicit text used only to derive the renderer
                        performance seed
  --instruction-lang {auto,ja,en}
  --ui-lang UI_LANG
  --include-thinking
  --save-history
  --save-artifacts, --no-save-artifacts
  --no-progress         disable elapsed-time progress animation
  --continue-on-error
  --summary-json SUMMARY_JSON
                        write batch summary JSON to this path (default:
                        OUT_DIR/analysis-summary.json)
  --vary VARY           generate N Stage 1.5 variations per prompt

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
  --replay REPLAY       render each sampled score N times and compute replay
                        divergence
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
usage: inku-cli vision-review [-h] [--model MODEL] [--output OUTPUT] input_dir

positional arguments:
  input_dir

options:
  -h, --help            show this help message and exit
  --model MODEL
  --output OUTPUT, -o OUTPUT

```

### `inku-cli render-score`

```
usage: inku-cli render-score [-h] [--base-url BASE_URL]
                             [--timeout-seconds TIMEOUT_SECONDS] [--file FILE]
                             [--out-dir OUT_DIR] [--prefix PREFIX] [--png]
                             [--svg-profile {display,editable,compat}]
                             [--canvas-aspect CANVAS_ASPECT]
                             [--render-seed RENDER_SEED]
                             [--vary-seed VARY_SEED] [--catalog-id CATALOG_ID]
                             [--color-catalog COLOR_CATALOG] [--full-json]
                             [score]

positional arguments:
  score                 Score JSON text

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --file FILE, -f FILE  read Score JSON from a file, or '-'
  --out-dir OUT_DIR, -o OUT_DIR
                        directory for JSON/SVG/PNG outputs
  --prefix PREFIX       output filename prefix
  --png                 also render PNG output when --out-dir is set
  --svg-profile {display,editable,compat}
  --canvas-aspect CANVAS_ASPECT
  --render-seed RENDER_SEED
                        renderer performance seed for reproducible replay
  --vary-seed VARY_SEED
                        record Stage 1.5 composition variation seed in output
                        metadata
  --catalog-id CATALOG_ID
                        color catalog id (legacy alias)
  --color-catalog COLOR_CATALOG
                        server color catalog id
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

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)
  --offset OFFSET
  --limit LIMIT
  --query QUERY, -q QUERY
  --starred

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
                               [--starred]
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

### `inku-cli refine`

```
usage: inku-cli refine [-h] [--base-url BASE_URL]
                       [--timeout-seconds TIMEOUT_SECONDS]
                       {generate,save} ...

positional arguments:
  {generate,save}
    generate            generate a variation option from a work
    save                save a candidate score into history connected to a
                        parent

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   inku API base URL (default: http://127.0.0.1:8100)
  --timeout-seconds TIMEOUT_SECONDS
                        HTTP timeout in seconds (default: 600)

```

### `inku-cli refine generate`

```
usage: inku-cli refine generate [-h] --kind {touch,layout,reading,color}
                                [--text TEXT] [--save-history] [--no-save]
                                [-o OUT_DIR] [--png]
                                item_id

positional arguments:
  item_id               target history item ID to refine

options:
  -h, --help            show this help message and exit
  --kind {touch,layout,reading,color}
                        refinement element type
  --text TEXT           override input text for layout/reading variations
  --save-history        automatically save the result to history
  --no-save             do not save the result to history
  -o OUT_DIR, --out-dir OUT_DIR
                        save outputs (svg/json) to this directory
  --png                 generate PNG rendering in output directory

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
usage: inku-cli review evaluate [-h] [--model MODEL] [--prompt PROMPT]
                                png_file

positional arguments:
  png_file         path to PNG image file of the drawing

options:
  -h, --help       show this help message and exit
  --model MODEL    NVIDIA NIM vision model name
  --prompt PROMPT  override vision review prompt

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
usage: inku-cli user create [-h] [--role {user,group_lead,admin}]
                            [--group-id GROUP_ID]
                            username email password

positional arguments:
  username              new username
  email                 email address
  password              password (min 8 chars)

options:
  -h, --help            show this help message and exit
  --role {user,group_lead,admin}
                        user role
  --group-id GROUP_ID   assign to a group ID

```

### `inku-cli user update`

```
usage: inku-cli user update [-h] [--username USERNAME] [--email EMAIL]
                            [--password PASSWORD]
                            [--role {user,group_lead,admin}]
                            [--group-id GROUP_ID]
                            user_id

positional arguments:
  user_id               target user ID

options:
  -h, --help            show this help message and exit
  --username USERNAME   update username
  --email EMAIL         update email
  --password PASSWORD   update password
  --role {user,group_lead,admin}
                        update role
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

```

<!-- HELP_END -->
