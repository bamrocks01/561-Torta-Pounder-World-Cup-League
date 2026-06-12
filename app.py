import os
import re
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timezone

st.set_page_config(
    page_title="The 561 Torta Pounder World Cup Draft",
    page_icon="⚽",
    layout="wide",
)

API_BASE = "https://api.football-data.org/v4"
COMPETITION_CODE = "WC"
SEASON = 2026

TEAM_ALIASES = {
    "USA": "United States",
    "United States of America": "United States",
    "USMNT": "United States",
    "Côte d’Ivoire": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "Korea Republic": "South Korea",
    "Republic of Korea": "South Korea",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Bosnia": "Bosnia and Herzegovina",
    "Czech Republic": "Czechia",
    "Curaçao": "Curacao",
    "DR Congo": "Congo",
    "Congo DR": "Congo",
    "Cape Verde": "Cabo Verde",
    "Türkiye": "Turkey",
    "IR Iran": "Iran",
}

# Optional manual correction layer.
# Use this if the API does not expose a knockout/advancement flag exactly how your league wants it.
# Format:
# MANUAL_ADVANCEMENT_BONUSES = {"Brazil": 3, "France": 8}
# Meaning Brazil gets +3 total advancement points, France gets +3 group +5 R32 = +8.
MANUAL_ADVANCEMENT_BONUSES = {}

def normalize_team(name: str) -> str:
    if not name:
        return ""
    name = str(name).strip()
    name = TEAM_ALIASES.get(name, name)
    name = re.sub(r"\s+", " ", name)
    return name

def get_secret_token() -> str:
    try:
        return st.secrets["FOOTBALL_DATA_TOKEN"]
    except Exception:
        return os.getenv("FOOTBALL_DATA_TOKEN", "")

@st.cache_data(ttl=60, show_spinner=False)
def fetch_world_cup_matches(api_token: str) -> list[dict]:
    if not api_token:
        return []
    url = f"{API_BASE}/competitions/{COMPETITION_CODE}/matches"
    params = {"season": SEASON}
    headers = {"X-Auth-Token": api_token}
    response = requests.get(url, params=params, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json().get("matches", [])

def score_match_for_team(match: dict, team: str) -> dict | None:
    home = normalize_team(match.get("homeTeam", {}).get("name"))
    away = normalize_team(match.get("awayTeam", {}).get("name"))
    team = normalize_team(team)

    if team not in {home, away}:
        return None

    status = match.get("status", "")
    utc_date = match.get("utcDate", "")
    stage = match.get("stage", "")
    group = match.get("group", "")
    score = match.get("score", {})

    # football-data.org commonly fills fullTime after regulation/extra time, with penalties separate.
    # Your league rule says shootouts count as a draw, so penalties are intentionally ignored for match-result points.
    full_time = score.get("fullTime") or {}
    regular_time = score.get("regularTime") or {}
    extra_time = score.get("extraTime") or {}

    home_goals = full_time.get("home")
    away_goals = full_time.get("away")

    # Fallbacks for APIs / statuses that fill a different score object first.
    if home_goals is None or away_goals is None:
        home_goals = extra_time.get("home")
        away_goals = extra_time.get("away")
    if home_goals is None or away_goals is None:
        home_goals = regular_time.get("home")
        away_goals = regular_time.get("away")

    is_finished = status in {"FINISHED", "AWARDED"} and home_goals is not None and away_goals is not None
    is_live = status in {"IN_PLAY", "PAUSED", "LIVE"} and home_goals is not None and away_goals is not None

    points = 0
    result = ""
    record_delta = {"W": 0, "D": 0, "L": 0}
    bonus_3_plus = 0
    bonus_shutout = 0

    if is_finished or is_live:
        team_goals = home_goals if team == home else away_goals
        opp_goals = away_goals if team == home else home_goals

        if team_goals > opp_goals:
            points += 3
            result = "W"
            record_delta["W"] = 1 if is_finished else 0
            if team_goals - opp_goals >= 3:
                bonus_3_plus = 1
            if opp_goals == 0:
                bonus_shutout = 1
        elif team_goals == opp_goals:
            points += 1
            result = "D"
            record_delta["D"] = 1 if is_finished else 0
        else:
            result = "L"
            record_delta["L"] = 1 if is_finished else 0

        points += bonus_3_plus + bonus_shutout

    opponent = away if team == home else home
    display_score = ""
    if home_goals is not None and away_goals is not None:
        display_score = f"{home_goals}-{away_goals}" if team == home else f"{away_goals}-{home_goals}"

    return {
        "team": team,
        "opponent": opponent,
        "date": utc_date,
        "stage": stage,
        "group": group,
        "status": status,
        "score": display_score,
        "result": result,
        "match_points": points,
        "win_by_3_bonus": bonus_3_plus,
        "shutout_win_bonus": bonus_shutout,
        "W": record_delta["W"],
        "D": record_delta["D"],
        "L": record_delta["L"],
        "finished": is_finished,
        "live": is_live,
    }

def compute_advancement_bonuses(matches: list[dict], drafted_teams: set[str]) -> dict[str, int]:
    """
    Best-effort automatic bonuses from finished knockout matches.
    Rules from the sheet:
      +3 survive group stage
      +5 win Round of 32
      +7 win Quarterfinal
      +10 win Semifinal
      +15 win Final
      +25 win Cup

    Why this is best-effort:
    APIs vary on whether they expose "qualified", "winner", "stage" and shootout winners.
    This catches winners when the API has winner metadata or a non-tied full-time knockout score.
    For shootouts, manual bonuses may be needed unless the API returns score.winner.
    """
    bonuses = {team: 0 for team in drafted_teams}
    won_r32 = set()
    won_qf = set()
    won_sf = set()
    finalists_won = set()
    knockout_teams_seen = set()

    for match in matches:
        stage = (match.get("stage") or "").upper()
        if "GROUP" in stage:
            continue

        home = normalize_team(match.get("homeTeam", {}).get("name"))
        away = normalize_team(match.get("awayTeam", {}).get("name"))
        for t in (home, away):
            if t in drafted_teams:
                knockout_teams_seen.add(t)

        if match.get("status") not in {"FINISHED", "AWARDED"}:
            continue

        score = match.get("score", {}) or {}
        winner = normalize_team(score.get("winner") or "")
        if winner not in {home, away}:
            ft = score.get("fullTime") or {}
            hg, ag = ft.get("home"), ft.get("away")
            if hg is not None and ag is not None and hg != ag:
                winner = home if hg > ag else away

        if winner not in drafted_teams:
            continue

        if "LAST_32" in stage or "ROUND_OF_32" in stage:
            won_r32.add(winner)
        elif "QUARTER" in stage:
            won_qf.add(winner)
        elif "SEMI" in stage:
            won_sf.add(winner)
        elif "FINAL" in stage and "THIRD" not in stage:
            finalists_won.add(winner)

    for team in knockout_teams_seen:
        bonuses[team] += 3
    for team in won_r32:
        bonuses[team] += 5
    for team in won_qf:
        bonuses[team] += 7
    for team in won_sf:
        bonuses[team] += 10
    for team in finalists_won:
        bonuses[team] += 15 + 25

    for team, bonus in MANUAL_ADVANCEMENT_BONUSES.items():
        bonuses[normalize_team(team)] = bonus

    return bonuses

def build_tables(matches: list[dict], draft_df: pd.DataFrame):
    draft_df = draft_df.copy()
    draft_df["team"] = draft_df["team"].map(normalize_team)

    drafted_teams = set(draft_df["team"])
    rows = []

    for _, drafted in draft_df.iterrows():
        team = drafted["team"]
        owner = drafted["owner"]
        for match in matches:
            scored = score_match_for_team(match, team)
            if scored:
                scored["owner"] = owner
                rows.append(scored)

    match_log = pd.DataFrame(rows)

    if match_log.empty:
        team_table = draft_df.copy()
        team_table["match_points"] = 0
        team_table["advancement_bonus"] = 0
        team_table["total_points"] = 0
        team_table["record"] = "0-0-0"
        return team_table, pd.DataFrame(), pd.DataFrame()

    advancement = compute_advancement_bonuses(matches, drafted_teams)

    grouped = (
        match_log.groupby(["owner", "team"], as_index=False)
        .agg(
            match_points=("match_points", "sum"),
            W=("W", "sum"),
            D=("D", "sum"),
            L=("L", "sum"),
            live_games=("live", "sum"),
        )
    )
    grouped["advancement_bonus"] = grouped["team"].map(advancement).fillna(0).astype(int)
    grouped["total_points"] = grouped["match_points"] + grouped["advancement_bonus"]
    grouped["record"] = grouped["W"].astype(str) + "-" + grouped["D"].astype(str) + "-" + grouped["L"].astype(str)

    all_teams = draft_df.merge(grouped, on=["owner", "team"], how="left").fillna({
        "match_points": 0, "W": 0, "D": 0, "L": 0, "live_games": 0,
        "advancement_bonus": 0, "total_points": 0
    })
    for col in ["match_points", "W", "D", "L", "live_games", "advancement_bonus", "total_points"]:
        all_teams[col] = all_teams[col].astype(int)
    all_teams["record"] = all_teams["W"].astype(str) + "-" + all_teams["D"].astype(str) + "-" + all_teams["L"].astype(str)

    owner_table = (
        all_teams.groupby("owner", as_index=False)
        .agg(
            total_points=("total_points", "sum"),
            match_points=("match_points", "sum"),
            advancement_bonus=("advancement_bonus", "sum"),
            W=("W", "sum"),
            D=("D", "sum"),
            L=("L", "sum"),
            live_games=("live_games", "sum"),
        )
        .sort_values(["total_points", "match_points"], ascending=False)
    )
    owner_table["record"] = owner_table["W"].astype(str) + "-" + owner_table["D"].astype(str) + "-" + owner_table["L"].astype(str)

    return all_teams.sort_values(["owner", "total_points"], ascending=[True, False]), owner_table, match_log

st.title("The 561 Torta Pounder World Cup Draft ⚽️")
st.caption("Live-ish scoring dashboard powered by football-data.org. Cached for 60 seconds to avoid API limits.")

token = get_secret_token()
draft = pd.read_csv("draft_teams.csv")
matches = []

if not token:
    st.warning("Add your FOOTBALL_DATA_TOKEN in Streamlit secrets to pull live World Cup data.")
else:
    try:
        with st.spinner("Pulling latest World Cup scores..."):
            matches = fetch_world_cup_matches(token)
    except Exception as e:
        st.error(f"Could not pull API data: {e}")

team_table, owner_table, match_log = build_tables(matches, draft)

col1, col2, col3 = st.columns(3)
col1.metric("Drafted countries", len(draft))
col2.metric("API matches loaded", len(matches))
col3.metric("Last refreshed", datetime.now().strftime("%I:%M:%S %p"))

st.subheader("League Standings")
if owner_table.empty:
    st.info("No match data yet. Once the API returns World Cup matches, standings will populate here.")
else:
    st.dataframe(
        owner_table[["owner", "total_points", "match_points", "advancement_bonus", "record", "live_games"]],
        use_container_width=True,
        hide_index=True,
    )

st.subheader("Team Scores")
st.dataframe(
    team_table[["owner", "team", "total_points", "match_points", "advancement_bonus", "record", "live_games"]],
    use_container_width=True,
    hide_index=True,
)

with st.expander("Match Log"):
    if match_log.empty:
        st.write("No match log yet.")
    else:
        display = match_log.sort_values(["date", "team"])
        st.dataframe(
            display[["date", "owner", "team", "opponent", "stage", "group", "status", "score", "result", "match_points", "win_by_3_bonus", "shutout_win_bonus"]],
            use_container_width=True,
            hide_index=True,
        )

with st.expander("Scoring Rules"):
    st.markdown("""
**Every Match**
- 3 pts: Win
- 1 pt: Draw
- 0 pts: Loss
- +1 bonus: Win by 3+ goals
- +1 bonus: Shutout win

**Advancement Bonuses**
- +3: Survive group stage
- +5: Win Round of 32
- +7: Win Quarterfinal
- +10: Win Semifinal
- +15: Win the Final
- +25: Win the Cup

**Shootout rule:** counts as a draw for match-result scoring, plus applicable advancement bonus.
""")
