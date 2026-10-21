# Lineup rules — Wish Upon a Sarr

Kyle: these are the agreed rules in plain English. The bot (`lineup.py`)
follows them in code, so to change a rule, tell Claude and it will update
both this file and the code.

League: Multi-Dynasty Basketball (ID 96295), team 1. Roto, daily lineups,
no games-played cap. Active slots: 4 G, 4 F, 2 C, 2 Util. 5 IL slots.

Agreed 2026-10-20.

---

## The rules, in priority order

1. **Fill the most active slots possible** with players who have a game that
   day. Rearrange positions to do it (e.g. move a G/F to F so another guard
   can take G). This beats every other rule.

2. **Out / Injured / Not Active never start.** Move them to IL if an IL slot
   is free (Yahoo only allows IL for Out / Injured, not Not Active).
   **Coming back:** when an IL player is healthy again, move him to the bench
   if a bench spot is free; he is then a normal candidate to start that day.
   If no bench spot is free, a drop is needed — leave it and alert Kyle; the
   bot never drops anyone.

3. **Score each player**, then start the lowest scores. For each factor, rank
   your own players 1 to N (1 = best on the team), then take the weighted
   average of those places:
   - **Through Nov 9:** 75% % Rostered, 25% pre-season rank (there is no
     season rank yet).
   - **From Nov 10:** 75% recent rank, 25% season rank. Yahoo's API has no
     last-14-days rank, so "recent" is the average of last week and last
     month. If a player has fewer than 3 games in the last 14 days, use his
     season rank alone.

4. **Questionable / game-time decision:** double his score.

5. **Doubtful:** start only if the slot would otherwise be empty.

6. **Ties** go to the player with the higher % Rostered.

7. **No games-played cap**, so never hold back a player who has a game.

---

## Ground rules (how the skill behaves)

- **Lineup only.** It never adds, drops, trades or claims anyone.
- **Never touches a locked player** (his game has tipped off).
- **Saves automatically** several times a day; you only hear about it when a
  run fails (GitHub emails you).
- **Every run sets today plus the next 4 days**, so later runs re-check days
  set earlier with fresher injury news.
