import requests

RANKS = [
    "bronze-1",
    "bronze-2",
    "bronze-3",
    "silver-1",
    "silver-2",
    "silver-3",
    "gold-1",
    "gold-2",
    "gold-3",
    "platinum-1",
    "platinum-2",
    "platinum-3",
    "diamond-1",
    "diamond-2",
    "diamond-3",
    "champion-1",
    "champion-2",
    "champion-3",
    "grand-champion-1",
    "grand-champion-2",
    "grand-champion-3",
    "supersonic-legend",
]


def replay_analyzer(replay_id: str, token: str) -> requests.Response:
    return requests.get(
        f"https://rocketleague-analyzer-93acc7980de0.herokuapp.com/replay/{replay_id}",
        headers={"Authorization": token},
    )


def query_replays(query: dict, token: str) -> requests.Response:
    return requests.get(
        "https://ballchasing.com/api/replays",
        params=query,
        headers={"Authorization": token},
    )
