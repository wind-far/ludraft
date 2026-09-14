import { config } from "./config.js";
export interface Item {
  x: number;
  y: number;
  kind: "coin" | "bomb";
}
export class Game {
  width = 640;
  height = 440;
  x = 320;
  score = 0;
  lives = config.lives;
  status: "ready" | "playing" | "over" = "ready";
  items: Item[] = [];
  elapsed = 0;
  spawnClock = 0;
  scoreClock = 0;
  start() {
    this.x = 320;
    this.score = 0;
    this.lives = config.lives;
    this.items = [];
    this.elapsed = 0;
    this.spawnClock = 0;
    this.scoreClock = 0;
    this.status = "playing";
  }
  spawn(kind: "coin" | "bomb", x = Math.random() * 600 + 20, y = 10) {
    this.items.push({ kind, x, y });
  }
  click(x: number, y: number) {
    if (this.status !== "playing" || config.mode !== "clicker") return;
    const index = this.items.findIndex(
      (i) => Math.hypot(i.x - x, i.y - y) < 26,
    );
    if (index < 0) return;
    const item = this.items.splice(index, 1)[0];
    if (item.kind === "coin") this.score += 10;
    else this.lives -= 1;
    if (this.lives <= 0) this.status = "over";
  }
  tick(dt: number, direction: number, autoSpawn = true) {
    if (this.status !== "playing") return;
    dt = Math.max(0, Math.min(dt, 0.1));
    this.elapsed += dt;
    this.x = Math.max(
      22,
      Math.min(this.width - 22, this.x + direction * config.speed * dt),
    );
    this.spawnClock += dt * 1000;
    if (autoSpawn && this.spawnClock >= config.spawnMs) {
      this.spawnClock = 0;
      this.spawn(
        config.mode === "dodger" || Math.random() < 0.28 ? "bomb" : "coin",
        Math.random() * 590 + 25,
        config.mode === "clicker" ? Math.random() * 330 + 40 : 5,
      );
    }
    if (config.mode === "dodger") {
      this.scoreClock += dt;
      if (this.scoreClock >= 1) {
        this.score += 1;
        this.scoreClock -= 1;
      }
    }
    for (let i = this.items.length - 1; i >= 0; i--) {
      const item = this.items[i];
      if (config.mode !== "clicker") item.y += config.fallSpeed * dt;
      if (
        config.mode !== "clicker" &&
        Math.abs(item.x - this.x) < 29 &&
        Math.abs(item.y - 404) < 24
      ) {
        if (item.kind === "coin") this.score += 10;
        else this.lives -= 1;
        this.items.splice(i, 1);
      } else if (item.y > this.height + 20) this.items.splice(i, 1);
    }
    if (this.items.length > 30) this.items.shift();
    if (this.lives <= 0 || this.elapsed >= config.duration)
      this.status = "over";
  }
}
