"""平台配置。

配置来自 JSON 文件（标准库解析），覆盖槽车卸氢压力与放散确认阈值、压缩机
入口与目标压力、瓶组压力带与基线有效期、预冷目标温度、流量阶梯公差、加注
枪落座行程、泄漏阀值与加注队列容量。任何缺失或越界取值都在装配阶段抛出
:class:`ConfigError`，不允许带着半份配置启动控制链。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping

from .errors import ConfigError

_MISSING = object()


def _section(mapping: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = mapping.get(key)
    if value is None:
        raise ConfigError(f"配置缺少段落 {key!r}", component="config")
    if not isinstance(value, Mapping):
        raise ConfigError(f"配置段落 {key!r} 必须是映射", component="config")
    return value


def _number(section: Mapping[str, Any], key: str, *, minimum: float | None = None) -> float:
    value = section.get(key, _MISSING)
    if value is _MISSING:
        raise ConfigError(f"配置缺少字段 {key!r}", component="config")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"配置字段 {key!r} 必须是数值", component="config")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ConfigError(f"配置字段 {key!r} 不得小于 {minimum}", component="config")
    return number


def _integer(section: Mapping[str, Any], key: str, *, minimum: int = 0) -> int:
    value = section.get(key, _MISSING)
    if value is _MISSING:
        raise ConfigError(f"配置缺少字段 {key!r}", component="config")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"配置字段 {key!r} 必须是整数", component="config")
    if value < minimum:
        raise ConfigError(f"配置字段 {key!r} 不得小于 {minimum}", component="config")
    return value


@dataclass(frozen=True)
class TruckLimits:
    """槽车卸氢压力与放散确认约束。"""

    hose_pressure_max_mpa: float
    vent_confirm_mpa: float
    vent_timeout_s: float
    unload_rate_kg_per_min: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "TruckLimits":
        limits = cls(
            hose_pressure_max_mpa=_number(section, "hose_pressure_max_mpa", minimum=1.0),
            vent_confirm_mpa=_number(section, "vent_confirm_mpa", minimum=0.0),
            vent_timeout_s=_number(section, "vent_timeout_s", minimum=1.0),
            unload_rate_kg_per_min=_number(section, "unload_rate_kg_per_min", minimum=0.1),
        )
        if limits.vent_confirm_mpa >= limits.hose_pressure_max_mpa:
            raise ConfigError("放散确认压力必须小于软管最高压力", component="config")
        return limits

    def discharge_ready(self, pressure_mpa: float) -> bool:
        """软管压力是否已降到可以拔管的水平。"""

        return pressure_mpa <= self.vent_confirm_mpa


@dataclass(frozen=True)
class VentLimits:
    """放散阀孔径与闩锁约束。"""

    orifice_mm: float
    rate_coeff: float
    ambient_mpa: float
    latch_travel_mm: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "VentLimits":
        limits = cls(
            orifice_mm=_number(section, "orifice_mm", minimum=0.5),
            rate_coeff=_number(section, "rate_coeff", minimum=0.1),
            ambient_mpa=_number(section, "ambient_mpa", minimum=0.0),
            latch_travel_mm=_number(section, "latch_travel_mm", minimum=1.0),
        )
        if limits.rate_coeff > 1.0:
            raise ConfigError("放散系数不得超过 1.0", component="config")
        return limits

    def vent_rate_mpa_per_s(self, pressure_mpa: float) -> float:
        """按孔口流量估算的压降速率，压力越低放散越慢。"""

        overpressure = max(0.0, pressure_mpa - self.ambient_mpa)
        return self.rate_coeff * self.orifice_mm * overpressure / 100.0


@dataclass(frozen=True)
class CompressorLimits:
    """压缩机入口、目标压力与喘振约束。"""

    inlet_min_mpa: float
    outlet_target_mpa: float
    ramp_mpa_per_s: float
    surge_band_mpa: float
    min_flow_kg_per_min: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "CompressorLimits":
        limits = cls(
            inlet_min_mpa=_number(section, "inlet_min_mpa", minimum=0.0),
            outlet_target_mpa=_number(section, "outlet_target_mpa", minimum=1.0),
            ramp_mpa_per_s=_number(section, "ramp_mpa_per_s", minimum=0.05),
            surge_band_mpa=_number(section, "surge_band_mpa", minimum=0.1),
            min_flow_kg_per_min=_number(section, "min_flow_kg_per_min", minimum=0.1),
        )
        if limits.outlet_target_mpa <= limits.inlet_min_mpa:
            raise ConfigError("压缩机目标压力必须高于入口最低压力", component="config")
        return limits


@dataclass(frozen=True)
class BufferLimits:
    """储氢瓶组压力带与基线有效期。"""

    target_pressure_mpa: float
    pressure_tolerance_mpa: float
    baseline_ttl_s: float
    capacity_kg: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "BufferLimits":
        limits = cls(
            target_pressure_mpa=_number(section, "target_pressure_mpa", minimum=1.0),
            pressure_tolerance_mpa=_number(section, "pressure_tolerance_mpa", minimum=0.1),
            baseline_ttl_s=_number(section, "baseline_ttl_s", minimum=1.0),
            capacity_kg=_number(section, "capacity_kg", minimum=1.0),
        )
        if limits.pressure_tolerance_mpa >= limits.target_pressure_mpa:
            raise ConfigError("瓶组压力公差必须小于目标压力", component="config")
        return limits

    def within(self, pressure_mpa: float) -> bool:
        """压力是否落在目标带内。"""

        return abs(pressure_mpa - self.target_pressure_mpa) <= self.pressure_tolerance_mpa


@dataclass(frozen=True)
class CoolLimits:
    """预冷目标温度与保持时长约束。"""

    target_temp_c: float
    temp_band_c: float
    cool_rate_c_per_s: float
    precool_hold_s: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "CoolLimits":
        limits = cls(
            target_temp_c=_number(section, "target_temp_c"),
            temp_band_c=_number(section, "temp_band_c", minimum=0.5),
            cool_rate_c_per_s=_number(section, "cool_rate_c_per_s", minimum=0.05),
            precool_hold_s=_number(section, "precool_hold_s", minimum=1.0),
        )
        if limits.target_temp_c >= 0.0:
            raise ConfigError("预冷目标温度必须低于 0 度", component="config")
        return limits

    def reached(self, temperature_c: float) -> bool:
        """温度是否已落到加注允许带。"""

        return abs(temperature_c - self.target_temp_c) <= self.temp_band_c


@dataclass(frozen=True)
class FlowLimits:
    """质量流量阶梯与速率约束。"""

    step_target_kg: float
    step_tolerance_kg: float
    max_rate_kg_per_min: float
    min_rate_kg_per_min: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "FlowLimits":
        limits = cls(
            step_target_kg=_number(section, "step_target_kg", minimum=0.1),
            step_tolerance_kg=_number(section, "step_tolerance_kg", minimum=0.01),
            max_rate_kg_per_min=_number(section, "max_rate_kg_per_min", minimum=0.1),
            min_rate_kg_per_min=_number(section, "min_rate_kg_per_min", minimum=0.01),
        )
        if not limits.min_rate_kg_per_min < limits.max_rate_kg_per_min:
            raise ConfigError("流量下限必须小于上限", component="config")
        if limits.step_tolerance_kg >= limits.step_target_kg:
            raise ConfigError("阶梯公差必须小于阶梯目标", component="config")
        return limits

    def within_step(self, mass_kg: float) -> bool:
        """本阶梯累计质量是否落在公差内。"""

        return abs(mass_kg - self.step_target_kg) <= self.step_tolerance_kg


@dataclass(frozen=True)
class DispenserLimits:
    """加注机枪位、落座与隔离约束。"""

    nozzle_seat_travel_mm: float
    seat_timeout_s: float
    max_line_pressure_mpa: float
    isolate_lead_s: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "DispenserLimits":
        limits = cls(
            nozzle_seat_travel_mm=_number(section, "nozzle_seat_travel_mm", minimum=1.0),
            seat_timeout_s=_number(section, "seat_timeout_s", minimum=1.0),
            max_line_pressure_mpa=_number(section, "max_line_pressure_mpa", minimum=1.0),
            isolate_lead_s=_number(section, "isolate_lead_s", minimum=0.0),
        )
        if limits.isolate_lead_s >= limits.seat_timeout_s:
            raise ConfigError("隔离提前量必须小于落座超时", component="config")
        return limits


@dataclass(frozen=True)
class LeakLimits:
    """泄漏阀值与闩锁保持约束。"""

    threshold_ppm: float
    sample_window_s: float
    hold_s: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "LeakLimits":
        limits = cls(
            threshold_ppm=_number(section, "threshold_ppm", minimum=1.0),
            sample_window_s=_number(section, "sample_window_s", minimum=0.1),
            hold_s=_number(section, "hold_s", minimum=1.0),
        )
        if limits.hold_s <= limits.sample_window_s:
            raise ConfigError("泄漏闩锁保持时长必须大于采样窗口", component="config")
        return limits

    def tripped(self, concentration_ppm: float) -> bool:
        """浓度是否达到泄漏阀值。"""

        return concentration_ppm >= self.threshold_ppm


@dataclass(frozen=True)
class QueueLimits:
    """加注队列容量与确认超时约束。"""

    max_waiting: int
    confirm_timeout_s: float

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "QueueLimits":
        return cls(
            max_waiting=_integer(section, "max_waiting", minimum=1),
            confirm_timeout_s=_number(section, "confirm_timeout_s", minimum=1.0),
        )


@dataclass(frozen=True)
class StationConfig:
    """一份完整的平台配置。"""

    name: str
    storage_root: str
    truck: TruckLimits
    vent: VentLimits
    compressor: CompressorLimits
    buffer: BufferLimits
    cool: CoolLimits
    flow: FlowLimits
    dispenser: DispenserLimits
    leak: LeakLimits
    queue: QueueLimits

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "StationConfig":
        meta = _section(mapping, "station")
        name = meta.get("name")
        storage_root = meta.get("storage_root")
        if not isinstance(name, str) or not name:
            raise ConfigError("station.name 必须是非空字符串", component="config")
        if not isinstance(storage_root, str) or not storage_root:
            raise ConfigError("station.storage_root 必须是非空字符串", component="config")

        limits = _section(mapping, "limits")
        return cls(
            name=name,
            storage_root=storage_root,
            truck=TruckLimits.from_mapping(_section(limits, "truck")),
            vent=VentLimits.from_mapping(_section(limits, "vent")),
            compressor=CompressorLimits.from_mapping(_section(limits, "comp")),
            buffer=BufferLimits.from_mapping(_section(limits, "buffer")),
            cool=CoolLimits.from_mapping(_section(limits, "cool")),
            flow=FlowLimits.from_mapping(_section(limits, "flow")),
            dispenser=DispenserLimits.from_mapping(_section(limits, "disp")),
            leak=LeakLimits.from_mapping(_section(limits, "leak")),
            queue=QueueLimits.from_mapping(_section(limits, "queue")),
        )


def load_config(path: str) -> StationConfig:
    """从 JSON 文件读取配置。"""

    if not os.path.isfile(path):
        raise ConfigError(f"配置文件不存在: {path}", component="config")
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, Mapping):
        raise ConfigError("配置文件顶层必须是映射", component="config")
    return StationConfig.from_mapping(raw)


def default_config() -> StationConfig:
    """内置默认配置，供未指定配置文件时装配使用。"""

    return StationConfig(
        name="refueling-control",
        storage_root="var/state",
        truck=TruckLimits(25.0, 1.5, 90.0, 6.0),
        vent=VentLimits(6.0, 0.9, 0.1, 40.0),
        compressor=CompressorLimits(3.0, 43.0, 0.8, 1.2, 1.5),
        buffer=BufferLimits(42.0, 1.5, 3600.0, 350.0),
        cool=CoolLimits(-40.0, 3.0, 0.6, 20.0),
        flow=FlowLimits(1.8, 0.15, 3.6, 0.4),
        dispenser=DispenserLimits(55.0, 15.0, 44.0, 2.0),
        leak=LeakLimits(4000.0, 5.0, 30.0),
        queue=QueueLimits(12, 45.0),
    )


def config_to_mapping(cfg: StationConfig) -> dict:
    """把配置还原成可打印的映射。"""

    return {
        "station": {"name": cfg.name, "storage_root": cfg.storage_root},
        "limits": {
            "truck": {
                "hose_pressure_max_mpa": cfg.truck.hose_pressure_max_mpa,
                "vent_confirm_mpa": cfg.truck.vent_confirm_mpa,
                "vent_timeout_s": cfg.truck.vent_timeout_s,
                "unload_rate_kg_per_min": cfg.truck.unload_rate_kg_per_min,
            },
            "vent": {
                "orifice_mm": cfg.vent.orifice_mm,
                "rate_coeff": cfg.vent.rate_coeff,
                "ambient_mpa": cfg.vent.ambient_mpa,
                "latch_travel_mm": cfg.vent.latch_travel_mm,
            },
            "comp": {
                "inlet_min_mpa": cfg.compressor.inlet_min_mpa,
                "outlet_target_mpa": cfg.compressor.outlet_target_mpa,
                "ramp_mpa_per_s": cfg.compressor.ramp_mpa_per_s,
                "surge_band_mpa": cfg.compressor.surge_band_mpa,
                "min_flow_kg_per_min": cfg.compressor.min_flow_kg_per_min,
            },
            "buffer": {
                "target_pressure_mpa": cfg.buffer.target_pressure_mpa,
                "pressure_tolerance_mpa": cfg.buffer.pressure_tolerance_mpa,
                "baseline_ttl_s": cfg.buffer.baseline_ttl_s,
                "capacity_kg": cfg.buffer.capacity_kg,
            },
            "cool": {
                "target_temp_c": cfg.cool.target_temp_c,
                "temp_band_c": cfg.cool.temp_band_c,
                "cool_rate_c_per_s": cfg.cool.cool_rate_c_per_s,
                "precool_hold_s": cfg.cool.precool_hold_s,
            },
            "flow": {
                "step_target_kg": cfg.flow.step_target_kg,
                "step_tolerance_kg": cfg.flow.step_tolerance_kg,
                "max_rate_kg_per_min": cfg.flow.max_rate_kg_per_min,
                "min_rate_kg_per_min": cfg.flow.min_rate_kg_per_min,
            },
            "disp": {
                "nozzle_seat_travel_mm": cfg.dispenser.nozzle_seat_travel_mm,
                "seat_timeout_s": cfg.dispenser.seat_timeout_s,
                "max_line_pressure_mpa": cfg.dispenser.max_line_pressure_mpa,
                "isolate_lead_s": cfg.dispenser.isolate_lead_s,
            },
            "leak": {
                "threshold_ppm": cfg.leak.threshold_ppm,
                "sample_window_s": cfg.leak.sample_window_s,
                "hold_s": cfg.leak.hold_s,
            },
            "queue": {
                "max_waiting": cfg.queue.max_waiting,
                "confirm_timeout_s": cfg.queue.confirm_timeout_s,
            },
        },
    }
