"""roster.py: names for the synthetic clubs and players (all fictional).

The generator uses ids (h01 to h11, a01 to a11). Viewers read names, and the verifier rejects
any number in a comment that is not a checked claim, so a comment that said "h09" would fail.
The tools add these names next to the ids.
"""
CLUBS = {"home": "Larkspur FC", "away": "Copper Vale"}
SHORT = {"home": "Larkspur", "away": "Copper Vale"}

PLAYERS = {
    "h01": "Tomas Brecht", "h02": "Jonah Okafor", "h03": "Elias Varga", "h04": "Marcus Lindqvist",
    "h05": "Dario Fenn", "h06": "Kai Moreland", "h07": "Ruben Ashe", "h08": "Theo Calloway",
    "h09": "Nico Halvorsen", "h10": "Sami Idris", "h11": "Leon Mbeki",
    "a01": "Piet Vandermeer", "a02": "Owen Strand", "a03": "Felix Arroyo", "a04": "Bram Kessler",
    "a05": "Iker Solano", "a06": "Malik Durand", "a07": "Jude Farrow", "a08": "Emil Toivo",
    "a09": "Rafa Quintero", "a10": "Ezra Holm", "a11": "Caleb Nwosu",
}


# Squad numbers. A player keeps his number in every match, whatever slot he plays.
# Larkspur keeps the traditional 1 to 11 pattern with one exception (14). Copper Vale has
# a modern spread (31 in goal, numbers in the teens, twenties and thirties), as many
# Premier League squads do. The page shows them; the narrator never writes them.
SHIRT = {
    "h01": 1, "h02": 3, "h03": 5, "h04": 4, "h05": 2, "h06": 6,
    "h07": 8, "h08": 14, "h09": 10, "h10": 9, "h11": 7,
    "a01": 31, "a02": 23, "a03": 15, "a04": 33, "a05": 22, "a06": 18,
    "a07": 24, "a08": 20, "a09": 19, "a10": 10, "a11": 11,
}

def player(pid: str | None) -> str:
    return PLAYERS.get(pid or "", pid or "")


def name_event(d: dict) -> dict:
    """Add team_name, player_name and other named players to one event dict."""
    d = dict(d)
    if d.get("team_id") in CLUBS:
        d["team_name"] = CLUBS[d["team_id"]]
    for key in ("player_id", "receiver_id", "target_player_id", "fouled_player_id"):
        if d.get(key):
            d[key.replace("_id", "_name")] = player(d[key])
    return d
