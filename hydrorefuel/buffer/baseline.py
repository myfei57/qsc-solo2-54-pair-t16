"""瓶组压力基线。

目标瓶组压力随批次与检修重新标定，每次标定代际加一。基线带有效期：超过有效
期后继续按旧基线核对会被判为过期，加注顺序里必须先重新核对才能启动压缩机。
"""

from __future__ import annotations


class BufferBaseline:
    """带代际与有效期的瓶组压力基线。"""

    def __init__(self, target_mpa: float, tolerance_mpa: float, ttl_s: float) -> None:
        if target_mpa <= 0:
            raise ValueError("基线目标压力必须为正")
        self._target_mpa = float(target_mpa)
        self._tolerance_mpa = float(tolerance_mpa)
        self._ttl_s = float(ttl_s)
        self._epoch = 0
        self._stamped_at = 0.0

    @property
    def target_mpa(self) -> float:
        return self._target_mpa

    @property
    def tolerance_mpa(self) -> float:
        return self._tolerance_mpa

    @property
    def epoch(self) -> int:
        """返回基线代际，重新标定一次加一。"""

        return self._epoch

    def calibrate(self, now: float, target_mpa: float) -> float:
        """按当前时刻重新标定基线，返回新的目标压力。"""

        if target_mpa <= 0:
            raise ValueError("标定值必须为正")
        self._target_mpa = float(target_mpa)
        self._stamped_at = float(now)
        self._epoch += 1
        return self._target_mpa

    def age_s(self, now: float) -> float:
        """返回基线自标定以来经过的秒数。"""

        return max(0.0, float(now) - self._stamped_at)

    def expired(self, now: float) -> bool:
        """基线是否已经超过有效期。"""

        return self.age_s(now) > self._ttl_s

    def check(self, pressure_mpa: float, now: float) -> dict:
        """按当前时刻核对瓶组压力。"""

        pressure = float(pressure_mpa)
        deviation = pressure - self._target_mpa
        expired = self.expired(now)
        return {
            "target_mpa": round(self._target_mpa, 3),
            "pressure_mpa": round(pressure, 3),
            "deviation_mpa": round(deviation, 3),
            "tolerance_mpa": round(self._tolerance_mpa, 3),
            "epoch": self._epoch,
            "age_s": round(self.age_s(now), 2),
            "expired": expired,
            "within_band": abs(deviation) <= self._tolerance_mpa,
            # 核对放行的判据是"基线未过期且瓶组未越过目标带上限"，
            # 未装满属于正常工况，不拦压缩机启动。
            "ok": (not expired) and deviation <= self._tolerance_mpa,
        }
