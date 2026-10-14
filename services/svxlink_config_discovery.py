#!/usr/bin/env python3

import configparser
import os
import re
from typing import Any, Dict, List


DEFAULT_SVXLINK_CONFIG = "/etc/pi3twe/svxlink/svxlink.conf"

def read_svxlink_config(config_file: str = DEFAULT_SVXLINK_CONFIG) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(
        interpolation=None,
        strict=False,
        delimiters=("=",),
        comment_prefixes=("#", ";"),
        inline_comment_prefixes=None,
    )

    parser.optionxform = str

    if not os.path.exists(config_file):
        raise FileNotFoundError(f"SvxLink config file not found: {config_file}")

    parser.read(config_file)

    return parser


def section_to_dict(parser: configparser.ConfigParser, section: str) -> Dict[str, str]:
    return {key: value for key, value in parser.items(section)}


def is_rx_section(section: str) -> bool:
    """
    Return True only for real numbered receiver sections:
    Rx1, Rx2, Rx3, etc.

    This deliberately excludes things that merely start with Rx.
    """
    return re.fullmatch(r"Rx\d+", section.strip(), re.IGNORECASE) is not None


def is_tx_section(section: str) -> bool:
    """
    Return True only for real numbered transmitter sections:
    Tx1, Tx2, Tx3, etc.

    This deliberately excludes TxStream, TxUDP, MultiTx, etc.
    """
    return re.fullmatch(r"Tx\d+", section.strip(), re.IGNORECASE) is not None


def discover_audio_sections(config_file: str = DEFAULT_SVXLINK_CONFIG) -> Dict[str, Any]:
    parser = read_svxlink_config(config_file)

    rx_sections: List[Dict[str, Any]] = []
    tx_sections: List[Dict[str, Any]] = []

    for section in parser.sections():
        values = section_to_dict(parser, section)

        item = {
            "section": section,
            "TYPE": values.get("TYPE", ""),
            "AUDIO_DEV": values.get("AUDIO_DEV", ""),
            "AUDIO_CHANNEL": values.get("AUDIO_CHANNEL", ""),
            "CARD_SAMPLE_RATE": values.get("CARD_SAMPLE_RATE", ""),
            "PTT_TYPE": values.get("PTT_TYPE", ""),
            "SQL_DET": values.get("SQL_DET", ""),
            "raw": values,
        }

        if is_rx_section(section):
            rx_sections.append(item)

        elif is_tx_section(section):
            tx_sections.append(item)

    return {
        "config_file": config_file,
        "rx_sections": rx_sections,
        "tx_sections": tx_sections,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(discover_audio_sections(), indent=2))

