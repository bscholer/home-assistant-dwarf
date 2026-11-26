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
from homeassistant.const import DEGREE, PERCENTAGE, EntityCategory, UnitOfInformation, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_MODE, MODE_DIRECT, MODE_RELAY
from .coordinator import Dwarf3ConfigEntry, Dwarf3Coordinator
from .entity import Dwarf3Entity

JOB_STATES = ["idle", "running", "done", "failed"]


@dataclass(frozen=True, kw_only=True)
class Dwarf3SensorDescription(SensorEntityDescription):
    value: Callable[[dict[str, Any]], Any]


# What the scope gives out without the relay. The rest needs the control connection.
DIRECT_SENSOR_KEYS = {"sd_free", "sd_used", "sd_total"}


def _job(data: dict[str, Any], key: str) -> Any:
    return (data.get("job") or {}).get(key)


def _job_state(data: dict[str, Any]) -> str | None:
    if "job" not in data:
        return None  # nothing read yet, or the scope is not answering: do not claim "idle"
    if data.get("busy_elsewhere"):
        return "running"
    state = _job(data, "state")
    return state if state in JOB_STATES else ("idle" if data.get("job") is None else None)


def _progress(data: dict[str, Any]) -> float | None:
    job = data.get("job") or {}
    if not job.get("frames") or job.get("captured") is None:
        return None
    return round(100 * job["captured"] / job["frames"], 1)


def _sd_used(data: dict[str, Any]) -> float | None:
    total, free = data.get("sd_total_gb"), data.get("sd_free_gb")
    if not total or free is None:
        return None
    return round(100 * (total - free) / total, 1)


SENSORS: tuple[Dwarf3SensorDescription, ...] = (
    Dwarf3SensorDescription(
        key="capture_progress",
        translation_key="capture_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value=_progress,
    ),
    Dwarf3SensorDescription(
        key="sd_used",
        translation_key="sd_used",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value=_sd_used,
    ),
    Dwarf3SensorDescription(
        key="sd_total",
        translation_key="sd_total",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda d: d.get("sd_total_gb"),
    ),
    Dwarf3SensorDescription(
        key="tele_darks",
        translation_key="tele_darks",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda d: d.get("tele_darks"),
    ),
    Dwarf3SensorDescription(
        key="wide_darks",
        translation_key="wide_darks",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda d: d.get("wide_darks"),
    ),
    # The goto and calibration codes are not mapped to meanings yet, so these stay off unless you want to look.
    Dwarf3SensorDescription(
        key="goto_state",
        translation_key="goto_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda d: d.get("goto_state"),
    ),
    Dwarf3SensorDescription(
        key="calibration_state",
        translation_key="calibration_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda d: d.get("calibration_state"),
    ),
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
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value=lambda d: d.get("pitch"),
    ),
    Dwarf3SensorDescription(
        key="rotation",
        translation_key="rotation",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value=lambda d: d.get("rotation"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: Dwarf3ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    if entry.data.get(CONF_MODE, MODE_RELAY) == MODE_DIRECT:
        async_add_entities(Dwarf3Sensor(coordinator, d) for d in SENSORS if d.key in DIRECT_SENSOR_KEYS)
        async_add_entities([Dwarf3DirectSessionsSensor(coordinator)])
        return
    async_add_entities(Dwarf3Sensor(coordinator, description) for description in SENSORS)
    async_add_entities([Dwarf3SessionsSensor(coordinator), Dwarf3RelayVersionSensor(coordinator)])


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


class Dwarf3SessionsSensor(Dwarf3Entity, SensorEntity):
    """How many capture sessions sit on the SD card. Read slowly, since it reads the scope's album."""

    _attr_translation_key = "sessions"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: Dwarf3Coordinator) -> None:
        super().__init__(coordinator, "sessions")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.sessions.async_add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.sessions.data
        return None if data is None else len(data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.sessions.data
        return None if data is None else {"sessions": data[-20:]}


class Dwarf3RelayVersionSensor(Dwarf3Entity, SensorEntity):
    _attr_translation_key = "relay_version"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Dwarf3Coordinator) -> None:
        super().__init__(coordinator, "relay_version")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.relay_version


class Dwarf3DirectSessionsSensor(Dwarf3Entity, SensorEntity):
    """Capture sessions on the SD card, listed over FTP every 10 minutes."""

    _attr_translation_key = "sessions"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DataUpdateCoordinator[dict[str, Any]]) -> None:
        super().__init__(coordinator, "sessions")

    @property
    def native_value(self) -> int | None:
        sessions = self.coordinator.data.get("sessions")
        return None if sessions is None else len(sessions)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        sessions = self.coordinator.data.get("sessions")
        return None if sessions is None else {"sessions": sessions[-20:]}
