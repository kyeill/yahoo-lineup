# Notes

## How it decides (RULES.md in code)

- Slot assignment is a greedy over a transversal matroid: players sorted by
  adjusted score, each taken if a G/F/C/Util matching still exists
  (augmenting paths). That is exact for "most filled slots, then best total".
- Places are within Kyle's roster (1 = best), ties averaged. Rank order comes
  from paging `/league/{key}/players;status=T;sort=...` and keeping his
  players in the order Yahoo lists them.
- Through 2026-11-09: 75% % Rostered + 25% pre-season rank (`sort=OR`).
  From 2026-11-10: 75% recent + 25% season (`sort=AR;sort_type=season`).
  Yahoo's API has **no last-14-days** sort; "recent" is the average of the
  `lastweek` and `lastmonth` places.
- "Fewer than 3 games in the last 14 days → season rank only" is NOT built
  yet. Needs live data to see how Yahoo reports games played; do before
  Nov 10.

## Traps already paid for

- Chrome version (retired 2026-10-20): `form_input` on Yahoo's hidden
  position `<select>` changes the DOM but Yahoo never saves it. Only
  click-pill-then-click-pill works. The API avoids all of this.
- GitHub delivers this account's scheduled runs 4-5 hours late, hence the
  early crons. `workflow_dispatch` is unaffected.
- GitHub disables cron in a repo with no commits for 60 days; the workflow
  re-enables itself every run.
- ESPN scoreboard: single-day `dates=` only (ranges 400). Teams are matched
  Yahoo↔ESPN by nickname (last word), since "Los Angeles Clippers" vs
  "LA Clippers".
- A player whose game has started is locked: `is_editable=0` from Yahoo, or
  ESPN game state not `pre`. Locked players keep their slot.
