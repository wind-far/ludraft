import { config } from "./config.js";
import { Game } from "./game.js";
const game = new Game();
const canvas = document.querySelector<HTMLCanvasElement>("#game")!;
const ctx = canvas.getContext("2d")!;
const start = document.querySelector<HTMLButtonElement>("#start")!;
const score = document.querySelector("#score")!,
  lives = document.querySelector("#lives")!,
  remaining = document.querySelector("#remaining")!,
  status = document.querySelector("#status")!;
document.querySelector("#title")!.textContent = config.title;
document.title = config.title;
document.querySelector("#instructions")!.textContent =
  config.mode === "clicker"
    ? "点击星光得分，避开红色危险目标"
    : config.mode === "dodger"
      ? "按住画布左右拖动，或用 ← → / A D 移动 · 躲开陨石，生存计分"
      : "按住画布左右拖动，或用 ← → / A D 移动 · 收集星光，躲开陨石";
const keys = new Set<string>();
let pointer: number | null = null;
let targetX: number | null = null;
function resetInput() {
  keys.clear();
  targetX = null;
  if (pointer !== null && canvas.hasPointerCapture(pointer)) canvas.releasePointerCapture(pointer);
  pointer = null;
}
addEventListener("keydown", (e) => {
  const key = e.key.toLowerCase();
  if (["arrowleft", "arrowright", "a", "d"].includes(key)) {
    e.preventDefault();
    keys.add(key);
  }
});
addEventListener("keyup", (e) => keys.delete(e.key.toLowerCase()));
addEventListener("blur", resetInput);
document.addEventListener("visibilitychange", () => { if (document.hidden) resetInput(); });
start.onclick = () => {
  resetInput();
  game.start();
  canvas.focus({ preventScroll: true });
};
function position(e: PointerEvent) {
  const r = canvas.getBoundingClientRect();
  return { x: ((e.clientX - r.left) * 640) / r.width, y: ((e.clientY - r.top) * 440) / r.height };
}
canvas.onpointerdown = (e) => {
  if (game.status !== "playing" || pointer !== null || !e.isPrimary || e.button !== 0) return;
  e.preventDefault();
  pointer = e.pointerId;
  canvas.setPointerCapture(pointer);
  canvas.focus({ preventScroll: true });
  if (config.mode !== "clicker") targetX = position(e).x;
};
canvas.onpointermove = (e) => {
  if (e.pointerId === pointer && config.mode !== "clicker") targetX = position(e).x;
};
canvas.onpointerup = (e) => {
  if (e.pointerId !== pointer) return;
  const p = position(e);
  if (config.mode === "clicker" && p.x >= 0 && p.x <= 640 && p.y >= 0 && p.y <= 440) game.click(p.x, p.y);
  resetInput();
};
canvas.onpointercancel = e => { if (e.pointerId === pointer) resetInput(); };
canvas.onlostpointercapture = e => { if (e.pointerId === pointer) resetInput(); };
const testing = new URLSearchParams(location.search).has("test");
if (testing) Object.assign(window, { __game: game, __config: config });
let last = performance.now();
function draw(time: number) {
  const dt = Math.max(0, Math.min((time - last) / 1000, 0.1));
  const keyboard = Number(keys.has("arrowright") || keys.has("d")) - Number(keys.has("arrowleft") || keys.has("a"));
  // Clamp the fractional direction so the player reaches the finger without oscillation.
  const touch = targetX === null || dt === 0 ? 0 : Math.max(-1, Math.min(1, (targetX - game.x) / (config.speed * dt)));
  game.tick(
    dt,
    keyboard || touch,
    !testing,
  );
  last = time;
  ctx.fillStyle = config.background;
  ctx.fillRect(0, 0, 640, 440);
  ctx.fillStyle = "#ffffff16";
  for (let i = 0; i < 45; i++)
    ctx.fillRect((i * 131) % 640, (i * 79) % 430, 2, 2);
  if (config.mode !== "clicker") {
    ctx.fillStyle = config.playerColor;
    ctx.beginPath();
    ctx.roundRect(game.x - 23, 390, 46, 24, 8);
    ctx.fill();
  }
  for (const item of game.items) {
    ctx.fillStyle =
      item.kind === "coin" ? config.targetColor : config.hazardColor;
    ctx.beginPath();
    ctx.arc(item.x, item.y, item.kind === "coin" ? 12 : 15, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#10192b";
    ctx.font = "bold 16px system-ui";
    ctx.textAlign = "center";
    ctx.fillText(item.kind === "coin" ? "✦" : "×", item.x, item.y + 6);
  }
  if (game.status !== "playing") {
    ctx.fillStyle = "#10192bcc";
    ctx.fillRect(0, 160, 640, 110);
    ctx.textAlign = "center";
    ctx.fillStyle = "#f6f7ff";
    ctx.font = "bold 25px system-ui";
    ctx.fillText(
      game.status === "over"
        ? "本局结束 · 得分 " + game.score
        : "准备收集你的第一束星光",
      320,
      215,
    );
  }
  score.textContent = String(game.score);
  lives.textContent = String(Math.max(0, game.lives));
  remaining.textContent = String(Math.max(0, Math.ceil(config.duration - game.elapsed)));
  start.textContent = game.status === "ready" ? "开始游戏" : "重新开始";
  status.textContent =
    game.status === "playing"
      ? "进行中"
      : game.status === "over"
        ? "游戏结束"
        : "准备开始";
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);
