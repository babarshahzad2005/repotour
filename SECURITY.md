# Security Policy

## Supported versions

Repotour is pre-1.0. Security fixes go into the latest release only.

## Reporting a vulnerability

Please do not open a public issue for security problems.

Report vulnerabilities privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. If that isn't possible, email babarshahzad2005@gmail.com.

Include what you found, how to reproduce it, and the impact you expect. You can expect an acknowledgement within 7 days. Once a fix is released, the report will be disclosed with credit to you unless you prefer otherwise.

## Scope notes

- Repotour runs `git` locally and reads repository files. It uses the network only when LLM summaries are explicitly enabled with `--summaries`.
- With summaries enabled, the contents of the selected files are sent to the configured provider (Groq by default; local Ollama keeps everything on the machine). Enabling summaries and choosing the provider is the user's decision; Repotour prints which files, which endpoint, and which model it will use before sending. Repotour never ships or stores an API key; it reads one from the environment.
