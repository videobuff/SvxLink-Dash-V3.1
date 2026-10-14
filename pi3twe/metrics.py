"""Prometheus text exposition for PI3TWE controller measurements."""

from __future__ import annotations


def prometheus_metrics(state: dict[str, object]) -> str:
    sensors = state["sensors"]
    system = state["system"]
    lines = [
        "# HELP pi3twe_sensor_temperature_c Sensor temperature in degrees Celsius.",
        "# TYPE pi3twe_sensor_temperature_c gauge",
    ]
    for sensor in sensors.values():
        _append_value(
            lines,
            "pi3twe_sensor_temperature_c",
            sensor["temperature_c"],
            location=str(sensor["name"]),
        )
    lines.extend(
        (
            "# HELP pi3twe_sensor_humidity_percent Relative humidity percentage.",
            "# TYPE pi3twe_sensor_humidity_percent gauge",
        )
    )
    for sensor in sensors.values():
        _append_value(
            lines,
            "pi3twe_sensor_humidity_percent",
            sensor["humidity_percent"],
            location=str(sensor["name"]),
        )

    metric_values = (
        ("pi3twe_nuc_cpu_load_percent", system["cpu_load_percent"]),
        ("pi3twe_nuc_disk_free_percent", system["disk_free_percent"]),
        ("pi3twe_nuc_disk_free_bytes", system["disk_free_bytes"]),
        ("pi3twe_nuc_disk_total_bytes", system["disk_total_bytes"]),
        ("pi3twe_nuc_cpu_temperature_c", system["cpu_temperature_c"]),
        ("pi3twe_nuc_soc_temperature_c", system["soc_temperature_c"]),
        ("pi3twe_nuc_uptime_seconds", state["uptime_s"]),
    )
    for name, value in metric_values:
        _append_value(lines, name, value)
    for period, value in zip(("1m", "5m", "15m"), system["load_average"]):
        _append_value(lines, "pi3twe_nuc_load_average", value, period=period)
    for relay in state["relays"]:
        _append_value(
            lines,
            "pi3twe_relay_on",
            1 if relay["on"] else 0,
            relay=str(relay["id"]),
            name=str(relay["name"]),
        )
    return "\n".join(lines) + "\n"


def _append_value(
    lines: list[str], metric: str, value: object, **labels: str
) -> None:
    if value is None:
        return
    label_text = ""
    if labels:
        encoded = ",".join(
            f'{key}="{_escape_label(label)}"' for key, label in labels.items()
        )
        label_text = "{" + encoded + "}"
    lines.append(f"{metric}{label_text} {float(value):g}")


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
