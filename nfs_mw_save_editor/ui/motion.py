"""Animation ticked at the screen's pace rather than at Qt's.

Qt drives every animation from one timer at 60Hz, whatever the screen is
doing.  On a 144Hz monitor that is one new position every two or three
refreshes, and anything that crosses real distance - a panel growing out of a
chip, an indicator sliding the width of a bar - moves in visible steps between
them.  `QAnimationDriver`, the supported way to raise that rate for the whole
application, is not exposed in PySide6, so the animations that need the frames
tick themselves.

Measured on the career page: Qt's driver 62fps, this 165fps, with a frame of
that page costing 4ms - the frames were there to be had all along.

Only for motion.  A fade has nothing to step between, so opacity animations
are left on Qt's timer: fewer moving parts, and nothing to gain.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QElapsedTimer,
    QObject,
    QPoint,
    QPointF,
    QTimer,
    Qt,
    Signal,
)


def spring(position: float, settle: float = 9.0, bounce: float = 0.0) -> float:
    """A critically damped spring, as a position between 0 and 1.

    Apple drives this kind of transition with a spring rather than a curve,
    and the difference is at the two ends.  A spring leaves ITS REST with no
    velocity and builds, where an ease-out leaves at its fastest - over the
    distance from a chip to a panel that first jump is tens of pixels in a
    frame, which reads as being thrown rather than opening.  And it settles
    asymptotically instead of arriving on a deadline.

    Closed form for the zero-velocity case, `1 - (1 + wt)e^-wt`, normalised so
    the run is home when its time is up.  `settle` is how many time constants
    fit in the run: 9 leaves a thousandth of the distance on the table, which
    is under a pixel of anything we move.

    A spring has no duration of its own, so the caller still says how long -
    what changes is the shape, not the schedule.
    """
    if position <= 0.0:
        return 0.0
    if position >= 1.0:
        return 1.0
    if bounce <= 0.0:
        reach = lambda t: 1.0 - (1.0 + settle * t) * math.exp(-settle * t)  # noqa: E731
        return reach(position) / reach(1.0)

    # Under-damped: it goes past and comes back.  Apple's `bounce` is one minus
    # the damping ratio, and the first overshoot is exp(-pi*z / sqrt(1-z^2)) -
    # 1.5% at bounce 0.2, 13% at 0.45.  Small numbers: over the few per cent of
    # scale a recoil is worth, anything gentler cannot be seen at all.
    damping = max(0.05, min(0.95, 1.0 - bounce))
    ringing = settle * math.sqrt(1.0 - damping * damping)
    def reach(t: float) -> float:
        decay = math.exp(-damping * settle * t)
        return 1.0 - decay * (
            math.cos(ringing * t) + (damping * settle / ringing) * math.sin(ringing * t)
        )
    return reach(position) / reach(1.0)


class PacedAnimation(QObject):
    """A stand-in for `QVariantAnimation` and `QPropertyAnimation`.

    Built to be swapped in by name: `PacedAnimation(self)` animates a value
    and emits it, `PacedAnimation(target, b"property", parent)` writes it to a
    Qt property, and both take the same duration, curve and start/end values
    as the class they replace.

    Progress is read off a clock rather than counted in ticks, so a frame that
    took too long lands where it belongs instead of stretching the run into
    slow motion.
    """

    valueChanged = Signal(object)   # noqa: N815 - Qt spelling, so it swaps in
    finished = Signal()

    # One tick per refresh of a 144Hz screen, with a little room to spare.
    _INTERVAL_MS = 6

    def __init__(
        self,
        target: Optional[QObject] = None,
        prop: bytes = b"",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent if prop else target)
        self._target = target if prop else None
        self._prop = prop.decode() if prop else ""
        self._span = 0
        self._start: Any = 0.0
        self._end: Any = 1.0
        self._value: Any = 0.0
        self._curve = QEasingCurve(QEasingCurve.Linear)
        self._clock = QElapsedTimer()
        self._ticker = QTimer(self)
        self._ticker.setTimerType(Qt.PreciseTimer)
        self._ticker.setInterval(self._INTERVAL_MS)
        self._ticker.timeout.connect(self._tick)

    # ── the surface the Qt classes offer ──────────────────────────────
    def duration(self) -> int:
        return self._span

    def setDuration(self, span_ms: int) -> None:  # noqa: N802 - Qt spelling
        self._span = max(0, round(span_ms))

    def setEasingCurve(self, curve) -> None:  # noqa: N802 - Qt spelling
        self._curve = curve if isinstance(curve, QEasingCurve) else QEasingCurve(curve)

    def easingCurve(self) -> QEasingCurve:  # noqa: N802 - Qt spelling
        return self._curve

    def setStartValue(self, value: Any) -> None:  # noqa: N802 - Qt spelling
        self._start = value

    def setEndValue(self, value: Any) -> None:  # noqa: N802 - Qt spelling
        self._end = value

    def startValue(self) -> Any:  # noqa: N802 - Qt spelling
        return self._start

    def endValue(self) -> Any:  # noqa: N802 - Qt spelling
        return self._end

    def currentValue(self) -> Any:  # noqa: N802 - Qt spelling
        return self._value

    def isRunning(self) -> bool:  # noqa: N802 - Qt spelling
        return self._ticker.isActive()

    def state(self) -> QAbstractAnimation.State:
        """Qt's own enum, because callers ask `state() != Running` and a
        stand-in that answers in a dialect of its own is not a stand-in."""
        if self._ticker.isActive():
            return QAbstractAnimation.Running
        return QAbstractAnimation.Stopped

    def start(self) -> None:
        if self._span <= 0:
            self._land()
            return
        self._clock.restart()
        self._ticker.start()
        self._apply(0.0)

    def stop(self) -> None:
        """Stop where it stands, silently - as Qt does, without `finished`."""
        self._ticker.stop()

    def setCurrentTime(self, done_ms: int) -> None:  # noqa: N802 - Qt spelling
        """Put the run at ``done_ms`` at once, without waiting on the clock."""
        if self._span <= 0 or done_ms >= self._span:
            self._land()
            return
        self._apply(max(0.0, done_ms / self._span))

    # ── the ticking itself ────────────────────────────────────────────
    def _tick(self) -> None:
        done = self._clock.elapsed()
        if done >= self._span:
            self._land()
            return
        self._apply(done / self._span)

    def _land(self) -> None:
        self._ticker.stop()
        self._apply(1.0)
        self.finished.emit()

    def _apply(self, position: float) -> None:
        self._value = self._between(self._start, self._end, self._curve.valueForProgress(position))
        if self._target is not None and self._prop:
            self._target.setProperty(self._prop, self._value)
        self.valueChanged.emit(self._value)

    @staticmethod
    def _between(start: Any, end: Any, eased: float) -> Any:
        """Only the kinds that travel: a number, or a point on the screen."""
        if isinstance(start, QPoint):
            return QPoint(
                round(start.x() + (end.x() - start.x()) * eased),
                round(start.y() + (end.y() - start.y()) * eased),
            )
        if isinstance(start, QPointF):
            return QPointF(
                start.x() + (end.x() - start.x()) * eased,
                start.y() + (end.y() - start.y()) * eased,
            )
        return start + (end - start) * eased
