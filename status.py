"""Create Builders server status -> Discord voice channel name.

Pings the Minecraft server the same way the multiplayer menu does, then renames a
locked Discord voice channel to show the result. Runs every ~10 minutes on GitHub
Actions (see .github/workflows/status.yml), so it keeps working when the server PC
itself is off.

Environment:
  DISCORD_TOKEN  bot token (GitHub secret). Without it the script only prints.
  CHANNEL_ID     the voice channel to rename.
  MC_ADDRESS     server address, default molecule-hall.tun.ply.gg
"""
import json
import os
import sys
import urllib.error
import urllib.request

from mcstatus import JavaServer

ADDRESS = os.environ.get("MC_ADDRESS") or "molecule-hall.tun.ply.gg"
CHANNEL_ID = os.environ.get("CHANNEL_ID") or ""
TOKEN = os.environ.get("DISCORD_TOKEN") or ""
API = "https://discord.com/api/v10"


def check_server():
    """Return (online, players_online, players_max). Two tries so one dropped packet isn't 'offline'."""
    last_error = None
    for _ in range(2):
        try:
            status = JavaServer.lookup(ADDRESS, timeout=8).status()
            return True, status.players.online, status.players.max
        except Exception as error:  # timeout, refused, DNS failure, bad handshake
            last_error = error
    print(f"Server check failed: {last_error!r}")
    return False, 0, 0


def channel_name(online, players, max_players):
    if online:
        return f"🟢 Online · {players}/{max_players} players"
    return "🔴 Server Offline"


def discord(method, path, body=None):
    request = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bot {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (create-builders-status, 1.0)",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read() or b"{}")


def main():
    online, players, max_players = check_server()
    wanted = channel_name(online, players, max_players)
    print(f"{ADDRESS}: {wanted}")

    if not TOKEN or not CHANNEL_ID:
        print("No DISCORD_TOKEN/CHANNEL_ID set: dry run, channel not changed.")
        return 0

    try:
        current = discord("GET", f"/channels/{CHANNEL_ID}").get("name")
        if current == wanted:
            print("Channel name already correct, nothing to do.")
            return 0
        discord("PATCH", f"/channels/{CHANNEL_ID}", {"name": wanted})
        print(f"Renamed channel: {current!r} -> {wanted!r}")
    except urllib.error.HTTPError as error:
        if error.code == 429:
            # Discord allows ~2 renames per 10 minutes; the next run will catch up.
            print("Rate limited by Discord, will retry next run.")
            return 0
        print(f"Discord API error {error.code}: {error.read()[:300]!r}")
        explain_access_problem()
        return 1
    return 0


def explain_access_problem():
    """Print which bot the token belongs to and whether it is in the server (never the token)."""
    try:
        me = discord("GET", "/users/@me")
        print(f"Token belongs to bot: {me.get('username')} (id {me.get('id')})")
        guilds = discord("GET", "/users/@me/guilds")
        names = [f"{g.get('name')} ({g.get('id')})" for g in guilds]
        print(f"That bot is in {len(guilds)} server(s): {names}")
        channel_guild = os.environ.get("GUILD_ID") or "1573992770203422741"
        if not any(g.get("id") == channel_guild for g in guilds):
            print("-> This bot is NOT in Create Builders: the token is for a different bot.")
        else:
            print("-> Bot is in Create Builders: check its permissions on the status channel.")
    except Exception as error:
        print(f"Could not identify the bot: {error!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
