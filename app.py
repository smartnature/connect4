#!/usr/bin/env python

import asyncio
import websockets
import json
from connect4 import PLAYER1, PLAYER2, Connect4
import secrets
import os
import signal
import watchdog


JOIN = {}
WATCH = {}
DELETE_TIMERS = {}

async def start(websocket):
    # Initialize a Connect Four game, the set of WebSocket connections
    # receiving moves from this game, and secret access token.
    game = Connect4()
    connected = {websocket}

    print("Started")

    join_key = secrets.token_urlsafe(12)
    watch_key = secrets.token_urlsafe(12)

    JOIN[join_key] = game, connected
    WATCH[watch_key] = game, connected

    print (f"JOIN: {JOIN}")

    try:
        # Send the secret access token to the browser of the first player,
        # where it'll be used for building a "join" link.
        event = {
            "type": "init",
            "join": join_key,
            "watch": watch_key
        }
        await websocket.send(json.dumps(event))

        print("first player started game", id(game))
        await play(websocket, game, PLAYER1, connected)

    except Exception as e:
        print(f"An exception occurred: {e}")

    finally:
        print (f"Setting timer to delete JOIN[join_key], where join_key value is {join_key}")
        # Do not delete it right away to get a chance to reconnect.
        DELETE_TIMERS[join_key] = \
            watchdog.Watchdog(timeout = 15*60, userHandler = lambda join_key = join_key,
                                                        watch_key = watch_key : cleanupClosedSocket(join_key, watch_key))


def cleanupClosedSocket(join_key, watch_key):
    print (f"Deleting JOIN[join_key], where join_key value is {join_key}")
    del WATCH[watch_key]
    del JOIN[join_key]
    del DELETE_TIMERS[join_key]



async def replay(websocket, game):
    for player, column, row in game.moves.copy():
        event = {
            "type": "play",
            "player": player,
            "column": column,
            "row": row
        }
        await websocket.send(json.dumps(event))


async def error(websocket, message):
    event = {
        "type": "error",
        "message": message,
    }
    await websocket.send(json.dumps(event))


async def watch(websocket, watch_key):
    # Find the Connect Four game.
    try:
        print(f"Trying to watch with {watch_key}")
        game, connected = WATCH[watch_key]
    except KeyError:
        await error(websocket, "Game not found.")
        return

    # Register to receive moves from this game.
    connected.add(websocket)
    try:
        print("Watching game", id(game))
        await replay(websocket, game)
        await websocket.wait_closed()

    finally:
        connected.remove(websocket)


async def join(websocket, join_key):
    # Find the Connect Four game.
    try:
        print(f"Trying to join with {join_key}")
        print(f"JOIN content: {JOIN}")
        game, connected = JOIN[join_key]
    except KeyError:
        await error(websocket, "Game not found.")
        return

    # Register to receive moves from this game.
    connected.add(websocket)
    try:
        print("second player joined game", id(game))
        await replay(websocket, game)
        await play(websocket, game, PLAYER2, connected)

    finally:
        connected.remove(websocket)


async def handler(websocket):
    # Receive and parse the "init" event from the UI.
    message = await websocket.recv()
    event = json.loads(message)
    if(event["type"] == "init"):
        if "join" in event:
            # Second player joins an existing game.
            await join(websocket, event["join"])
        elif "watch" in event:
            await watch(websocket, event["watch"])
        else:
            # First player starts a new game.
            await start(websocket)
    elif(event["type"] == "play"):
        # received play event instead of init. This happens when websocket disconnects during a game
        reconnectPlay(websocket, event)


async def reconnectPlay(websocket, event):
    join_key = event["gameId"]
    player = event["player"]
    game, connected = JOIN[join_key]
    print(f"{player} reconnected to the game", id(game))
    await replay(websocket, game)
    await play(websocket, game, player, connected)


async def play(websocket, game, player, connected):

    print("Play function started")

    async for message in websocket:
        # Parse a "play" event from the UI.
        event = json.loads(message)
        assert event["type"] == "play"
        column = event["column"]

        try:
            # Play the move.
            row = game.play(player, column)
        except RuntimeError as exc:
            # Send an "error" event if the move was illegal.
            await error(websocket, str(exc))
            continue

        # Send a "play" event to update the UI.
        event = {
            "type": "play",
            "player": player,
            "column": column,
            "row": row
        }
        websockets.broadcast(connected, json.dumps(event))

        # If move is winning, send a "win" event.
        if game.winner is not None:
            event = {
                "type": "win",
                "player": game.winner
            }
            websockets.broadcast(connected, json.dumps(event))


async def main():
    if 'ON_HEROKU' in os.environ:
        # Set the stop condition when receiving SIGTERM.
        loop = asyncio.get_running_loop()
        stop = loop.create_future()
        loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

        port = int(os.environ.get("PORT", "8001"))
        async with websockets.serve(handler, "", port):
            await stop
    else:
        async with websockets.serve(handler, "", 8001):
            await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())