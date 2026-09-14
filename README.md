# Dilpat Rai — Social Media Automation

This repository is the permanent source of truth for Dilpat Rai's daily technical social-media content queue and history.

## What runs automatically

GitHub Actions runs the daily workflow at **19:00 Asia/Karachi** and also supports manual runs from the Actions tab.

For each run it:

1. Reads the existing post history.
2. Selects the next topic from `data/topics.json` while avoiding recent repetition.
3. Generates one original Instagram, Facebook, and LinkedIn caption.
4. Generates a fresh technical visual.
5. Performs automated visual QA and retries image generation once if QA fails.
6. Creates a unique `dilpat-YYYY-MM-DD-HHMM-PKT` request ID.
7. Saves the image under `media/YYYY/MM/`.
8. Appends the complete record to `data/posts.json`.
9. Rebuilds `data/posts.csv`.
10. Saves the complete Markdown package under `content/YYYY/MM/`.
11. Commits everything back to `main` with status `ready` and mode `queue`.

The workflow does **not** claim a post was published to Instagram, Facebook, or LinkedIn. It creates and queues the content in GitHub. Actual social-platform publishing can be added later with the appropriate official APIs and secrets.

## Repository structure

```text
.
├── data/
│   ├── posts.json
│   ├── posts.csv
│   ├── topics.json
│   └── settings.json
├── content/
│   └── YYYY/MM/
├── media/
│   └── YYYY/MM/
├── scripts/
│   └── generate_daily_post.py
├── .github/workflows/
│   └── daily-post.yml
└── requirements.txt
```

## Required GitHub secret

Add this repository secret:

`OPENAI_API_KEY`

GitHub: **Settings → Secrets and variables → Actions → New repository secret**.

Never place the API key in source code, JSON, CSV, workflow YAML, or commits.

## Manual test

After adding `OPENAI_API_KEY`, open **Actions → Daily Social Media Post → Run workflow**. The run should generate today's post and commit the result to `main`.

## History policy

Post history is append-only. Existing records are not replaced simply because a new daily post is generated. Duplicate request IDs are rejected, and each generated post keeps its image, captions, alt text, status, timestamps, and error field in the history.

## Brand

- Name: Dilpat Rai
- Role: Software Engineer
- Platforms: Instagram, Facebook, LinkedIn
- Timezone: Asia/Karachi
- Default mode: queue
- Default status: ready

## Security

Do not commit API keys, access tokens, passwords, OAuth credentials, or other secrets. Use GitHub Actions Secrets and official platform integrations for credentials.
