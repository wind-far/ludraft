"""Trusted template capabilities; generated files cannot widen this policy."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'templates'
LEGACY_EDITABLE = frozenset({'src/config.ts', 'src/game.ts', 'style.css'})


@dataclass(frozen=True)
class Template:
    id: str
    version: str
    engine: str
    mode: str
    source: Path
    validator: str
    status: str

    def editable(self, path: str):
        if self.engine == 'canvas':
            return path in LEGACY_EDITABLE
        return path in ('src/config.ts', 'src/gameConfig.json', 'style.css') or (
            path.startswith(('src/scenes/', 'src/entities/')) and path.endswith('.ts')
            and not Path(path).name.startswith(('Base', '_Template'))
            and path not in ('src/scenes/Preloader.ts', 'src/scenes/TitleScreen.ts',
                             'src/scenes/UIScene.ts', 'src/scenes/PauseUIScene.ts',
                             'src/scenes/VictoryUIScene.ts', 'src/scenes/GameOverUIScene.ts',
                             'src/scenes/GameCompleteUIScene.ts'))


TEMPLATES = {
    **{f'canvas-{mode}': Template(f'canvas-{mode}', '1', 'canvas', mode,
        ROOT / ('match3' if mode == 'match3' else 'canvas'),
        'match3' if mode == 'match3' else 'canvas', 'available')
       for mode in ('collector', 'dodger', 'clicker', 'match3')},
    **{f'phaser-{mode}': Template(f'phaser-{mode}', '1', 'phaser', mode,
        ROOT / 'phaser' / mode, mode, 'planned')
       for mode in ('tower_defense', 'platformer', 'top_down', 'grid_logic', 'ui_heavy')},
}


def get_template(template_id, version):
    result = TEMPLATES.get(template_id)
    if result is None or result.version != version:
        raise ValueError('模板或模板版本尚未注册')
    return result


def public_templates():
    return [{'id': t.id, 'version': t.version, 'engine': t.engine, 'mode': t.mode,
             'validator': t.validator, 'status': t.status}
            for t in TEMPLATES.values()]
