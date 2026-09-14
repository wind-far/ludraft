"""Portable instructions and project license included with every game archive."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STARTUP='''# 独立运行导出的游戏

1. 解压整个 ZIP，保留 index.html、style.css、src/ 和 dist/ 的相对位置。
2. 在解压目录打开终端，运行 `python3 -m http.server 8000 --bind 127.0.0.1`。
3. 在浏览器访问 http://127.0.0.1:8000/ 。退出服务器时按 Ctrl+C。

已包含验证过的 dist，不需要启动游芽工作台、配置模型密钥或安装 Node.js 即可试玩。
不要直接双击 index.html；浏览器对本地文件的模块加载有限制。
如端口占用，可将命令中的 8000 改成其他空闲端口，并访问对应地址。

若要修改 TypeScript 源码，再安装 Node.js，运行 `npm install` 和 `npm run build`，然后重启静态服务器。
修改源码后的结果不沿用原 verification.json 的通过结论，需要重新验证。

操作方式见游戏中的提示。手机触屏支持以 verification.json 的 mobile 记录为准；旧快照可能只有桌面验证。
自动交互结果不代表人工可玩性评价；verification.json 保存的是导出版本的测试证据。

## 来源

本作品由游芽 Ludraft 工作台导出。工作台基于 https://github.com/LinHao-city/openclaw-multi-agent-gamedev 复刻八角色规则和协作流程；Canvas 模板、隔离验证、版本和导出闭环为本地新增实现。
许可证保存在 licenses/upstream-MIT.txt。规则及协作记录存在时另附 rules.json、collaboration.json 等文件；没有记录的角色调用不视为发生过。
'''


def write_startup_files(archive, engine=None):
    instructions = STARTUP
    if engine == 'phaser':
        instructions = instructions.replace('保留 index.html、style.css、src/ 和 dist/ 的相对位置', '保留完整源码、public/ 素材和 dist/ 构建产物')
        instructions = instructions.replace('python3 -m http.server 8000 --bind 127.0.0.1', 'python3 -m http.server 8000 --bind 127.0.0.1 --directory dist')
        instructions = instructions.replace('`npm install`', '`npm ci --ignore-scripts`')
    archive.writestr('RUN_GAME.md',instructions)
    archive.writestr('licenses/upstream-MIT.txt',(ROOT/'LICENSE').read_text())
