# Security policy

## Supported versions

Until `v1.0.0`, only the latest release receives security fixes.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that may expose API keys,
private student information, or local files. Contact the maintainers privately
using the security contact published in the GitHub repository.

Qingwu is local-first. OpenAI API keys are stored by the Tauri shell in Windows
Credential Manager and must never be written to the SQLite database, logs,
export bundles, or crash reports.
