import os
import re
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

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
FLAGS = {
    "Mexico": "🇲🇽",
    "South Africa": "🇿🇦",
    "South Korea": "🇰🇷",
    "Czechia": "🇨🇿",
    "Canada": "🇨🇦",
    "Bosnia and Herzegovina": "🇧🇦",
    "Qatar": "🇶🇦",
    "Switzerland": "🇨🇭",
    "Brazil": "🇧🇷",
    "Morocco": "🇲🇦",
    "Haiti": "🇭🇹",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "United States": "🇺🇸",
    "USA": "🇺🇸",
    "Paraguay": "🇵🇾",
    "Turkey": "🇹🇷",
    "Australia": "🇦🇺",
    "Germany": "🇩🇪",
    "Curacao": "🇨🇼",
    "Curaçao": "🇨🇼",
    "Ivory Coast": "🇨🇮",
    "Ecuador": "🇪🇨",
    "Netherlands": "🇳🇱",
    "Japan": "🇯🇵",
    "Sweden": "🇸🇪",
    "Tunisia": "🇹🇳",
    "Belgium": "🇧🇪",
    "Egypt": "🇪🇬",
    "Iran": "🇮🇷",
    "New Zealand": "🇳🇿",
    "Spain": "🇪🇸",
    "Cabo Verde": "🇨🇻",
    "Saudi Arabia": "🇸🇦",
    "Uruguay": "🇺🇾",
    "France": "🇫🇷",
    "Senegal": "🇸🇳",
    "Iraq": "🇮🇶",
    "Norway": "🇳🇴",
    "Argentina": "🇦🇷",
    "Algeria": "🇩🇿",
    "Austria": "🇦🇹",
}
MANUAL_ADVANCEMENT_BONUSES = {}


def normalize_team(name: str) -> str:
    if not name:
        return ""
    name = str(name).strip()
    name = TEAM_ALIASES.get(name, name)
    return re.sub(r"\s+", " ", name)

def team_label(team: str) -> str:
    normalized = normalize_team(team)
    value = FLAGS.get(normalized, "")

    if len(value) == 2 and value.isalpha():
        flag = "".join(chr(127397 + ord(char.upper())) for char in value)
        return f"{flag} {normalized}"

    if value:
        return f"{value} {normalized}"

    return f"🏳️ {normalized}"
    
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
    score = match.get("score", {}) or {}

    full_time = score.get("fullTime") or {}
    regular_time = score.get("regularTime") or {}
    extra_time = score.get("extraTime") or {}

    home_goals = full_time.get("home")
    away_goals = full_time.get("away")

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
    bonuses = {team: 0 for team in drafted_teams}
    won_r32 = set()
    won_qf = set()
    won_sf = set()
    won_final = set()
    knockout_teams_seen = set()

    for match in matches:
        stage = (match.get("stage") or "").upper()

        if "GROUP" in stage:
            continue

        home = normalize_team(match.get("homeTeam", {}).get("name"))
        away = normalize_team(match.get("awayTeam", {}).get("name"))

        for team in (home, away):
            if team in drafted_teams:
                knockout_teams_seen.add(team)

        if match.get("status") not in {"FINISHED", "AWARDED"}:
            continue

        score = match.get("score", {}) or {}
        winner = normalize_team(score.get("winner") or "")

        if winner not in {home, away}:
            full_time = score.get("fullTime") or {}
            home_goals = full_time.get("home")
            away_goals = full_time.get("away")

            if home_goals is not None and away_goals is not None and home_goals != away_goals:
                winner = home if home_goals > away_goals else away

        if winner not in drafted_teams:
            continue

        if "LAST_32" in stage or "ROUND_OF_32" in stage:
            won_r32.add(winner)
        elif "QUARTER" in stage:
            won_qf.add(winner)
        elif "SEMI" in stage:
            won_sf.add(winner)
        elif "FINAL" in stage and "THIRD" not in stage:
            won_final.add(winner)

    for team in knockout_teams_seen:
        bonuses[team] += 3

    for team in won_r32:
        bonuses[team] += 5

    for team in won_qf:
        bonuses[team] += 7

    for team in won_sf:
        bonuses[team] += 10

    for team in won_final:
        bonuses[team] += 15 + 25

    for team, bonus in MANUAL_ADVANCEMENT_BONUSES.items():
        bonuses[normalize_team(team)] = bonus

    return bonuses


def build_tables(matches: list[dict], draft_df: pd.DataFrame):
    draft_df = draft_df.copy()
    draft_df.columns = [c.strip().lower() for c in draft_df.columns]

    if "owner" not in draft_df.columns or "team" not in draft_df.columns:
        st.error("draft_teams.csv must have columns named owner and team.")
        st.stop()

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
        team_table["live_games"] = 0

        owner_table = (
            team_table.groupby("owner", as_index=False)
            .agg(
                total_points=("total_points", "sum"),
                match_points=("match_points", "sum"),
                advancement_bonus=("advancement_bonus", "sum"),
                live_games=("live_games", "sum"),
            )
        )

        owner_table["record"] = "0-0-0"

        return team_table, owner_table, match_log

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
    grouped["record"] = (
        grouped["W"].astype(int).astype(str)
        + "-"
        + grouped["D"].astype(int).astype(str)
        + "-"
        + grouped["L"].astype(int).astype(str)
    )

    all_teams = draft_df.merge(grouped, on=["owner", "team"], how="left")

    all_teams = all_teams.fillna(
        {
            "match_points": 0,
            "W": 0,
            "D": 0,
            "L": 0,
            "live_games": 0,
            "advancement_bonus": 0,
            "total_points": 0,
            "record": "0-0-0",
        }
    )

    for col in ["match_points", "W", "D", "L", "live_games", "advancement_bonus", "total_points"]:
        all_teams[col] = all_teams[col].astype(int)

    all_teams["record"] = (
        all_teams["W"].astype(str)
        + "-"
        + all_teams["D"].astype(str)
        + "-"
        + all_teams["L"].astype(str)
    )

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

    owner_table["record"] = (
        owner_table["W"].astype(int).astype(str)
        + "-"
        + owner_table["D"].astype(int).astype(str)
        + "-"
        + owner_table["L"].astype(int).astype(str)
    )

    return (
        all_teams.sort_values(["owner", "total_points"], ascending=[True, False]),
        owner_table,
        match_log,
    )


def pretty_owner_table(df):
    display = df.copy()
    return display.rename(
        columns={
            "owner": "Owner",
            "total_points": "Total",
            "match_points": "Match Pts",
            "advancement_bonus": "Bonus",
            "record": "Record",
            "live_games": "Live",
        }
    )


def pretty_team_table(df):
    display = df.copy()

    if "team" in display.columns:
        display["team"] = display["team"].map(team_label)

    return display.rename(
        columns={
            "owner": "Owner",
            "team": "Country",
            "total_points": "Total",
            "match_points": "Match Pts",
            "advancement_bonus": "Bonus",
            "record": "Record",
            "live_games": "Live",
        }
    )


def pretty_match_log(df):
    display = df.copy()
    return display.rename(
        columns={
            "date": "Date",
            "owner": "Owner",
            "team": "Country",
            "opponent": "Opponent",
            "stage": "Stage",
            "group": "Group",
            "status": "Status",
            "score": "Score",
            "result": "Result",
            "match_points": "Pts",
            "win_by_3_bonus": "3+ Bonus",
            "shutout_win_bonus": "Shutout Bonus",
        }
    )


st.markdown(
    """
<style>
.block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
}

.hero {
    padding: 1.35rem 1.6rem;
    border-radius: 22px;
    background: linear-gradient(135deg, #12372A 0%, #0B1F1A 100%);
    border: 1px solid rgba(255,255,255,0.12);
    margin-bottom: 1.25rem;
}

.hero h1 {
    margin: 0;
    font-size: 42px;
    line-height: 1.1;
    letter-spacing: -0.02em;
}

.hero p {
    margin-top: 0.6rem;
    color: #D1D5DB;
    font-size: 15px;
}

.league-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.1rem 1.25rem;
    margin-bottom: 0.75rem;
    border-radius: 18px;
    background: #111827;
    border: 1px solid #374151;
}

.rank-label {
    color: #FACC15;
    font-size: 18px;
    font-weight: 800;
    margin-bottom: 0.25rem;
}

.owner-name {
    font-size: 25px;
    font-weight: 850;
}

.total-points {
    font-size: 34px;
    font-weight: 900;
    white-space: nowrap;
}

.small-muted {
    color: #9CA3AF;
    font-size: 13px;
}

.country-card {
    padding: 1rem;
    border-radius: 18px;
    background: #111827;
    border: 1px solid #374151;
    margin-bottom: 1rem;
    min-height: 150px;
}

.country-name {
    font-size: 22px;
    font-weight: 850;
    margin-bottom: 0.25rem;
}

.country-owner {
    color: #9CA3AF;
    font-size: 13px;
    margin-bottom: 0.8rem;
}

.country-points {
    font-size: 34px;
    font-weight: 900;
    margin-bottom: 0.35rem;
}

.country-meta {
    color: #D1D5DB;
    font-size: 13px;
    line-height: 1.6;
}

.live-pill {
    display: inline-block;
    padding: 0.15rem 0.45rem;
    border-radius: 999px;
    background: rgba(34,197,94,0.15);
    color: #86EFAC;
    font-size: 12px;
    font-weight: 700;
    margin-left: 0.35rem;
}

.dead-pill {
    display: inline-block;
    padding: 0.15rem 0.45rem;
    border-radius: 999px;
    background: rgba(156,163,175,0.12);
    color: #D1D5DB;
    font-size: 12px;
    font-weight: 700;
    margin-left: 0.35rem;
}

.section-note {
    color: #9CA3AF;
    margin-bottom: 1rem;
}

div[data-testid="stDataFrame"] {
    border-radius: 16px;
    overflow: hidden;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="hero">
    <h1>The 561 Torta Pounder World Cup Draft ⚽️</h1>
    <p>Live fantasy standings powered by football-data.org.</p>
</div>
""",
    unsafe_allow_html=True,
)

token = get_secret_token()

try:
    draft = pd.read_csv("draft_teams.csv")
except FileNotFoundError:
    st.error("draft_teams.csv was not found. Make sure it is uploaded to the GitHub repo root.")
    st.stop()

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

tabs = st.tabs(["🏆 Standings", "🌎 Teams", "📋 Match Log", "📖 Rules"])

with tabs[0]:
    st.subheader("League Standings")

    if owner_table.empty:
        st.info("No standings yet.")
    else:
        ranked = owner_table.sort_values(["total_points", "match_points"], ascending=False).reset_index(drop=True)

        for idx, row in ranked.iterrows():
            rank = idx + 1
            medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"

            st.markdown(
                f"""
<div class="league-row">
    <div>
        <div class="rank-label">{medal}</div>
        <div class="owner-name">{row["owner"]}</div>
        <div class="small-muted">Record: {row["record"]} • Match Pts: {int(row["match_points"])} • Bonus: {int(row["advancement_bonus"])}</div>
    </div>
    <div class="total-points">{int(row["total_points"])} pts</div>
</div>
""",
                unsafe_allow_html=True,
            )

        with st.expander("Detailed Standings Table"):
            display = pretty_owner_table(owner_table)
            wanted_cols = ["Owner", "Total", "Match Pts", "Bonus", "Record", "Live"]
            display = display[[c for c in wanted_cols if c in display.columns]]
            st.dataframe(display, use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("Team Cards")
    st.markdown('<div class="section-note">Filter by owner to view each drafted country as a card.</div>', unsafe_allow_html=True)

    owners = sorted(team_table["owner"].dropna().unique())
    selected_owner = st.selectbox("Select an owner", ["All Owners"] + owners)

    filtered = team_table.copy()

    if selected_owner != "All Owners":
        filtered = filtered[filtered["owner"] == selected_owner]

    filtered = filtered.sort_values(["owner", "total_points", "match_points"], ascending=[True, False, False])

    card_cols = st.columns(3)

    for i, (_, row) in enumerate(filtered.iterrows()):
        live_badge = '<span class="live-pill">LIVE</span>' if int(row["live_games"]) > 0 else '<span class="dead-pill">IDLE</span>'

        with card_cols[i % 3]:
            st.markdown(
                f"""
<div class="country-card">
    <div class="country-name">{team_label(row["team"])} {live_badge}</div>
    <div class="country-owner">Owned by {row["owner"]}</div>
    <div class="country-points">{int(row["total_points"])} pts</div>
    <div class="country-meta">
        Record: {row["record"]}<br>
        Match Points: {int(row["match_points"])}<br>
        Advancement Bonus: {int(row["advancement_bonus"])}
    </div>
</div>
""",
                unsafe_allow_html=True,
            )

    with st.expander("Detailed Team Table"):
        display = pretty_team_table(filtered)
        wanted_cols = ["Owner", "Country", "Total", "Match Pts", "Bonus", "Record", "Live"]
        display = display[[c for c in wanted_cols if c in display.columns]]
        st.dataframe(display, use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("Match Log")

    if match_log.empty:
        st.info("No match log yet.")
    else:
        display = match_log.sort_values(["date", "team"]).copy()

        if "status" in display.columns:
            display["status"] = display["status"].replace(
                {
                    "FINISHED": "✅ Finished",
                    "IN_PLAY": "🟢 Live",
                    "PAUSED": "🟡 Paused",
                    "TIMED": "⏳ Scheduled",
                    "SCHEDULED": "⏳ Scheduled",
                }
            )

        display = pretty_match_log(display)

        wanted_cols = [
            "Date",
            "Owner",
            "Country",
            "Opponent",
            "Stage",
            "Group",
            "Status",
            "Score",
            "Result",
            "Pts",
            "3+ Bonus",
            "Shutout Bonus",
        ]

        display = display[[c for c in wanted_cols if c in display.columns]]
        st.dataframe(display, use_container_width=True, hide_index=True)

with tabs[3]:
    st.subheader("Scoring Rules")

    st.markdown(
        """
### Every Match
- **3 pts**: Win
- **1 pt**: Draw
- **0 pts**: Loss
- **+1 bonus**: Win by 3+ goals
- **+1 bonus**: Shutout win

### Advancement Bonuses
- **+3**: Survive group stage
- **+5**: Win Round of 32
- **+7**: Win Quarterfinal
- **+10**: Win Semifinal
- **+15**: Win the Final
- **+25**: Win the Cup

### Shootout Rule
Shootouts count as a draw for match-result scoring, plus the applicable advancement bonus.
"""
    )
