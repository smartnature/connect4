import { createBoard, playMove } from "./connect4.js";

let gameId = "";
let player = "";
var websocket;
var board;

window.addEventListener("DOMContentLoaded", () => {
  // Initialize the UI.
  board = document.querySelector(".board");
  createBoard(board);
  registerVisibilityChange();

  // Open the WebSocket connection and register event handlers.
  websocket = new WebSocket(getWebSocketServer());
  initGame();
  receiveMoves();
  sendMoves();
});

var hidden, visibilityChange;
if (typeof document.hidden !== "undefined") { // Opera 12.10 and Firefox 18 and later support
  hidden = "hidden";
  visibilityChange = "visibilitychange";
} else if (typeof document.msHidden !== "undefined") {
  hidden = "msHidden";
  visibilityChange = "msvisibilitychange";
} else if (typeof document.webkitHidden !== "undefined") {
  hidden = "webkitHidden";
  visibilityChange = "webkitvisibilitychange";
}



function registerVisibilityChange() {
    console.log("registering visibility change")
    document.addEventListener(visibilityChange, handleVisibilityChange, false);
}


function handleVisibilityChange() {
  if (document[hidden]) {
    websocket.close()
  } else {
    console.log("reconnecting")
    websocket = new WebSocket(getWebSocketServer());
    receiveMoves();
  }
}


function initGame() {
  websocket.addEventListener("open", () => {
    // Send an "init" event according to who is connecting.
    const params = new URLSearchParams(window.location.search);
    let event = { type: "init" };
    if (params.has("join")) {
      // Second player joins an existing game.
      event.join = params.get("join");
      document.querySelector(".join").href = "?join=" + params.get("join");
      gameId = params.get("join");
      player = "yellow"
    } else if (params.has("watch")) {
      event.watch = params.get("watch");
    } else {
      // First player starts a new game.
    }
    websocket.send(JSON.stringify(event));
  });
}


function sendMoves() {
  // When clicking a column, send a "play" event for a move in that column.
  board.addEventListener("click", ({ target }) => {
    const column = target.dataset.column;
    // Ignore clicks outside a column.
    if (column === undefined) {
      return;
    }
    const event = {
      type: "play",
      column: parseInt(column, 10),
      gameId: gameId,
      player: player
    };
    websocket.send(JSON.stringify(event));
  });
}

function showMessage(message) {
  window.setTimeout(() => window.alert(message), 50);
}

function receiveMoves() {
  websocket.addEventListener("message", ({ data }) => {
    const event = JSON.parse(data);
    switch (event.type) {
      case "init":
        // Create link for inviting the second player.
        document.querySelector(".join").href = "?join=" + event.join;
        document.querySelector(".watch").href = "?watch=" + event.watch;
        gameId = event.join;
        player = "red";
        break;
      case "play":
        // Update the UI with the move.
        playMove(board, event.player, event.column, event.row);
        break;
      case "win":
        showMessage(`Player ${event.player} wins!`);
        // No further messages are expected; close the WebSocket connection.
        websocket.close(1000);
        break;
      case "error":
        showMessage(event.message);
        break;
      default:
        console.log("Error: Unsupported event type");
        throw new Error(`Unsupported event type: ${event.type}.`);
    }
  });
  if(gameId != ""){
      const event = {
          type: "replay",
          gameId: gameId
        };
         waitForSocketConnection(websocket, function(){
            websocket.send(JSON.stringify(event));
        });
  }

}

// Make the function wait until the connection is made...
function waitForSocketConnection(socket, callback){
    setTimeout(
        function () {
            if (socket.readyState === 1) {
                console.log("Connection is made")
                if (callback != null){
                    callback();
                }
            } else {
                console.log("wait for connection...")
                waitForSocketConnection(socket, callback);
            }

        }, 5); // wait 5 milisecond for the connection...
}


function getWebSocketServer() {
  if (window.location.host === "smartnature.github.io") {
    return "wss://websocket-tutorial-smartine.herokuapp.com/";
  } else if (window.location.host === "localhost:8000") {
    return "ws://localhost:8001/";
  } else {
    throw new Error(`Unsupported host: ${window.location.host}`);
  }
}
