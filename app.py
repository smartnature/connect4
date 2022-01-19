#!/usr/bin/env python

import asyncio
import websockets
import json
from connect4 import PLAYER1, PLAYER2, Connect4
import secrets
import os
import signal
import watchdog
from inspect import currentframe, getframeinfo
import sys


JOIN = {}
WATCH = {}
DELETE_TIMERS = {}

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

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

        print(f"first player started game {join_key}")

    except Exception as e:
        frameinfo = getframeinfo(currentframe())
        eprint(f"An exception of type {type(e)} occurred: {e} \n{frameinfo.filename}, {frameinfo.lineno}")

    #finally:
        # Todo : find the right place to delete the game.
        # Do not delete it right away to get a chance to reconnect.
        #DELETE_TIMERS[join_key] = \
        #    watchdog.Watchdog(timeout = 15*60, userHandler = lambda join_key = join_key,
        #                                                watch_key = watch_key : cleanupClosedSocket(join_key, watch_key))


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

    print(f"Watching game {watch_key}")
    await replay(websocket, game)


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

    print(f"Second player joined game {join_key}")
    await replay(websocket, game)


async def handler(websocket):
    # Receive and parse the "init" event from the UI.
    try:
        async for message in websocket:
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
            elif (event["type"] == "replay"):
                print("Received replay event")
                await replayFromEvent(websocket, event)

            elif(event["type"] == "play"):
                # received play event
                print("Received play event")
                await play(websocket, event)

    except websockets.exceptions.ConnectionClosedError:
        pass
    except Exception as e:
        frameinfo = getframeinfo(currentframe())
        eprint(f"An exception of type {type(e)} occurred: {e} \n{frameinfo.filename}, {frameinfo.lineno}")


async def  replayFromEvent(websocket, event):
    join_key = event["gameId"]
    try:
        game, connected = JOIN[join_key]
    except KeyError:
        await error(websocket, "Game not found.")
        eprint(f"Event: {event}")
        eprint(f"join_key: {join_key}")
        eprint(f"JOIN: {JOIN}")
        return

    connected.add(websocket)
    await replay(websocket, game)


async def play(websocket, event):

    join_key = event["gameId"]
    player = event["player"]

    try:
        game, connected = JOIN[join_key]
    except KeyError:
        await error(websocket, "Game not found.")
        eprint(f"Event: {event}")
        eprint(f"join_key: {join_key}")
        eprint(f"JOIN: {JOIN}")
        return

    connected.add(websocket)

    await replay(websocket, game)
    await playMessage(event, game, player, connected, websocket)


async def playMessage(event, game, player, connected, websocket):
    # Parse a "play" event from the UI.
    assert event["type"] == "play"
    column = event["column"]

    try:
        # Play the move.
        row = game.play(player, column)
    except RuntimeError as exc:
        # Send an "error" event if the move was illegal.
        await error(websocket, str(exc))
        return

    # Send a "play" event to update the UI.
    event = {
        "type": "play",
        "player": player,
        "column": column,
        "row": row
    }
    print("Sending play event to update UI")
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