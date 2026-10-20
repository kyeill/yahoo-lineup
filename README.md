# yahoo-lineup

Sets Kyle's Yahoo fantasy basketball lineup (Multi-Dynasty Basketball, team
"Wish Upon a Sarr") for today plus the next 4 days, using the rules in
[RULES.md](RULES.md). Runs on GitHub Actions through Yahoo's Fantasy API, so
Kyle's PC can be off.

- **Automatic:** several times a day (see `.github/workflows/lineup.yml`).
- **On demand:** GitHub app → this repo → Actions → *Set lineup* →
  *Run workflow*. Tick *dry run* to see the plan without saving.
- **What it did:** open any run; the summary lists each day's moves.
- **When it breaks:** the run fails and GitHub emails Kyle.

Files: `lineup.py` (the bot), `setup_auth.py` (one-time Yahoo sign-in, stores
the three GitHub secrets), `RULES.md` (the agreed logic), `NOTES.md` (traps).
