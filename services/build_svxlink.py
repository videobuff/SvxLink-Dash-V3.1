#!/usr/bin/env python3

"""
Primary build orchestration service for SvxLink-Dash-V3.1.

This module coordinates:
- model validation
- platform validation
- configuration rendering
- backup creation
- file deployment
- optional service restart

This is the authoritative build pipeline.
"""

from pathlib import Path
import subprocess
import json
from unittest import result


NODE_INFO_FILE = Path("/etc/pi3twe/svxlink/node_info.json")
from models.node_model import validate_model

from hw_platforms import (
    validate_platform_model,
)

from renderers.svxlink_renderer import (
    render_svxlink_config,
    render_echolink_module,
    render_metar_module,
    get_primary_callsign,
)

from services.svxlink_service import (
    backup_active_config,
    write_text_file,
    deploy_required_logic_files,
    apply_courtesy_tone,
    apply_repeater_event_customisations,
    apply_va_barred_cw_symbol,
    restart_svxlink,
    svxlink_status,
)

from services.svxlink_service import (
    SVXLINK_CONF,
    MODULE_DIR,
)

SOUND_BASE_DIR = Path("/usr/share/svxlink/sounds")

LANGUAGE_REPOS = {
    "en_GB": "https://github.com/f5vmr/en_GB.git",
    "en_US": "https://github.com/f5vmr/en_US.git",
    "en_AU": "https://github.com/f5vmr/en_AU.git",
}


# =========================================================
# Build result helper
# =========================================================

def build_result():
    """
    Standard structured build result.
    """

    return {
        "success": False,

        "validation_errors": [],
        "platform_errors": [],
        "deployment_errors": [],

        "rendered_files": [],
        "backups": [],
        "logic_files": [],

        "service_restarted": False,
        "service_status": "unknown",
    }


# =========================================================
# Validation
# =========================================================

def validate_build(model):
    """
    Validate complete build readiness.

    Returns:
        dict
    """

    result = build_result()

    validation_errors = validate_model(model)
    platform_errors = validate_platform_model(model)

    result["validation_errors"] = validation_errors
    result["platform_errors"] = platform_errors

    return result


# =========================================================
# Render phase
# =========================================================

def render_all(model):
    """
    Render all required configuration outputs.

    Returns:
        dict
    """

    rendered = {}

# =====================================================
# Main SvxLink configuration
# =====================================================

    rendered["svxlink.conf"] = render_svxlink_config(model)

# =====================================================
# Optional module configurations
# =====================================================

    echolink_conf = render_echolink_module(model)

    if echolink_conf:
        rendered["ModuleEchoLink.conf"] = echolink_conf

    metar_conf = render_metar_module(model)

    if metar_conf:
        rendered["ModuleMetarInfo.conf"] = metar_conf

    return rendered

# =========================================================
# Deployment phase
# =========================================================
def render_motd_script(model):
    callsign = get_primary_callsign(model)

    return f"""#!/bin/sh

uname -snrvm
TERM=linux toilet -F metal {callsign}-SVX
/usr/bin/vcgencmd measure_temp

## This file gives the login screen of a Raspberry Pi a new look
## 24062026 - 3.1
"""
def deploy_motd_script(content):
    tmp_path = Path("/tmp/10-uname")

    tmp_path.write_text(content, encoding="utf-8")

    subprocess.run(
        [
            "sudo",
            "install",
            "-o", "root",
            "-g", "root",
            "-m", "755",
            str(tmp_path),
            "/etc/update-motd.d/10-uname",
        ],
        check=True,
    )

    tmp_path.unlink(missing_ok=True)

    return "/etc/update-motd.d/10-uname"


def deploy_node_info(model):
    node_info = {
        "callsign": model.get("node", {}).get("callsign"),
        "type": model.get("node", {}).get("type"),
        "platform": model.get("platform", {}).get("name"),
        "reflector": model.get("reflector", {}).get("name"),
        "modules": model.get("modules", {}).get("enabled", []),
    }

    write_text_file(
        NODE_INFO_FILE,
        json.dumps(node_info, indent=4) + "\n",
    )

    return str(NODE_INFO_FILE)

def ensure_language_pack(model):
    language = (
        model.get("language", {}).get("default")
        or model.get("node", {}).get("language")
        or "en_GB"
    )

    target_dir = SOUND_BASE_DIR / language
    if target_dir.exists():
        return str(target_dir)

    repo_url = LANGUAGE_REPOS.get(language)
    if not repo_url:
        raise RuntimeError(f"No repository configured for language {language}; install the language pack first")

    subprocess.run(
        [
            "sudo",
            "git",
            "clone",
            repo_url,
            str(target_dir),
        ],
        check=True,
    )

    return str(target_dir)

def deploy_rendered_files(rendered_files):
    """
    Deploy rendered configuration files.

    Returns:
        list[str]
    """

    deployed = []



# =====================================================
# Main svxlink.conf
# =====================================================

    if "svxlink.conf" in rendered_files:

        write_text_file(
            SVXLINK_CONF,
            rendered_files["svxlink.conf"]
        )

        deployed.append(str(SVXLINK_CONF))

    # =====================================================
    # Optional module configuration files
    # =====================================================

    for filename in (
        "ModuleEchoLink.conf",
        "ModuleMetarInfo.conf",
    ):

        if filename not in rendered_files:
            continue

        target = MODULE_DIR / filename

        write_text_file(
            target,
            rendered_files[filename]
        )

        deployed.append(str(target))

    return deployed

# =========================================================
# Full build pipeline
# =========================================================

def build_svxlink_configuration(
    model,
    restart=False,
):
    """
    Execute full configuration build pipeline.

    Steps:
        1. Validate model
        2. Validate platform
        3. Render config
        4. Backup active config
        5. Deploy config
        6. Deploy logic files
        7. Restart service optionally

    Returns:
        dict
    """

    result = build_result()

    # =====================================================
    # Validation
    # =====================================================

    validation = validate_build(model)

    result["validation_errors"] = validation["validation_errors"]
    result["platform_errors"] = validation["platform_errors"]

    if (
        result["validation_errors"]
        or
        result["platform_errors"]
    ):
        result["service_status"] = svxlink_status()
        return result

    # =====================================================
    # Render
    # =====================================================

    try:
        rendered = render_all(model)

    except Exception as exc:

        result["deployment_errors"].append(
            f"Render failed: {exc}"
        )

        result["service_status"] = svxlink_status()
        return result

    # =====================================================
    # Backup
    # =====================================================

    try:
        backups = backup_active_config()
        result["backups"] = [str(x) for x in backups]

    except Exception as exc:

        result["deployment_errors"].append(
            f"Backup failed: {exc}"
        )

        result["service_status"] = svxlink_status()
        return result

    # =====================================================
    # Deploy config
    # =====================================================

    try:
        deployed = deploy_rendered_files(rendered)

        result["rendered_files"] = deployed
        # Do not replace the host's login banner as part of a radio config build.
        result["rendered_files"] = deployed
        
        node_info_path = deploy_node_info(model)
        result["rendered_files"].append(node_info_path)
        language_path = ensure_language_pack(model)
        result["rendered_files"].append(language_path)
    except Exception as exc:

        result["deployment_errors"].append(
            f"Configuration deployment failed: {exc}"
        )

        result["service_status"] = svxlink_status()
        return result

    # =====================================================
    # Deploy logic overrides
    # =====================================================
    event_model = model

    hardware = model.get("hardware", {})
    enabled_ports = model.get("ports", {}).get("enabled", [])
    nodes = model.get("nodes", {})

    if hardware.get("family") == "ics" and enabled_ports:
        port_id = str(enabled_ports[0])
        node = nodes.get(port_id, {})

        event_model = model.copy()
        event_model["courtesy"] = node.get("courtesy", {})
        event_model["repeater"] = node.get("repeater", {})
        event_model["cw"] = node.get("cw", model.get("cw", {}))
    try:
        logic_files = deploy_required_logic_files()
        va_cw = apply_va_barred_cw_symbol()
        logic_files.append(va_cw)
        courtesy_logic = apply_courtesy_tone(event_model)
        logic_files.append(courtesy_logic)
        if event_model.get("node", {}).get("type") == "repeater":
            repeater_logic = apply_repeater_event_customisations(event_model)
            logic_files.append(repeater_logic)
        result["logic_files"] = [
            str(x) for x in logic_files
        ]

    except Exception as exc:

        result["deployment_errors"].append(
            f"Logic deployment failed: {exc}"
        )

        result["service_status"] = svxlink_status()
        return result

    # =====================================================
    # Restart service
    # =====================================================

    if restart:

        try:
            restart_svxlink()
            result["service_restarted"] = True

        except Exception as exc:

            result["deployment_errors"].append(
                f"SvxLink restart failed: {exc}"
            )

    # =====================================================
    # Final status
    # =====================================================

    result["service_status"] = svxlink_status()

    if not result["deployment_errors"]:
        result["success"] = True

    return result
