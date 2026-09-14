# 林间守卫 · 固定塔防工程

内部接入验证模板，尚未开放模型创作。复用 OpenGame 的 core 与 tower_defense 基类；原始路径和摘要见 licenses/OpenGame-source.json，许可见 licenses/OpenGame-Apache-2.0.txt。

本地改动：固定依赖和相对构建路径；注册 Level1Scene；补齐 Preloader 的 Phaser 导入；标题中文化；HUD 贴图使用本地 URL 避免 iframe 画布跨源转换；加入原创几何占位素材及两种塔的固定关卡。

运行构建产物：python3 -m http.server 8000 --bind 127.0.0.1 --directory dist
源码重建：npm ci --ignore-scripts && npm run build。首次需下载依赖。

点击开始，选择塔后点击地图可建造空地，点击已有塔升级，空格提前开始下一波，ESC 暂停。

占位 PNG 素材为本项目程序绘制，沿用本项目 MIT 许可，无第三方品牌或模型生成素材。没有通过专用玩法验收前不得将此模板标为正式支持。
