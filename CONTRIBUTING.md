# Contributing to Qingwu

Thank you for helping make student work lighter.

## Development

1. Install Node.js 22+, Rust stable, Python 3.12, and the Windows WebView2 runtime.
2. Run `npm install`.
3. Create a Python virtual environment and run `pip install -e .`.
4. Run `npm run dev` for the browser development shell or `npm run tauri dev` for desktop integration.
5. Run `npm test`, `python -m pytest`, `npm run build`, and `cargo test` before opening a PR.

## Pull requests

- Keep changes focused.
- Add tests for behavior changes.
- Never commit real student names, phone numbers, invoices, API keys, or organization-internal documents.
- Workflow templates must be declarative and pass `qingwu template validate`.
- User-facing Chinese text should be concise and natural.
