import test from "node:test";
import assert from "node:assert/strict";

import {
  createInitialState,
  spawnFood,
  stepState
} from "../src/snakeLogic.js";

test("moves one step in current direction", () => {
  const state = {
    gridSize: 8,
    snake: [
      { x: 3, y: 3 },
      { x: 2, y: 3 },
      { x: 1, y: 3 }
    ],
    direction: "right",
    food: { x: 6, y: 6 },
    score: 0,
    isGameOver: false
  };

  const next = stepState(state);
  assert.deepEqual(next.snake, [
    { x: 4, y: 3 },
    { x: 3, y: 3 },
    { x: 2, y: 3 }
  ]);
  assert.equal(next.score, 0);
});

test("ignores immediate reverse direction input", () => {
  const state = {
    gridSize: 8,
    snake: [
      { x: 3, y: 3 },
      { x: 2, y: 3 },
      { x: 1, y: 3 }
    ],
    direction: "right",
    food: { x: 0, y: 0 },
    score: 0,
    isGameOver: false
  };

  const next = stepState(state, "left");
  assert.equal(next.direction, "right");
  assert.equal(next.snake[0].x, 4);
});

test("grows and increments score when food is eaten", () => {
  const state = {
    gridSize: 8,
    snake: [
      { x: 3, y: 3 },
      { x: 2, y: 3 },
      { x: 1, y: 3 }
    ],
    direction: "right",
    food: { x: 4, y: 3 },
    score: 0,
    isGameOver: false
  };

  const next = stepState(state, null, () => 0);
  assert.equal(next.score, 1);
  assert.equal(next.snake.length, 4);
  assert.ok(next.food);
});

test("ends game on wall collision", () => {
  const state = {
    gridSize: 5,
    snake: [
      { x: 4, y: 2 },
      { x: 3, y: 2 },
      { x: 2, y: 2 }
    ],
    direction: "right",
    food: { x: 0, y: 0 },
    score: 0,
    isGameOver: false
  };

  const next = stepState(state);
  assert.equal(next.isGameOver, true);
});

test("ends game on self collision", () => {
  const state = {
    gridSize: 7,
    snake: [
      { x: 3, y: 3 },
      { x: 3, y: 4 },
      { x: 2, y: 4 },
      { x: 2, y: 3 }
    ],
    direction: "left",
    food: { x: 6, y: 6 },
    score: 0,
    isGameOver: false
  };

  const next = stepState(state, "down");
  assert.equal(next.isGameOver, true);
});

test("spawnFood returns only unoccupied cells", () => {
  const snake = [
    { x: 0, y: 0 },
    { x: 1, y: 0 },
    { x: 0, y: 1 }
  ];
  const food = spawnFood(snake, 2, () => 0.9);
  assert.deepEqual(food, { x: 1, y: 1 });
});

test("initial state is valid", () => {
  const state = createInitialState({ gridSize: 10, randomFn: () => 0 });
  assert.equal(state.snake.length, 3);
  assert.equal(state.score, 0);
  assert.equal(state.isGameOver, false);
  assert.ok(state.food);
});
