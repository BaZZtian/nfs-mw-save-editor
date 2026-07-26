import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QAbstractAnimation
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
    shell.queue_reveal(duration_ms=100, stable_checks=1)
    assert effect.isEnabled()

    deadline = time.monotonic() + 2.0
    while shell._animation_group is None:
        app.processEvents()
        assert time.monotonic() < deadline

    animation = shell._animation_group
    assert animation.state() == QAbstractAnimation.Running
    assert effect.isEnabled()

    while not finished:
        QTest.qWait(10)
        assert time.monotonic() < deadline

    assert finished == [True]
    assert shell._animation_group is None
    assert effect.opacity() == 1.0
    assert not effect.isEnabled()

    shell.play_reveal(duration_ms=100)
    assert effect.isEnabled()
    shell.clear_animation()
    assert shell.offsetY == 0
    assert effect.opacity() == 1.0
    assert not effect.isEnabled()

    shell.close()
