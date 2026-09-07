import json
import sqlite3

conn = sqlite3.connect("data/ipl.sqlite3")

actual = {
    "vaibhav_runs": conn.execute("select coalesce(sum(batter_runs),0) from deliveries where season_id=2026 and batter in ('V Suryavanshi','Vaibhav Suryavanshi','Vaibhav Sooryavanshi')").fetchone()[0],
    "vaibhav_sixes": conn.execute("select coalesce(sum(case when batter_runs=6 then 1 else 0 end),0) from deliveries where season_id=2026 and batter in ('V Suryavanshi','Vaibhav Suryavanshi','Vaibhav Sooryavanshi')").fetchone()[0],
    "vaibhav_avg": conn.execute("select round(sum(batter_runs)*1.0 / nullif(sum(case when is_wicket=1 and player_out in ('V Suryavanshi','Vaibhav Suryavanshi','Vaibhav Sooryavanshi') and coalesce(wicket_kind,'') not in ('run out','retired hurt','retired out','obstructing the field') then 1 else 0 end),0), 2) from deliveries where season_id=2026 and batter in ('V Suryavanshi','Vaibhav Suryavanshi','Vaibhav Sooryavanshi')").fetchone()[0],
    "rabada_wickets": conn.execute("select coalesce(sum(case when is_wicket=1 and coalesce(wicket_kind,'') not in ('run out','retired hurt','retired out','obstructing the field') then 1 else 0 end),0) from deliveries where season_id=2026 and bowler='K Rabada'").fetchone()[0],
    "kl_highest": conn.execute("select coalesce(max(runs),0) from (select match_id, innings, sum(batter_runs) runs from deliveries where season_id=2026 and batter='KL Rahul' group by match_id, innings)").fetchone()[0],
    "season_fours": conn.execute("select coalesce(sum(case when batter_runs=4 then 1 else 0 end),0) from deliveries where season_id=2026").fetchone()[0],
    "season_sixes": conn.execute("select coalesce(sum(case when batter_runs=6 then 1 else 0 end),0) from deliveries where season_id=2026").fetchone()[0],
    "season_wickets": conn.execute("select coalesce(sum(case when is_wicket=1 and coalesce(wicket_kind,'') not in ('run out','retired hurt','retired out','obstructing the field') then 1 else 0 end),0) from deliveries where season_id=2026").fetchone()[0],
    "season_dot_balls": conn.execute("select coalesce(sum(case when legal_ball=1 and total_runs=0 then 1 else 0 end),0) from deliveries where season_id=2026").fetchone()[0],
}

expected = {
    "vaibhav_runs": 776,
    "vaibhav_avg": 48.50,
    "vaibhav_sixes": 72,
    "rabada_wickets": 29,
    "kl_highest": 152,
    "season_fours": 2332,
    "season_sixes": 1426,
    "season_wickets": 835,
    "season_dot_balls": 5686,
}

report = {"actual": actual, "expected": expected, "mismatches": {}}
for key, exp in expected.items():
    act = actual.get(key)
    if act != exp:
        report["mismatches"][key] = {"expected": exp, "actual": act}

print(json.dumps(report, indent=2))

