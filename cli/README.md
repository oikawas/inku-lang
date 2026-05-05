# inku-cli

Command line client for controlling an inku API server.

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
