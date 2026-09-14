import { spawnSync } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { verifyMatch3 } from "./match3-verify.mjs";
import { verifyMobile } from "./mobile-verify.mjs";
import { chromium } from "playwright";
const root = "/workspace";
const evidence = {
  passed: false,
  build: false,
  checks: [],
  console_errors: [],
  started_at: new Date().toISOString(),
};
let browser, server;
function check(name, ok) {
  evidence.checks.push({ name, passed: !!ok });
  if (!ok) throw new Error("检查失败: " + name);
}
try {
  const built = spawnSync(
    "/opt/runner/node_modules/.bin/tsc",
    ["-p", root + "/tsconfig.json"],
    { timeout: 45000, encoding: "utf8", maxBuffer: 1024 * 1024 },
  );
  evidence.build = built.status === 0;
  evidence.build_log = (built.stdout || "") + (built.stderr || "");
  check("TypeScript 构建", evidence.build);
  server = http.createServer((req, res) => {
    const requested = decodeURIComponent(
      new URL(req.url, "http://localhost").pathname,
    );
    const file = path.resolve(
      root,
      "." + (requested === "/" ? "/index.html" : requested),
    );
    if (
      !file.startsWith(root + "/") ||
      !fs.existsSync(file) ||
      !fs.statSync(file).isFile()
    ) {
      res.writeHead(404);
      res.end();
      return;
    }
    res.setHeader(
      "Content-Type",
      file.endsWith(".js")
        ? "text/javascript"
        : file.endsWith(".css")
          ? "text/css"
          : "text/html",
    );
    fs.createReadStream(file).pipe(res);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const page = await browser.newPage();
  page.setDefaultTimeout(5000);
  page.on("pageerror", (e) => {
    if (evidence.console_errors.length < 100)
      evidence.console_errors.push(e.message);
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/?test=1`);
  await page.waitForFunction(() => window.__game && window.__config);
  const config = await page.evaluate(() => window.__config);
  evidence.config = config;
  const canvasV2=fs.readFileSync(root+'/index.html','utf8').includes('<meta name="ludraft-runtime" content="canvas-input-v2" />');
  evidence.runtime=canvasV2?'canvas-input-v2':config.mode==='match3'?'match3-v1':'canvas-v1';
  if(config.mode==='match3'){
    await verifyMatch3(page,config,check);
  } else {
  check(
    "参数边界",
    config.speed > 0 &&
      config.speed <= 1500 &&
      Number.isInteger(config.lives) &&
      config.lives >= 1 &&
      config.lives <= 10 &&
      config.duration >= 5 &&
      config.duration <= 600 &&
      config.spawnMs >= 100 &&
      config.spawnMs <= 10000 &&
      config.fallSpeed > 0 &&
      config.fallSpeed <= 1000 &&
      ["collector", "dodger", "clicker"].includes(config.mode),
  );
  await page.locator("#start").click();
  check(
    "开始游戏",
    await page.evaluate(() => window.__game.status === "playing"),
  );
  const before = await page.evaluate(() => window.__game.x);
  await page.keyboard.down("ArrowRight");
  await page.waitForTimeout(160);
  await page.keyboard.up("ArrowRight");
  check("键盘移动", await page.evaluate((x) => window.__game.x > x, before));
  const previous = await page.evaluate(() => window.__game.score);
  if (config.mode === "clicker") {
    await page.evaluate(() => window.__game.spawn("coin", 180, 150));
    const bounds = await page.locator("canvas").boundingBox();
    await page.mouse.click(
      bounds.x + (180 * bounds.width) / 640,
      bounds.y + (150 * bounds.height) / 440,
    );
  } else if (config.mode === "collector") {
    await page.evaluate(() => {
      window.__game.spawn("coin", window.__game.x, 404);
      window.__game.tick(0, 0, false);
    });
  } else {
    await page.waitForTimeout(1100);
  }
  await page.waitForTimeout(60);
  check(
    "真实得分及界面更新",
    await page.evaluate(
      (p) =>
        window.__game.score > p &&
        Number(document.querySelector("#score").textContent) ===
          window.__game.score,
      previous,
    ),
  );
  const initialLives = await page.evaluate(() => window.__game.lives);
  if (config.mode === "clicker") {
    await page.evaluate(() => window.__game.spawn("bomb", 180, 150));
    const bounds = await page.locator("canvas").boundingBox();
    await page.mouse.click(
      bounds.x + (180 * bounds.width) / 640,
      bounds.y + (150 * bounds.height) / 440,
    );
  } else {
    await page.evaluate(() => {
      window.__game.spawn("bomb", window.__game.x, 404);
      window.__game.tick(0, 0, false);
    });
  }
  check(
    "危险目标扣命",
    await page.evaluate((n) => window.__game.lives === n - 1, initialLives),
  );
  await page.evaluate(() => {
    const g = window.__game;
    for (let i = 0; i < 12 && g.status === "playing"; i++) {
      g.spawn("bomb", g.x, 404);
      if (window.__config.mode === "clicker") g.click(g.x, 404);
      else g.tick(0, 0, false);
    }
  });
  check("游戏结束", await page.evaluate(() => window.__game.status === "over"));
  await page.locator("#start").click();
  check(
    "重新开始",
    await page.evaluate(
      () =>
        window.__game.status === "playing" &&
        window.__game.score === 0 &&
        window.__game.lives === window.__config.lives,
    ),
  );
  }
  await verifyMobile(browser,`http://127.0.0.1:${server.address().port}/?test=1`,config,check,evidence,canvasV2);
  check("无浏览器异常", evidence.console_errors.length === 0);
  evidence.passed = true;
} catch (e) {
  evidence.error = String(e.message || e);
} finally {
  if (browser) await browser.close();
  if (server) server.close();
  evidence.finished_at = new Date().toISOString();
  fs.writeFileSync(root + "/evidence.json", JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify(evidence));
  process.exit(evidence.passed ? 0 : 1);
}
