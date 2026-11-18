"""Scope sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Dwarf3ConfigEntry, Dwarf3Coordinator
from .entity import Dwarf3Entity

JOB_STATES = ["idle", "running", "done", "failed"]


@dataclass(frozen=True, kw_only=True)
class Dwarf3SensorDescription(SensorEntityDescription):
    value: Callable[[dict[str, Any]], Any]


def _job(data: dict[str, Any], key: str) -> Any:
    return (data.get("job") or {}).get(key)


def _job_state(data: dict[str, Any]) -> str | None:
    if data.get("busy_elsewhere"):
        return "running"
    state = _job(data, "state")
    return state if state in JOB_STATES else ("idle" if data.get("job") is None else None)


SENSORS: tuple[Dwarf3SensorDescription, ...] = (
    Dwarf3SensorDescription(
        key="job_state",
        translation_key="job_state",
        device_class=SensorDeviceClass.ENUM,
        options=JOB_STATES,
        value=_job_state,
    ),
    Dwarf3SensorDescription(
        key="frames_captured",
        translation_key="frames_captured",
        state_class=SensorStateClass.TOTAL,
        value=lambda d: _job(d, "captured"),
    ),
    Dwarf3SensorDescription(
        key="frames_failed",
        translation_key="frames_failed",
        state_class=SensorStateClass.TOTAL,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda d: _job(d, "failed"),
    ),
    Dwarf3SensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d.get("battery_percent"),
    ),
    Dwarf3SensorDescription(
        key="device_temperature",
        translation_key="device_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d.get("device_temperature_c"),
    ),
    Dwarf3SensorDescription(
        key="tele_sensor_temperature",
        translation_key="tele_sensor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda d: d.get("tele_sensor_temperature_c"),
    ),
    Dwarf3SensorDescription(
        key="wide_sensor_temperature",
        translation_key="wide_sensor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda d: d.get("wide_sensor_temperature_c"),
    ),
    Dwarf3SensorDescription(
        key="sd_free",
        translation_key="sd_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value=lambda d: d.get("sd_free_gb"),
    ),
    Dwarf3SensorDescription(
        key="pitch",
        translation_key="pitch",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda d: d.get("pitch"),
    ),
    Dwarf3SensorDescription(
        key="rotation",
        translation_key="rotation",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda d: d.get("rotation"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: Dwarf3ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(Dwarf3Sensor(coordinator, description) for description in SENSORS)


class Dwarf3Sensor(Dwarf3Entity, SensorEntity):
    entity_description: Dwarf3SensorDescription

    def __init__(self, coordinator: Dwarf3Coordinator, description: Dwarf3SensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "job_state":
            return None
        job = self.coordinator.data.get("job") or {}
        return {k: job[k] for k in ("frames", "captured", "failed", "session", "error") if job.get(k) is not None}
