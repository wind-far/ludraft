# 宝石花园 · 三消模板

人工编写的 TypeScript + Canvas 三消基线，不是模型生成成果。8×8 棋盘、相邻交换、无效交换回退、不消耗步数、三连及多连消除、下落补位、连锁加分、死局重排、目标分数与步数、胜负和重开。支持鼠标、触摸滑动和键盘。

导出包含 dist 时，在解压目录运行 `python3 -m http.server 8000 --bind 127.0.0.1` 并访问 http://127.0.0.1:8000/ 即可试玩，不依赖工作台或模型密钥。不要直接双击 HTML。

修改源码后运行 `npm install`、`npm run build` 再通过静态 HTTP 服务打开根目录。模型仅可修改 src/game.ts、src/config.ts、style.css；main.ts 与 HTML 由工作台固定。
