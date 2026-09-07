import json
import sqlite3

conn = sqlite3.connect("data/ipl.sqlite3")
conn.row_factory = sqlite3.Row

out = {}
out["vaibhav_runs"] = conn.execute(
    "select sum(batter_runs) from deliveries where season_id=2026 and batter in ('V Suryavanshi','Vaibhav Suryavanshi','Vaibhav Sooryavanshi')"
).fetchone()[0]
out["vaibhav_sixes"] = conn.execute(
    "select sum(case when batter_runs=6 then 1 else 0 end) from deliveries where season_id=2026 and batter in ('V Suryavanshi','Vaibhav Suryavanshi','Vaibhav Sooryavanshi')"
).fetchone()[0]
out["vaibhav_dismissals"] = conn.execute(
    "select sum(case when is_wicket=1 and player_out in ('V Suryavanshi','Vaibhav Suryavanshi','Vaibhav Sooryavanshi') and coalesce(wicket_kind,'') not in ('run out','retired hurt','retired out','obstructing the field') then 1 else 0 end) from deliveries where season_id=2026"
).fetchone()[0]
out["rabada_wickets"] = conn.execute(
    "select sum(case when is_wicket=1 and coalesce(wicket_kind,'') not in ('run out','retired hurt','retired out','obstructing the field') then 1 else 0 end) from deliveries where season_id=2026 and bowler='K Rabada'"
).fetchone()[0]
out["kl_highest"] = conn.execute(
    "select max(runs) from (select match_id, innings, sum(batter_runs) runs from deliveries where season_id=2026 and batter='KL Rahul' group by match_id, innings)"
).fetchone()[0]
out["season_fours"] = conn.execute(
    "select sum(case when batter_runs=4 then 1 else 0 end) from deliveries where season_id=2026"
).fetchone()[0]
out["season_sixes"] = conn.execute(
    "select sum(case when batter_runs=6 then 1 else 0 end) from deliveries where season_id=2026"
).fetchone()[0]
out["season_wickets"] = conn.execute(
    "select sum(case when is_wicket=1 and coalesce(wicket_kind,'') not in ('run out','retired hurt','retired out','obstructing the field') then 1 else 0 end) from deliveries where season_id=2026"
).fetchone()[0]
out["season_dot_balls"] = conn.execute(
    "select sum(case when legal_ball=1 and total_runs=0 then 1 else 0 end) from deliveries where season_id=2026"
).fetchone()[0]

print(json.dumps(out, indent=2))

