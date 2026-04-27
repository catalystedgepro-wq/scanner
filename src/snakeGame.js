import { createInitialState, stepState } from "./snakeLogic.js";

const TICK_MS = 140;
const GRID_SIZE = 16;

const app = document.querySelector("#app");

app.innerHTML = `
  <main class="snake-app">
    <h1>Snake</h1>
    <div class="status-row">
      <span>Score: <strong id="score">0</strong></span>
      <span id="state-label">Running</span>
    </div>
    <div id="grid" class="grid" aria-label="Snake game board" role="application"></div>
    <div class="actions">
      <button id="pause-btn" type="button">Pause</button>
      <button id="restart-btn" type="button">Restart</button>
    </div>
    <div class="controls" aria-label="On-screen controls">
      <button data-dir="up" type="button">Up</button>
      <button data-dir="left" type="button">Left</button>
      <button data-dir="down" type="button">Down</button>
      <button data-dir="right" type="button">Right</button>
    </div>
    <p class="help">Use arrow keys or WASD. Press Space to pause/resume.</p>
  </main>
`;

const gridEl = document.querySelector("#grid");
const scoreEl = document.querySelector("#score");
const stateLabelEl = document.querySelector("#state-label");
const pauseBtn = document.querySelector("#pause-btn");
const restartBtn = document.querySelector("#restart-btn");
const controlsEl = document.querySelector(".controls");

let state = createInitialState({ gridSize: GRID_SIZE });
let pendingDirection = null;
let paused = false;
let tickHandle = null;

function render() {
  scoreEl.textContent = String(state.score);

  if (state.isGameOver) {
    stateLabelEl.textContent = "Game Over";
  } else if (paused) {
    stateLabelEl.textContent = "Paused";
  } else {
    stateLabelEl.textContent = "Running";
  }

  const snakeSet = new Set(state.snake.map((segment) => `${segment.x},${segment.y}`));
  const headKey = `${state.snake[0].x},${state.snake[0].y}`;
  let html = "";

  for (let y = 0; y < state.gridSize; y += 1) {
    for (let x = 0; x < state.gridSize; x += 1) {
      const key = `${x},${y}`;
      let className = "cell";
      if (state.food && state.food.x === x && state.food.y === y) {
        className += " food";
      } else if (snakeSet.has(key)) {
        className += key === headKey ? " snake head" : " snake";
      }
      html += `<div class="${className}"></div>`;
    }
  }

  gridEl.innerHTML = html;
}

function tick() {
  if (paused || state.isGameOver) {
    return;
  }
  state = stepState(state, pendingDirection);
  pendingDirection = null;
  render();
}

function restart() {
  state = createInitialState({ gridSize: GRID_SIZE });
  pendingDirection = null;
  paused = false;
  pauseBtn.textContent = "Pause";
  render();
}

function setRequestedDirection(direction) {
  pendingDirection = direction;
}

function togglePause() {
  if (state.isGameOver) {
    return;
  }
  paused = !paused;
  pauseBtn.textContent = paused ? "Resume" : "Pause";
  render();
}

document.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();

  if (key === "arrowup" || key === "w") setRequestedDirection("up");
  if (key === "arrowdown" || key === "s") setRequestedDirection("down");
  if (key === "arrowleft" || key === "a") setRequestedDirection("left");
  if (key === "arrowright" || key === "d") setRequestedDirection("right");

  if (key === " " || key === "p") {
    event.preventDefault();
    togglePause();
  }

  if (key === "enter" && state.isGameOver) {
    restart();
  }
});

pauseBtn.addEventListener("click", togglePause);
restartBtn.addEventListener("click", restart);
controlsEl.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLButtonElement)) {
    return;
  }
  const dir = target.dataset.dir;
  if (dir) {
    setRequestedDirection(dir);
  }
});

render();
tickHandle = setInterval(tick, TICK_MS);

window.addEventListener("beforeunload", () => {
  if (tickHandle) {
    clearInterval(tickHandle);
  }
});
