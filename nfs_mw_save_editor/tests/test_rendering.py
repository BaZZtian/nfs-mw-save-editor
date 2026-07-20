import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from ui.rendering import AnimatedCardShell


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_animated_card_shell_disables_opacity_effect_between_reveals() -> None:
    app = _app()
    shell = AnimatedCardShell()
    content = QWidget()
    content.setMinimumSize(240, 120)
    shell.set_content(content)
    shell.resize(240, 120)
    shell.show()
    app.processEvents()

    effect = shell.graphicsEffect()
    assert effect is not None
    assert not effect.isEnabled()

    finished = []
    shell.revealFinished.connect(lambda: finished.append(True))
    shell.queue_reveal(duration_ms=1, stable_checks=1)
    assert effect.isEnabled()

    QTest.qWait(30)
    app.processEvents()
    assert finished == [True]
    assert effect.opacity() == 1.0
    assert not effect.isEnabled()

    shell.play_reveal(duration_ms=100)
    assert effect.isEnabled()
    shell.clear_animation()
    assert shell.offsetY == 0
    assert effect.opacity() == 1.0
    assert not effect.isEnabled()

    shell.close()
