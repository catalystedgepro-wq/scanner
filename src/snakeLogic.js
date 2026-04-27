export const DIRECTIONS = {
  up: { x: 0, y: -1 },
  down: { x: 0, y: 1 },
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 }
};

export function isOppositeDirection(a, b) {
  return (
    (a === "up" && b === "down") ||
    (a === "down" && b === "up") ||
    (a === "left" && b === "right") ||
    (a === "right" && b === "left")
  );
}

export function positionsEqual(a, b) {
  return a.x === b.x && a.y === b.y;
}

export function isOutOfBounds(position, gridSize) {
  return (
    position.x < 0 ||
    position.y < 0 ||
    position.x >= gridSize ||
    position.y >= gridSize
  );
}

export function spawnFood(snake, gridSize, randomFn = Math.random) {
  const occupied = new Set(snake.map((segment) => `${segment.x},${segment.y}`));
  const free = [];

  for (let y = 0; y < gridSize; y += 1) {
    for (let x = 0; x < gridSize; x += 1) {
      const key = `${x},${y}`;
      if (!occupied.has(key)) {
        free.push({ x, y });
      }
    }
  }

  if (free.length === 0) {
    return null;
  }

  const index = Math.floor(randomFn() * free.length);
  return free[index];
}

function nextHead(head, direction) {
  const delta = DIRECTIONS[direction];
  return { x: head.x + delta.x, y: head.y + delta.y };
}

export function createInitialState(options = {}) {
  const gridSize = options.gridSize ?? 16;
  const randomFn = options.randomFn ?? Math.random;
  const center = Math.floor(gridSize / 2);
  const snake = [
    { x: center, y: center },
    { x: center - 1, y: center },
    { x: center - 2, y: center }
  ];

  return {
    gridSize,
    snake,
    direction: "right",
    food: spawnFood(snake, gridSize, randomFn),
    score: 0,
    isGameOver: false
  };
}

export function stepState(state, requestedDirection, randomFn = Math.random) {
  if (state.isGameOver) {
    return state;
  }

  let direction = state.direction;
  if (
    requestedDirection &&
    requestedDirection !== state.direction &&
    !isOppositeDirection(state.direction, requestedDirection)
  ) {
    direction = requestedDirection;
  }

  const newHead = nextHead(state.snake[0], direction);
  if (isOutOfBounds(newHead, state.gridSize)) {
    return { ...state, direction, isGameOver: true };
  }

  const isEating = state.food && positionsEqual(newHead, state.food);
  const bodyToCheck = isEating ? state.snake : state.snake.slice(0, -1);
  const selfCollision = bodyToCheck.some((segment) => positionsEqual(segment, newHead));

  if (selfCollision) {
    return { ...state, direction, isGameOver: true };
  }

  const newSnake = [newHead, ...state.snake];
  if (!isEating) {
    newSnake.pop();
  }

  return {
    ...state,
    direction,
    snake: newSnake,
    food: isEating ? spawnFood(newSnake, state.gridSize, randomFn) : state.food,
    score: isEating ? state.score + 1 : state.score,
    isGameOver: false
  };
}
