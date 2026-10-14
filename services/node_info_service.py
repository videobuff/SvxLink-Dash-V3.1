#!/usr/bin/env python3

"""
node_info.json renderer for SvxLink-Dash-V3.1.
"""

import json
from pathlib import Path


NODE_INFO_FILE = Path("/etc/pi3twe/svxlink/node_info.json")


def build_node_info_json(model):
    info = model.get("node_info", {})

    return {
        "nodeLocation": info.get("nodeLocation", ""),
        "hidden": False,
        "sysop": info.get("sysop", ""),
        "qth": [
            {
                "name": info.get("qth_name", ""),
                "pos": {
                    "lat": info.get("lat", ""),
                    "long": info.get("long", ""),
                    "loc": info.get("locator", ""),
                },
                "rx": {
                    "K": {
                        "name": "Rx1",
                        "freq": float(info.get("rx_freq") or 0),
                        "sqlType": "COR",
                        "ant": {
                            "comment": info.get("antenna", ""),
                            "height": info.get("antenna_height", ""),
                            "dir": info.get("antenna_direction", "Omni"),
                        },
                    }
                },
                "tx": {
                    "K": {
                        "name": "Tx1",
                        "freq": float(info.get("tx_freq") or 0),
                        "pwr": info.get("tx_power", ""),
                        "ant": {
                            "comment": info.get("antenna", ""),
                            "height": info.get("antenna_height", ""),
                            "dir": info.get("antenna_direction", "Omni"),
                            "gain": "",
                            "Antenna_type": "omni",
                        },
                    }
                },
            }
        ],
    }


def write_node_info_json(model):
    data = build_node_info_json(model)

    NODE_INFO_FILE.write_text(
        json.dumps(data, indent=4),
        encoding="utf-8",
    )

    return NODE_INFO_FILE
