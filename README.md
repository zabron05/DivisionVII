# Division VII — WoW Forever Leaderboard

Static GitHub Pages frontend plus scheduled GitHub Actions Python scraper. No Python required on guild members’ computers.

## Publish
1. Create a **public** GitHub repository, e.g. `division-vii-leaderboard`.
2. Upload **all contents** of this folder to the repository root, including `.github/workflows/update.yml`. GitHub's web uploader may hide dot-folders; check that the workflow exists.
3. In **Settings → Pages**, choose **Deploy from a branch**, `main`, `/ (root)`, then Save.
4. In **Settings → Actions → General**, enable workflow permissions **Read and write permissions** (needed for committing roster updates).
5. Open **Actions → Update Armory roster → Run workflow** to trigger the first import.
6. Inspect the action log and the generated `data/leaderboard.json`. The website will be available at `https://USERNAME.github.io/REPOSITORY/`.

The workflow requests the three guild pages every five minutes (best-effort GitHub scheduling). Browser refresh re-reads the latest published JSON; it **does not** trigger a scrape. No data is fabricated if scraping fails. The parser is based on expected Armory markup and has **not been verified against live responses**; if the first job fails, inspect the Actions logs and update the parser. Failed individual guilds retain their last successfully saved roster.

GitHub Pages publishing and scheduled workflows are subject to GitHub policies and limits. The public repo exposes the scraped roster data. Avoid scraping more frequently than necessary and respect the Armory's access policies.
