#!/usr/bin/env python3

from platform import node
from pyexpat import model

from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from pathlib import Path
import shutil
import datetime 
from datetime import timedelta
from werkzeug.security import generate_password_hash, check_password_hash
                                                                                       
from services.sound_discovery import (
    discover_sound_cards,
    discover_default_audio_dev,
    apply_safe_baseline,
    set_slider_control,
)
from services.ident_audio_service import save_ident_upload
from services.svxlink_config_discovery import (
    DEFAULT_SVXLINK_CONFIG,
    discover_audio_sections,
)

from services.sound_calibration import (
    get_svxlink_service_state,
    stop_svxlink_for_calibration,
    restart_svxlink_after_calibration,
    start_devcal_session,
    stop_devcal_session,
    get_devcal_output,
    devcal_is_running,
    get_devcal_mode,
    get_devcal_tx_state,
    toggle_devcal_tx,
)

from services.hardware_profile_service import (
    list_hardware_profiles,
    load_hardware_profile,
)
from services.model_store import (
    load_node_model,
    save_node_model,
    CTCSS_TONES,
)
from services.build_svxlink import build_svxlink_configuration

from services.model_store import (
    load_node_model,
    save_node_model,
)

## Wifi
from services.wifi_service import (
    wifi_scan,
    connection_list,
    wifi_status,
    wifi_on,
    connect_wifi,
    switch_wifi,
    delete_wifi,
    hotspot_status,
    start_hotspot,
    stop_hotspot,
)

from services.talkgroup_service import load_talkgroups, save_talkgroups
from services.dtmf_service import send_dtmf
from services.status_service import get_runtime_status
from services.activity_service import get_reflector_activity
from services.hardware_service import get_system_info
from services.ics_prepare_service import (
    build_ics_status,
    configure_pcm1803,
    configure_audio_boot,
    get_ics_profiles,
    set_overlay,
    enable_i2c,
)
from services.log_service import get_svxlink_log_path
from services.gpio_service import (
    flatten_gpio_lines,
    prepare_gpio_lines,
    update_model_gpiod_discovery,
)
from services.node_info_service import write_node_info_json
from renderers.svxlink_renderer import (
    render_echolink_module,
)
from services.version_service import get_version_info
from services.svxlink_service import (
    MODULE_DIR,
    write_text_file,
    restart_svxlink,
)
import subprocess
import hw_platforms
from services.system_service import (
    restart_services,
    reboot_device,
    shutdown_device,
    schedule_reboot,
)
from data.metar_airports import METAR_REGIONS
from data.timezones import TIMEZONES



# =========================================================
# Core paths
# =========================================================

APP_ROOT = Path("/opt/dashboard")
TEMPLATE_DIR = APP_ROOT / "templates"
STATIC_DIR = APP_ROOT / "static"

CONFIG_DIR = APP_ROOT / "config"
MODEL_FILE = CONFIG_DIR / "node_model.json"
MODEL_BACKUP_DIR = CONFIG_DIR / "backups"
# =========================================================
# Supported CTCSS frequencies
# =========================================================
CTCSS_FREQUENCIES = [
    ("", "None / disabled"),
    ("67.0", "67.0 Hz"),
    ("69.3", "69.3 Hz"),
    ("71.9", "71.9 Hz"),
    ("74.4", "74.4 Hz"),
    ("77.0", "77.0 Hz"),
    ("79.7", "79.7 Hz"),
    ("82.5", "82.5 Hz"),
    ("85.4", "85.4 Hz"),
    ("88.5", "88.5 Hz"),
    ("91.5", "91.5 Hz"),
    ("94.8", "94.8 Hz"),
    ("97.4", "97.4 Hz"),
    ("100.0", "100.0 Hz"),
    ("103.5", "103.5 Hz"),
    ("107.2", "107.2 Hz"),
    ("110.9", "110.9 Hz"),
    ("114.8", "114.8 Hz"),
    ("118.8", "118.8 Hz"),
    ("123.0", "123.0 Hz"),
    ("127.3", "127.3 Hz"),
    ("131.8", "131.8 Hz"),
    ("136.5", "136.5 Hz"),
    ("141.3", "141.3 Hz"),
    ("146.2", "146.2 Hz"),
    ("151.4", "151.4 Hz"),
    ("156.7", "156.7 Hz"),
    ("159.8", "159.8 Hz"),
    ("162.2", "162.2 Hz"),
    ("165.5", "165.5 Hz"),
    ("167.9", "167.9 Hz"),
    ("171.3", "171.3 Hz"),
    ("173.8", "173.8 Hz"),
    ("177.3", "177.3 Hz"),
    ("179.9", "179.9 Hz"),
    ("183.5", "183.5 Hz"),
    ("186.2", "186.2 Hz"),
    ("189.9", "189.9 Hz"),
    ("192.8", "192.8 Hz"),
    ("196.6", "196.6 Hz"),
    ("199.5", "199.5 Hz"),
    ("203.5", "203.5 Hz"),
    ("206.5", "206.5 Hz"),
    ("210.7", "210.7 Hz"),
    ("218.1", "218.1 Hz"),
    ("225.7", "225.7 Hz"),
    ("229.1", "229.1 Hz"),
    ("233.6", "233.6 Hz"),
    ("241.8", "241.8 Hz"),
    ("250.3", "250.3 Hz"),
    ("254.1", "254.1 Hz"),
]

# =========================================================
# SvxLink paths
# =========================================================

SVXLINK_CONF = Path("/etc/pi3twe/svxlink/svxlink.conf")

MODULE_DIR = Path("/etc/pi3twe/svxlink/svxlink.d")


EVENT_FILES = ['Logic.tcl', 'RepeaterLogicType.tcl', 'CW.tcl']
# =========================================================
# Flask app
# =========================================================

app = Flask(
    __name__,
    template_folder=str(TEMPLATE_DIR),
    static_folder=str(STATIC_DIR),
    static_url_path="/static"
)
app.permanent_session_lifetime = timedelta(hours=8)
app.secret_key = "change-this-dashboard-secret"

app.permanent_session_lifetime = datetime.timedelta(minutes=15)

# =========================================================
# Authorisation and protection
# =========================================================
def dashboard_auth_exists():
    """
    Return True only when dashboard credentials exist and are parseable.
    Fail closed if the model cannot be read safely.
    """

    try:
        model = load_node_model()
        auth = model.get("dashboard_auth", {})

        username = auth.get("username", "").strip()
        password_hash = auth.get("password_hash", "").strip()

        return bool(username and password_hash)

    except Exception:
        return False

@app.before_request
def require_dashboard_auth():
    """
    Protect all dashboard configuration/control routes.

    Public:
      - static assets
      - /status
      - /api/status
      - /authorise
      - /logout
      - /setup-auth only when no credentials exist yet

    Everything else requires session["authorised"].
    """

    public_paths = {
        "/metrics",
        "/",
        "/status",
        "/api/status",
        "/wifi",
    }

    auth_paths = {
        "/authorise",
        "/logout",
    }

    setup_auth_path = "/setup-auth"

    if request.endpoint == "static":
        return None

    path = request.path.rstrip("/") or "/"

    if path in public_paths:
        return None

    auth_exists = dashboard_auth_exists()

    if not auth_exists:
        if path == setup_auth_path:
            return None

        session.pop("authorised", None)
        return redirect(url_for("setup_auth_page"))

    if path in auth_paths:
        return None

    if path == setup_auth_path:
        if session.get("authorised"):
            return None

        return redirect(url_for("authorise_page", next=request.path))

    if not session.get("authorised"):
        return redirect(url_for("authorise_page", next=request.path))

    return None
# ========================================================
# Context processors
# ========================================================
@app.context_processor
def inject_versions():
    return {
        "version_info": get_version_info()
    }


# =========================================================
# Platform detection
# =========================================================

def detect_platform():
    """
    Detect supported hardware profile.

    Initial supported targets:
    - raspberry_pi
    - nanopi_neo

    Anything else is unsupported unless later proven compatible.
    """

    model_text = ""

    try:
        model_text = Path("/proc/device-tree/model").read_text(errors="ignore").lower()
    except FileNotFoundError:
        pass

    if "raspberry pi" in model_text:
        return {
            "id": "raspberry_pi",
            "name": "Raspberry Pi",
            "supported": True,
        }

    if "nanopi neo" in model_text or "friendlyarm nanopi" in model_text:
        return {
            "id": "nanopi_neo",
            "name": "NanoPi-Neo",
            "supported": True,
        }

    return {
        "id": "unknown",
        "name": hw_platforms.machine(),
        "supported": False,
    }
# =========================================================
# Hardware Profiles
# =========================================================
@app.route("/hardware-profiles")
def hardware_profiles():
    profiles = list_hardware_profiles()
    return render_template("hardware_profiles.html", profiles=profiles)


# =========================================================
# GPIOD Support
# =========================================================
# services/platform_service.py

def detect_gpiod_support():
    """
    Return True if this system exposes Linux GPIO character devices.
    """

    return any(Path("/dev").glob("gpiochip*"))


def platform_supports_gpiod(model):
    """
    Decide whether GPIOD options should be shown.

    Explicit platform setting wins.
    Runtime detection is fallback.
    """

    platform = model.get("platform", {})

    if "supports_gpiod" in platform:
        return bool(platform["supports_gpiod"])

    return detect_gpiod_support()
# =========================================================
# Node model defaults
# =========================================================

def default_node_model():
    """
    This is the authoritative in-memory model.
    svxlink.conf should eventually be generated from this.
    """

    return {
        "platform": detect_platform(),
        "node_type": None,          # simplex | repeater
        "callsign": None,
        "language": "en_US",

        "reflector": {
            "enabled": False,
            "name": None,
            "host": None,
            "port": None,
            "auth_key": None,
        },

        "ident": {
            "short": {
                "mode": None,       # none | cw | voice | both
                "interval": 15,
            },
            "long": {
                "mode": None,       # none | cw | voice | both
                "interval": 60,
            },
        },

        "courtesy": {
            "mode": "none",         # none | beep | morse_t | morse_k
        },

        "squelch": {
            "method": None,         # gpiod | ctcss
            "ctcss_freq": None,
            "ctcss_tx": False,
        },

        "modules": [
            "ModuleHelp",
            "ModuleParrot",
        ],
    }


# =========================================================
# Model persistence
# =========================================================

def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)



# =========================================================
# SvxLink service wrapper
# =========================================================

def svxlink_status():
    result = subprocess.run(
        ["systemctl", "is-active", "pi3twe-svxlink.service"],
        text=True,
        capture_output=True
    )

    return result.stdout.strip()

# =========================================================
# Wizard routes
# =========================================================

@app.route("/", methods=["GET"])
def index():
    return redirect(url_for("status_page"))


@app.route("/start", methods=["GET", "POST"])
def start():
    model = load_node_model()
    resume_after_reboot = model.get("build", {}).get("resume_after_reboot")
    if resume_after_reboot:
        return redirect(resume_after_reboot)
    
    if "build" not in model:
        model["build"] = {
            "intent": "single_channel",
        }

    if request.method == "POST":
        build_intent = request.form.get("build_intent", "single_channel").strip()

        if build_intent not in ("single_channel", "multichannel"):
            build_intent = "single_channel"

        model["build"]["intent"] = build_intent
        save_node_model(model)

        return redirect(url_for("platform_page"))

    return render_template("start.html", model=model)

@app.route("/platform", methods=["GET", "POST"])
def platform_page():
    model = load_node_model()

    if request.method == "POST":
        # Platform is normally detected, not user-selected.
        save_node_model(model)
        return redirect(url_for("hardware_page"))

    return render_template("platform.html", model=model)

@app.route("/hardware", methods=["GET", "POST"])
def hardware_page():
    model = load_node_model()

    build_intent = (
        model.get("build", {})
        .get("intent", "single_channel")
    )

    all_profiles = list_hardware_profiles()

    if build_intent == "multichannel":
        profiles = [
            profile for profile in all_profiles
            if profile.get("type") in ("port_based", "multi_interface")
        ]
    else:
        profiles = [
            profile for profile in all_profiles
            if profile.get("type") == "generic"
        ]

    if request.method == "POST":
        hardware_profile_id = request.form.get("hardware_profile_id", "").strip()

        allowed_profile_ids = {
            profile["profile_id"]
            for profile in profiles
        }

        if hardware_profile_id not in allowed_profile_ids:
            return render_template(
                "hardware.html",
                model=model,
                profiles=profiles,
                build_intent=build_intent,
                error="Please select a valid hardware profile for this build type.",
            )

        model["hardware_profile_id"] = hardware_profile_id

        profile = load_hardware_profile(hardware_profile_id)

        model["hardware"] = {
            "profile_id": hardware_profile_id,
            "profile_name": profile.get("name"),
            "type": profile.get("type"),
            "family": profile.get("family"),
            "ports": profile.get("ports", 1),
        }

        model["hardware_preparation"] = {
            "required": bool(profile.get("preparation", {}).get("required")),
            "requires_reboot": bool(profile.get("preparation", {}).get("requires_reboot")),
            "service": profile.get("preparation", {}).get("service"),
            "status": "pending" if profile.get("preparation", {}).get("required") else "not_required",
            "resume_after_reboot": profile.get("preparation", {}).get("resume_after_reboot"),
        }
        if hardware_profile_id == "generic_single":
            model.setdefault("audio", {})

            current_audio_dev = (
            model["audio"].get("audio_dev", "").strip()
        )

            # Upgrade the old numeric default while preserving any
            # explicit custom or previously discovered device.
            if current_audio_dev in ("", "alsa:plughw:0"):
                detected_audio_dev = discover_default_audio_dev()

                if detected_audio_dev:
                    model["audio"]["audio_dev"] = detected_audio_dev

        save_node_model(model)

        if profile.get("preparation", {}).get("required"):
            return redirect(url_for("hardware_prepare_page"))

        return redirect(url_for("hardware_ports_page"))

    return render_template(
        "hardware.html",
        model=model,
        profiles=profiles,
        build_intent=build_intent,
        error=None,
    )
@app.route("/hardware-prepare")
def hardware_prepare_page():
    model = load_node_model()

    hardware_profile_id = model.get("hardware_profile_id")

    if not hardware_profile_id:
        return redirect(url_for("hardware_page"))

    try:
        profile = load_hardware_profile(hardware_profile_id)
    except FileNotFoundError:
        return redirect(url_for("hardware_page"))

    return render_template(
        "hardware_prepare.html",
        model=model,
        profile=profile,
    )


@app.route("/hardware-prepare/reviewed", methods=["POST"])
def hardware_prepare_reviewed_page():
    model = load_node_model()

    hardware_profile_id = model.get("hardware_profile_id")

    if not hardware_profile_id:
        return redirect(url_for("hardware_page"))

    try:
        profile = load_hardware_profile(hardware_profile_id)
    except FileNotFoundError:
        return redirect(url_for("hardware_page"))

    requires_physical_confirmation = (
        profile.get("family") == "ics"
        or profile.get("type") == "port_based"
    )

    if requires_physical_confirmation:
        confirmed = request.form.get("confirm_hardware") == "yes"

        if not confirmed:
            return render_template(
                "hardware_prepare.html",
                model=model,
                profile=profile,
                error="Please confirm that the selected ICS board is physically installed.",
            )

    if "hardware_preparation" not in model:
        model["hardware_preparation"] = {}

    model["hardware_preparation"]["status"] = "reviewed"
    model["hardware_preparation"]["physical_profile_confirmed"] = (
        requires_physical_confirmation
    )

    save_node_model(model)

    if profile.get("family") == "ics":
        return redirect(url_for("ics_prepare_page"))

    return redirect(url_for("hardware_ports_page"))
@app.route("/hardware-ports", methods=["GET", "POST"])
def hardware_ports_page():
    model = load_node_model()

    hardware_profile_id = model.get("hardware_profile_id")

    if not hardware_profile_id:
        return redirect(url_for("hardware_page"))

    try:
        profile = load_hardware_profile(hardware_profile_id)
    except FileNotFoundError:
        return redirect(url_for("hardware_page"))
    if profile.get("family") == "ics":
        ics_prepare = model.get("ics_prepare", {})
        if not ics_prepare.get("verified"):
            return redirect(url_for("ics_prepare_page"))
    port_count = int(profile.get("ports", 1))
    available_ports = list(range(1, port_count + 1))

    if request.method == "POST":
        selected_ports = request.form.getlist("enabled_ports")

        enabled_ports = []
        for port in selected_ports:
            try:
                port_number = int(port)
            except ValueError:
                continue

            if port_number in available_ports:
                enabled_ports.append(port_number)

        enabled_ports = sorted(set(enabled_ports))

        if not enabled_ports:
            return render_template(
                "hardware_ports.html",
                model=model,
                profile=profile,
                available_ports=available_ports,
                enabled_ports=model.get("ports", {}).get("enabled", available_ports),
                error="Select at least one port.",
                version_info=get_version_info(),
            )

        model["ports"] = {
            "available": available_ports,
            "enabled": enabled_ports,
        }

        if profile.get("family") == "ics":
            try:
                model = update_model_gpiod_discovery(model)
            except Exception as exc:
                return render_template(
                    "hardware_ports.html",
                    model=model,
                    profile=profile,
                    available_ports=available_ports,
                    enabled_ports=enabled_ports,
                    error=f"GPIOD discovery failed after port selection: {exc}",
                    version_info=get_version_info(),
                )

        save_node_model(model)

#        if len(enabled_ports) > 1:
#            return redirect(url_for("port_roles_page"))

        return redirect(url_for("hardware_review_page"))

    enabled_ports = (
        model.get("ports", {})
        .get("enabled", available_ports)
    )

    return render_template(
        "hardware_ports.html",
        model=model,
        profile=profile,
        available_ports=available_ports,
        enabled_ports=enabled_ports,
        error=None,
    )
@app.route("/hardware-review", methods=["GET", "POST"])
def hardware_review_page():
    model = load_node_model()

    hardware_profile_id = model.get("hardware_profile_id")

    if not hardware_profile_id:
        return redirect(url_for("hardware_page"))

    try:
        profile = load_hardware_profile(hardware_profile_id)
    except FileNotFoundError:
        return redirect(url_for("hardware_page"))

    ports = model.get("ports", {})
    available_ports = ports.get("available", [])
    enabled_ports = ports.get("enabled", [])
    if not available_ports or not enabled_ports:
        return redirect(url_for("hardware_ports_page"))

    if request.method == "POST":
        return redirect(url_for("environment_page"))

    return render_template(
        "hardware_review.html",
        model=model,
        profile=profile,
        available_ports=available_ports,
        enabled_ports=enabled_ports,
        error=None,
        version_info=get_version_info
    )
@app.route("/ics_prepare", methods=["GET", "POST"])
def ics_prepare_page():
    model = load_node_model()
    message = None
    error = None

    selected_profile = (
        model.get("hardware_profile_id")
        or model.get("hardware", {}).get("profile")
        or "ics_4x"
    )

    if request.method == "POST":
        action = request.form.get("action", "")
        selected_profile = request.form.get("profile", selected_profile)

        model["hardware_profile_id"] = selected_profile
        save_node_model(model)

        if action == "enable_i2c":
            result = enable_i2c()

            if result["ok"]:
                model.setdefault("build", {})
                model["build"]["resume_after_reboot"] = "/ics_prepare"

                model.setdefault("ics_prepare", {})
                model["ics_prepare"]["i2c_enable_requested"] = True
                model["ics_prepare"]["reboot_required"] = False

                save_node_model(model)

                message = (
                    result["stdout"]
                    or "I²C enable request completed. Reboot required before continuing."
                )
            else:
                error = result["stderr"] or result["stdout"] or "Failed to enable I²C."
        elif action == "set_overlay":
            result = set_overlay(selected_profile)

            if result["ok"]:
                model.setdefault("build", {})
                audio_result = configure_audio_boot(selected_profile)
                
                if not audio_result["ok"]:
                    error = (
                        audio_result["stderr"]
                        or audio_result["stdout"]
                        or "Failed to configure ICS audio boot overlays."
                    )
                else:
                    message = (
                        result["stdout"]
                        or "Overlay applied. Reboot required before continuing."
                    )
                
                    if audio_result["stdout"]:
                        message += "\n" + audio_result["stdout"]                
                model["build"]["resume_after_reboot"] = "/ics_prepare"

                model.setdefault("ics_prepare", {})
                model["ics_prepare"]["overlay_applied"] = selected_profile
                model["ics_prepare"]["reboot_required"] = True
                model["ics_prepare"]["verified"] = False
                model["ics_prepare"]["audio_boot_configured"] = True
                save_node_model(model)

                message = (
                    result["stdout"]
                    or f"Overlay set for {selected_profile}. Reboot required before continuing."
                )
                if audio_result["stdout"]:
                    message += "\n" + audio_result["stdout"]
            else:
                error = result["stderr"] or result["stdout"] or "Failed to set ICS overlay."
        elif action == "reboot":
            model.setdefault("build", {})
            model["build"]["resume_after_reboot"] = "/ics_prepare"
        
            model.setdefault("ics_prepare", {})
            model["ics_prepare"]["reboot_required"] = True
        
            save_node_model(model)
        
            result = schedule_reboot(8)
        
            if result.returncode != 0:
                error = result.stderr or result.stdout or "Failed to schedule reboot."
            else:
                return redirect(url_for("rebooting_page"))
        else:
            error = "Unknown action."

    status = build_ics_status(selected_profile)
    if (
        status.get("i2c")
        and status["i2c"].get("ok")
        and status.get("gpio_names")
        and status["gpio_names"].get("ok")
    ):
        model.setdefault("ics_prepare", {})
        model["ics_prepare"]["reboot_required"] = False
        model["ics_prepare"]["verified"] = True

        try:
            model = update_model_gpiod_discovery(model)

            missing_lines = (
                model.get("gpiod", {})
                .get("missing_lines", [])
            )

            if missing_lines:
                error = (
                    "GPIOD discovery completed, but these required lines "
                    "were not found: "
                    + ", ".join(missing_lines)
                )
            else:
                pcm1803_result = configure_pcm1803(selected_profile)

                if not pcm1803_result["ok"]:
                    error = (
                        pcm1803_result["stderr"]
                        or pcm1803_result["stdout"]
                        or "Failed to configure PCM1803 service."
                    )
                elif selected_profile in ("ics_4x", "ics_8x"):
                    message = (
                        message
                        or "ICS GPIO lines discovered and PCM1803 service enabled."
                    )
                else:
                    message = (
                        message
                        or "ICS GPIO lines discovered. PCM1803 service disabled for this profile."
                    )

        except Exception as exc:
            error = f"GPIOD discovery failed: {exc}"

        if "build" in model and not error:
            model["build"].pop("resume_after_reboot", None)

    save_node_model(model)
    return render_template(
        "ics_prepare.html",
        model=model,
        profiles=get_ics_profiles(),
        selected_profile=selected_profile,
        status=status,
        message=message,
        error=error,
        version_info=get_version_info(),
    )
@app.route("/rebooting")
def rebooting_page():
    return render_template(
        "rebooting.html",
        version_info=get_version_info(),
    )      
@app.route("/environment", methods=["GET", "POST"])
def environment_page():
    model = load_node_model()
    error = None

    if "environment" not in model:
        model["environment"] = {}

    if request.method == "POST":

        environment = request.form.get("environment", "").strip()

        if not environment:
            error = "Please select an operating environment."

        else:

            if environment == "north_america":
                language = "en_US"
                metar_region = "north_america"

            elif environment == "australia_nz":
                language = "en_AU"
                metar_region = "australia"

            else:
                environment = "british_isles"
                language = "en_GB"
                metar_region = "ukwide"

            model["environment"] = {
                "region": environment,
            }

            # Region controls network defaults; retain the selected voice.
            selected_language = model.get("language", {}).get("default")
            model["language"] = {"default": selected_language or language}
            model.setdefault("metar", {})
            model["metar"]["region"] = metar_region

            save_node_model(model)

            return redirect(url_for("timezone_page"))

    return render_template(
        "environment.html",
        model=model,
        error=error,
    )
@app.route("/timezone", methods=["GET", "POST"])
def timezone_page():
    model = load_node_model()
    error = None

    if "timezone" not in model:
        model["timezone"] = {}

    environment = (
        model.get("environment", {})
        .get("region", "british_isles")
    )

    timezones = TIMEZONES.get(environment, {})

    if request.method == "POST":

        timezone = request.form.get("timezone", "").strip()

        if not timezone:
            error = "Please select a time zone."

        elif timezone not in timezones:
            error = "Invalid time zone selection."

        else:
            model["timezone"] = {
                "name": timezone,
            }

            save_node_model(model)

            return redirect(next_after_timezone(model))

    return render_template(
        "timezone.html",
        model=model,
        timezones=timezones,
        error=error,
    )
    
def is_multiport_build(model):
    enabled_ports = model.get("ports", {}).get("enabled", [])
    hardware = model.get("hardware", {})
    profile_id = (
        model.get("hardware_profile_id")
        or hardware.get("profile")
        or hardware.get("profile_id")
        or ""
    )

    return (
        profile_id in ("ics_1x","ics_2x", "ics_4x", "ics_8x")
        or len(enabled_ports) > 1
    )

def next_after_timezone(model):
    if is_multiport_build(model):
        return url_for("reflector_page")

    return url_for("node_page")

def next_after_reflector(model):
    if is_multiport_build(model):
        return url_for("port_roles_page")

    return url_for("review_page")
def initialise_port_nodes(model, profile):
    ports = model.get("ports", {})
    enabled_ports = ports.get("enabled", [])
    port_roles = model.get("port_roles", {})
    port_map = profile.get("port_map", {})

    existing_nodes = model.get("nodes", {})
    nodes = {}

    for port in enabled_ports:
        port_id = str(port)

        role_entry = port_roles.get(port_id, {})

        if isinstance(role_entry, dict):
            role = role_entry.get("role", "simplex")
        else:
            role = role_entry or "simplex"

        if role not in ("simplex", "repeater"):
            role = "simplex"

        mapping = port_map.get(port_id, {})

        node = existing_nodes.get(port_id, {}).copy()

        node.setdefault("port", port)
        node["role"] = role
        node.setdefault("enabled", True)
        node.setdefault("name", f"Port {port} {role.title()}")
        node.setdefault("callsign", None)
        node.setdefault(
            "language",
            model.get("language", {}).get("default", "en_GB")
        )
        node.setdefault("configured", False)

        node.setdefault("audio", {})
        node["audio"].setdefault("rx_audio", mapping.get("rx_audio"))
        node["audio"].setdefault("tx_audio", mapping.get("tx_audio"))

        node.setdefault("gpio", {})
        node["gpio"].setdefault("ptt", mapping.get("ptt"))
        node["gpio"].setdefault("cos", mapping.get("cos"))
        node["gpio"].setdefault("enable", mapping.get("enable"))
        node["gpio"].setdefault("control", mapping.get("control"))
        node.setdefault("hidraw", {})

        try:
            hidraw_index = int(port_id) - 1
        except ValueError:
            hidraw_index = 0
        
        node["hidraw"].setdefault(
            "device",
            mapping.get("hidraw_device", f"/dev/hidraw{hidraw_index}")
        )
        
        node["hidraw"].setdefault(
            "sql_pin",
            mapping.get("hidraw_sql_pin", "VOL_DN")
        )
        
        node["hidraw"].setdefault(
            "ptt_pin",
            mapping.get("hidraw_ptt_pin", "GPIO3")
        )
        
        node["hidraw"].setdefault("sql_invert", False)
        node["hidraw"].setdefault("ptt_invert", False)
        nodes[port_id] = node

    return nodes
@app.route("/port-roles", methods=["GET", "POST"])
def port_roles_page():
    model = load_node_model()

    ports = model.get("ports", {})
    enabled_ports = ports.get("enabled", [])

    if not is_multiport_build(model):
        return redirect(url_for("node_page"))

    if not enabled_ports:
        return redirect(url_for("hardware_ports_page"))

    existing_roles = model.get("port_roles", {})

    if request.method == "POST":
        port_roles = {}

        for port in enabled_ports:
            role = request.form.get(f"port_{port}_role", "").strip()

            if role not in ("simplex", "repeater"):
                return render_template(
                    "port_roles.html",
                    model=model,
                    enabled_ports=enabled_ports,
                    port_roles=existing_roles,
                    error=f"Please select a valid role for Port {port}.",
                    version_info=get_version_info(),
                )

            port_roles[str(port)] = {
                "role": role,
            }

        model["port_roles"] = port_roles

        nodes = model.get("nodes", {})

        for port in enabled_ports:
            port_id = str(port)
            node = nodes.get(port_id, {})

            node["role"] = port_roles[port_id]["role"]
            nodes[port_id] = node

        model["nodes"] = nodes
        save_node_model(model)

        return redirect(url_for("port_config_page"))

    return render_template(
        "port_roles.html",
        model=model,
        enabled_ports=enabled_ports,
        port_roles=existing_roles,
        error=None,
        version_info=get_version_info(),
    )
@app.route("/port-config", methods=["GET", "POST"])
def port_config_page():
    model = load_node_model()

    hardware_profile_id = model.get("hardware_profile_id")
    ports = model.get("ports", {})
    enabled_ports = ports.get("enabled", [])

    if not is_multiport_build(model):
        return redirect(url_for("node_page"))

    if not enabled_ports:
        return redirect(url_for("hardware_ports_page"))

    if not model.get("port_roles"):
        return redirect(url_for("port_roles_page"))

    try:
        profile = load_hardware_profile(hardware_profile_id)
    except FileNotFoundError:
        return redirect(url_for("hardware_page"))
    profile.setdefault("port_map", {})

    if request.method == "POST":
        first_port = str(enabled_ports[0])

        model["nodes"] = initialise_port_nodes(model, profile)

        model.setdefault("build", {})
        model["build"]["multi_node"] = True
        model["build"]["active_port"] = first_port

        save_node_model(model)

        return redirect(url_for("port_config_page"))

    nodes = model.get("nodes", {})

    nodes_need_initialising = any(
        str(port) not in nodes
        or not nodes.get(str(port), {}).get("role")
        or "audio" not in nodes.get(str(port), {})
        or "gpio" not in nodes.get(str(port), {})
        for port in enabled_ports
    )

    if nodes_need_initialising:
        model["nodes"] = initialise_port_nodes(model, profile)
        save_node_model(model)
        nodes = model.get("nodes", {})

    all_ports_configured = bool(enabled_ports) and all(
        nodes.get(str(port), {}).get("node_details_configured")
        for port in enabled_ports
    )

    return render_template(
        "port_config.html",
        model=model,
        profile=profile,
        enabled_ports=enabled_ports,
        port_roles=model.get("port_roles", {}),
        nodes=nodes,
        all_ports_configured=all_ports_configured,
        version_info=get_version_info(),
    )
@app.route("/port-node/<port_id>", methods=["GET", "POST"])
def port_node_page(port_id):
    model = load_node_model()

    nodes = model.get("nodes", {})
    node = nodes.get(port_id)

    if not node:
        return redirect(url_for("port_config_page"))

    node.setdefault("audio", {})
    node["audio"].setdefault("rx_audio", f"rx{port_id}")
    node["audio"].setdefault("tx_audio", f"tx{port_id}")

    node.setdefault("gpio", {})
    node["gpio"].setdefault("ptt", f"TX_{port_id}")
    node["gpio"].setdefault("cos", f"RX_{port_id}")
    node["gpio"].setdefault("enable", f"EN_{port_id}")
    node["gpio"].setdefault("control", f"CT_{port_id}")

    role_entry = model.get("port_roles", {}).get(port_id, {})

    if isinstance(role_entry, dict):
        role = role_entry.get("role", "simplex")
    else:
        role = role_entry or "simplex"

    node["role"] = node.get("role") or role

    nodes[port_id] = node
    model["nodes"] = nodes
    save_node_model(model)
    
    enabled_ports = [
        str(port)
        for port in model.get("ports", {}).get("enabled", [])
    ]

    if port_id not in enabled_ports:
        return redirect(url_for("port_config_page"))

    error = None

    if request.method == "POST":
        callsign = request.form.get("callsign", "").strip().upper()
        name = request.form.get("name", "").strip()
        name = name.capitalize() if name else ""

        if not callsign:
            error = "Please enter a callsign for this port."
        else:
            node["callsign"] = callsign
            node["name"] = name or node.get("name") or f"Port {port_id} {node.get('role', '').title()}"
            node["node_details_configured"] = True
            node["configured"] = True

            nodes[port_id] = node
            model["nodes"] = nodes

            model.setdefault("build", {})
            model["build"]["active_port"] = port_id

            save_node_model(model)

            return redirect(url_for("port_config_page"))

    return render_template(
        "port_node.html",
        model=model,
        port_id=port_id,
        node=node,
        error=error,
        version_info=get_version_info(),
    )
@app.route("/port-profile-review", methods=["GET", "POST"])
def port_profile_review_page():
    model = load_node_model()

    hardware = model.get("hardware", {})
    hardware_profile_id = model.get("hardware_profile_id")
    nodes = model.get("nodes", {})
    enabled_ports = model.get("ports", {}).get("enabled", [])

    if not is_multiport_build(model):
        return redirect(url_for("interface_page"))

    if not nodes:
        return redirect(url_for("port_config_page"))

    all_ports_configured = bool(enabled_ports) and all(
        nodes.get(str(port), {}).get("node_details_configured")
        for port in enabled_ports
    )

    if not all_ports_configured:
        return redirect(url_for("port_config_page"))

    try:
        profile = load_hardware_profile(hardware_profile_id)
    except FileNotFoundError:
        return redirect(url_for("hardware_page"))

    if request.method == "POST":
        model.setdefault("build", {})
        model["build"]["profile_interface_confirmed"] = True

        save_node_model(model)

        return redirect(url_for("port_squelch_page"))

    return render_template(
        "port_profile_review.html",
        model=model,
        profile=profile,
        nodes=nodes,
        enabled_ports=enabled_ports,
        version_info=get_version_info(),
    )
@app.route("/port-squelch", methods=["GET"])
def port_squelch_page():
    model = load_node_model()

    hardware = model.get("hardware", {})
    nodes = model.get("nodes", {})
    enabled_ports = model.get("ports", {}).get("enabled", [])

    if not is_multiport_build(model):
        return redirect(url_for("squelch_page"))
    if not nodes:
        return redirect(url_for("port_config_page"))

    all_ports_configured = bool(enabled_ports) and all(
        nodes.get(str(port), {}).get("squelch_configured")
        for port in enabled_ports
    )

    return render_template(
        "port_squelch.html",
        model=model,
        nodes=nodes,
        enabled_ports=enabled_ports,
        all_ports_configured=all_ports_configured,
        version_info=get_version_info(),
    )
@app.route("/port-squelch-complete", methods=["GET"])
def port_squelch_complete_page():
    model = load_node_model()

    hardware = model.get("hardware", {})
    nodes = model.get("nodes", {})
    enabled_ports = model.get("ports", {}).get("enabled", [])

    if not is_multiport_build(model):
        return redirect(url_for("squelch_page"))

    all_ports_configured = bool(enabled_ports) and all(
        nodes.get(str(port), {}).get("squelch_configured")
        for port in enabled_ports
    )

    if not all_ports_configured:
        return redirect(url_for("port_squelch_page"))

    model.setdefault("build", {})
    model["build"]["port_squelch_configured"] = True

    save_node_model(model)

    return redirect(url_for("port_modules_page"))
@app.route("/port-squelch/<port_id>", methods=["GET", "POST"])
def port_squelch_detail_page(port_id):
    model = load_node_model()

    hardware = model.get("hardware", {})
    nodes = model.get("nodes", {})
    node = nodes.get(port_id)

    if not is_multiport_build(model):
        return redirect(url_for("squelch_page"))

    if not node:
        return redirect(url_for("port_squelch_page"))

    enabled_ports = [
        str(port)
        for port in model.get("ports", {}).get("enabled", [])
    ]

    if port_id not in enabled_ports:
        return redirect(url_for("port_squelch_page"))

    error = None

    if request.method == "POST":
        method = request.form.get("squelch_method", "gpiod").strip()
        ctcss_mode = request.form.get("ctcss_mode", "rx").strip()
        ctcss_freq = request.form.get("ctcss_freq", "").strip()

        valid_ctcss_values = {
            value
            for value, _label in CTCSS_FREQUENCIES
        }

        if hardware.get("family") == "ics":
            valid_squelch_methods = {"gpiod", "ctcss"}
        else:
            valid_squelch_methods = {"hidraw", "gpiod", "ctcss", "serial"}
        if method not in valid_squelch_methods:
            error = "Please select a valid squelch source."
            
        elif method == "ctcss" and ctcss_mode not in ("rx", "rx_tx"):
            error = "Please select a valid CTCSS behaviour."

        elif ctcss_freq and ctcss_freq not in valid_ctcss_values:
            error = "Please select a valid CTCSS frequency."

        elif method == "ctcss" and not ctcss_freq:
            error = "Please select a CTCSS frequency when SvxLink CTCSS squelch is selected."

        else:
            if method != "ctcss":
                ctcss_mode = "none"
                ctcss_freq = ""

            node.setdefault("gpio", {})
            node.setdefault("hidraw", {})
            node.setdefault("serial", {})

            node["gpio"]["cos_invert"] = (
                request.form.get("sql_gpio_invert") == "yes"
            )

            node["gpio"]["ptt_invert"] = (
                request.form.get("ptt_gpio_invert") == "yes"
            )

            node["hidraw"]["sql_invert"] = (
                request.form.get("hidraw_sql_invert") == "yes"
            )

            node["serial"]["sql_invert"] = (
                request.form.get("serial_sql_invert") == "yes"
            )
            node["hidraw"]["ptt_invert"] = (
                request.form.get("hidraw_ptt_invert") == "yes"
            )

            node["squelch"] = {
                "method": method,
                "ctcss_mode": ctcss_mode,
                "ctcss_freq": ctcss_freq or None,
            }
            node["squelch_configured"] = True

            nodes[port_id] = node
            model["nodes"] = nodes

            model.setdefault("build", {})
            model["build"]["active_port"] = port_id

            save_node_model(model)

            return redirect(url_for("port_squelch_page"))
    return render_template(
        "port_squelch_detail.html",
        model=model,
        hardware=hardware,
        port_id=port_id,
        node=node,
        squelch=node.get("squelch", {}),
        ctcss_frequencies=CTCSS_FREQUENCIES,
        error=error,
        version_info=get_version_info(),
    )
@app.route("/port-modules", methods=["GET", "POST"])
def port_modules_page():
    model = load_node_model()

    nodes = model.get("nodes", {})
    enabled_ports = model.get("ports", {}).get("enabled", [])

    if not is_multiport_build(model):
        return redirect(url_for("modules_page"))

    if not nodes:
        return redirect(url_for("port_config_page"))

    enabled_port_ids = [str(port) for port in enabled_ports]
    modules_multi = model.get("modules_multi", {})

    if request.method == "POST":
        echolink_port = request.form.get("echolink_port", "none").strip()

        if echolink_port == "none":
            echolink_port = None
        elif echolink_port not in enabled_port_ids:
            echolink_port = None

        metar_ports = request.form.getlist("metar_ports")
        metar_ports = [
            port_id
            for port_id in metar_ports
            if port_id in enabled_port_ids
        ]

        for port_id in enabled_port_ids:
            node = nodes.get(port_id, {})
            node["modules"] = {
                "echolink": port_id == echolink_port,
                "metar": port_id in metar_ports,
            }
            nodes[port_id] = node

        model["nodes"] = nodes
        model["modules_multi"] = {
            "echolink_port": echolink_port,
            "metar_ports": metar_ports,
        }

        model.setdefault("build", {})
        model["build"]["port_modules_configured"] = True

        model.setdefault("modules", {})
        global_enabled = set(model["modules"].get("enabled", []))

        if echolink_port:
            global_enabled.add("ModuleEchoLink")
        else:
            global_enabled.discard("ModuleEchoLink")

        if metar_ports:
            global_enabled.add("ModuleMetarInfo")
        else:
            global_enabled.discard("ModuleMetarInfo")

        model["modules"]["enabled"] = sorted(global_enabled)

        if metar_ports and not model.get("metar", {}).get("startdefault"):
            model["build"]["return_after_metar"] = "port_ident_page"
            model["build"].pop("return_after_modules", None)
            save_node_model(model)
            return redirect(url_for("metar_default_page"))

        model["build"].pop("return_after_modules", None)
        model["build"].pop("return_after_metar", None)

        save_node_model(model)

        return redirect(url_for("port_ident_page"))

    return render_template(
        "port_modules.html",
        model=model,
        nodes=nodes,
        enabled_ports=enabled_ports,
        modules_multi=modules_multi,
        version_info=get_version_info(),
    )
@app.route("/port-ident", methods=["GET", "POST"])
def port_ident_page():
    model = load_node_model()
    error = None

    hardware = model.get("hardware", {})
    nodes = model.get("nodes", {})
    enabled_ports = model.get("ports", {}).get("enabled", [])

    if not is_multiport_build(model):
        return redirect(url_for("ident_page"))

    if not nodes:
        return redirect(url_for("port_config_page"))

    enabled_port_ids = [
        str(port)
        for port in enabled_ports
    ]

    if request.method == "POST":
        try:
            for port_id in enabled_port_ids:
                node = nodes.get(port_id, {})

                existing_ident = node.get("ident", {})
                existing_short = existing_ident.get("short", {})
                existing_long = existing_ident.get("long", {})

                short_interval = request.form.get(
                    f"port_{port_id}_short_ident_interval",
                    "15"
                ).strip()

                long_interval = request.form.get(
                    f"port_{port_id}_long_ident_interval",
                    "60"
                ).strip()

                try:
                    short_interval_value = int(short_interval)
                except ValueError:
                    short_interval_value = 15

                try:
                    long_interval_value = int(long_interval)
                except ValueError:
                    long_interval_value = 60

                short_upload = request.files.get(
                    f"port_{port_id}_short_announce_file"
                )

                long_upload = request.files.get(
                    f"port_{port_id}_long_announce_file"
                )

                short_announce_file = save_ident_upload(
                    short_upload,
                    f"port{port_id}_short_ident",
                )

                long_announce_file = save_ident_upload(
                    long_upload,
                    f"port{port_id}_long_ident",
                )

                if not short_announce_file:
                    short_announce_file = existing_short.get(
                        "announce_file",
                        ""
                    )

                if not long_announce_file:
                    long_announce_file = existing_long.get(
                        "announce_file",
                        ""
                    )

                node["ident"] = {
                    "short": {
                        "interval": short_interval_value,
                        "voice_enable": request.form.get(
                            f"port_{port_id}_short_voice_enable"
                        ) == "1",
                        "cw_enable": request.form.get(
                            f"port_{port_id}_short_cw_enable"
                        ) == "1",
                        "announce_enable": request.form.get(
                            f"port_{port_id}_short_announce_enable"
                        ) == "1",
                        "announce_file": short_announce_file,
                    },
                    "long": {
                        "interval": long_interval_value,
                        "voice_enable": request.form.get(
                            f"port_{port_id}_long_voice_enable"
                        ) == "1",
                        "cw_enable": request.form.get(
                            f"port_{port_id}_long_cw_enable"
                        ) == "1",
                        "announce_enable": request.form.get(
                            f"port_{port_id}_long_announce_enable"
                        ) == "1",
                        "announce_file": long_announce_file,
                    },
                }

                node["ident_configured"] = True
                nodes[port_id] = node

            model["nodes"] = nodes

            model.setdefault("build", {})
            model["build"]["port_ident_configured"] = True

            save_node_model(model)

            return redirect(url_for("port_cw_page"))

        except Exception as exc:
            error = f"Announcement file upload failed: {exc}"

    return render_template(
        "port_ident.html",
        model=model,
        nodes=nodes,
        enabled_ports=enabled_ports,
        error=error,
        version_info=get_version_info(),
    )
@app.route("/port-cw", methods=["GET", "POST"])
def port_cw_page():
    model = load_node_model()

    hardware = model.get("hardware", {})
    nodes = model.get("nodes", {})
    enabled_ports = model.get("ports", {}).get("enabled", [])

    if not is_multiport_build(model):
        return redirect(url_for("cw_page"))

    if not nodes:
        return redirect(url_for("port_config_page"))

    enabled_port_ids = [
        str(port)
        for port in enabled_ports
    ]

    if request.method == "POST":
        for port_id in enabled_port_ids:
            node = nodes.get(port_id, {})

            amp = request.form.get(f"port_{port_id}_cw_amp", "-10").strip()
            pitch = request.form.get(f"port_{port_id}_cw_pitch", "650").strip()
            cpm = request.form.get(f"port_{port_id}_cw_cpm", "95").strip()

            try:
                amp_value = int(amp)
            except ValueError:
                amp_value = -10

            try:
                pitch_value = int(pitch)
            except ValueError:
                pitch_value = 650

            try:
                cpm_value = int(cpm)
            except ValueError:
                cpm_value = 95

            node["cw"] = {
                "amp": amp_value,
                "pitch": pitch_value,
                "cpm": cpm_value,
            }

            node["cw_configured"] = True
            nodes[port_id] = node

        model["nodes"] = nodes

        model.setdefault("build", {})
        model["build"]["port_cw_configured"] = True

        save_node_model(model)

        return redirect(url_for("port_courtesy_page"))

    return render_template(
        "port_cw.html",
        model=model,
        nodes=nodes,
        enabled_ports=enabled_ports,
        version_info=get_version_info(),
    )
@app.route("/port-courtesy", methods=["GET", "POST"])
def port_courtesy_page():
    model = load_node_model()

    hardware = model.get("hardware", {})
    nodes = model.get("nodes", {})
    enabled_ports = model.get("ports", {}).get("enabled", [])
    if not is_multiport_build(model):
        return redirect(url_for("courtesy_page"))
    if not nodes:
        return redirect(url_for("port_config_page"))

    enabled_port_ids = [
        str(port)
        for port in enabled_ports
    ]

    if request.method == "POST":
        for port_id in enabled_port_ids:
            node = nodes.get(port_id, {})
            role = node.get("role", "simplex")

            courtesy_mode = request.form.get(
                f"port_{port_id}_courtesy_mode",
                "none"
            ).strip()

            idle_tone = request.form.get(
                f"port_{port_id}_idle_tone",
                "none"
            ).strip()

            down_tone = request.form.get(
                f"port_{port_id}_down_tone",
                "none"
            ).strip()

            if courtesy_mode not in ("none", "beep", "morse_k", "morse_t"):
                courtesy_mode = "none"

            if idle_tone not in ("none", "pip", "chime"):
                idle_tone = "none"

            if down_tone not in ("none", "biboop", "va"):
                down_tone = "none"

            node["courtesy"] = {
                "mode": courtesy_mode,
                "idle_tone": idle_tone,
                "down_tone": down_tone,
            }

            node["courtesy_configured"] = True
            nodes[port_id] = node

        model["nodes"] = nodes

        model.setdefault("build", {})
        model["build"]["port_courtesy_configured"] = True

        save_node_model(model)

        return redirect(url_for("port_repeater_page"))

    return render_template(
        "port_courtesy.html",
        model=model,
        nodes=nodes,
        enabled_ports=enabled_ports,
        version_info=get_version_info(),
    )
@app.route("/port-repeater", methods=["GET", "POST"])
def port_repeater_page():
    model = load_node_model()

    hardware = model.get("hardware", {})
    nodes = model.get("nodes", {})
    enabled_ports = model.get("ports", {}).get("enabled", [])

    if not is_multiport_build(model):
        return redirect(url_for("repeater_page"))

    if not nodes:
        return redirect(url_for("port_config_page"))

    enabled_port_ids = [
        str(port)
        for port in enabled_ports
    ]

    repeater_port_ids = [
        port_id
        for port_id in enabled_port_ids
        if nodes.get(port_id, {}).get("role") == "repeater"
    ]

    if request.method == "POST":
        for port_id in repeater_port_ids:
            node = nodes.get(port_id, {})

            idle_timeout = request.form.get(
                f"port_{port_id}_idle_timeout",
                "10"
            ).strip()

            sql_timeout = request.form.get(
                f"port_{port_id}_sql_timeout",
                "180"
            ).strip()

            open_on_sql = request.form.get(
                f"port_{port_id}_open_on_sql",
                "200"
            ).strip()

            try:
                idle_timeout_value = int(idle_timeout)
            except ValueError:
                idle_timeout_value = 10

            try:
                sql_timeout_value = int(sql_timeout)
            except ValueError:
                sql_timeout_value = 180

            try:
                open_on_sql_value = int(open_on_sql)
            except ValueError:
                open_on_sql_value = 200

            node["repeater"] = {
                "idle_timeout": idle_timeout_value,
                "sql_timeout": sql_timeout_value,
                "open_on_sql": open_on_sql_value,
                "open_sql_flank": "OPEN",
            }

            node["repeater_configured"] = True
            nodes[port_id] = node

        for port_id in enabled_port_ids:
            node = nodes.get(port_id, {})
            if node.get("role") != "repeater":
                node["repeater_configured"] = True
                nodes[port_id] = node

        model["nodes"] = nodes

        model.setdefault("build", {})
        model["build"]["port_repeater_configured"] = True

        save_node_model(model)

        return redirect(url_for("build_page"))

    return render_template(
        "port_repeater.html",
        model=model,
        nodes=nodes,
        enabled_ports=enabled_ports,
        repeater_port_ids=repeater_port_ids,
        version_info=get_version_info(),
    )
@app.route("/port-final-review", methods=["GET", "POST"])
def port_final_review_page():
    model = load_node_model()

    hardware = model.get("hardware", {})
    nodes = model.get("nodes", {})
    enabled_ports = model.get("ports", {}).get("enabled", [])

    if not is_multiport_build(model):
        return redirect(url_for("status_page"))

    if not nodes:
        return redirect(url_for("port_config_page"))

    enabled_port_ids = [
        str(port)
        for port in enabled_ports
    ]

    required_flags = [
        "node_details_configured",
        "squelch_configured",
        "ident_configured",
        "cw_configured",
        "courtesy_configured",
        "repeater_configured",
    ]

    incomplete = []

    for port_id in enabled_port_ids:
        node = nodes.get(port_id, {})

        for flag in required_flags:
            if not node.get(flag):
                incomplete.append({
                    "port_id": port_id,
                    "node": node,
                    "missing": flag,
                })

    if request.method == "POST":
        if incomplete:
            return redirect(url_for("port_final_review_page"))

        model.setdefault("build", {})
        model["build"]["port_final_review_confirmed"] = True

        save_node_model(model)

        return redirect(url_for("build_page"))

    return render_template(
        "port_final_review.html",
        model=model,
        nodes=nodes,
        enabled_ports=enabled_ports,
        incomplete=incomplete,
        version_info=get_version_info(),
    )
#def render_port_rx_section(model, port_id, node):
#    """
#    Render one Rx section for an ICS port.
#    """
#
#    audio = node.get("audio", {})
#    squelch = node.get("squelch", {})
#    gpio = node.get("gpio", {})
#
#    rx_name = f"Rx{port_id}"
#    audio_dev = audio.get("rx_audio", f"alsa:rx{port_id}")
#
#    method = squelch.get("method", "gpiod")
#    ctcss_mode = squelch.get("ctcss_mode", "radio")
#    ctcss_freq = squelch.get("ctcss_freq")
#
#    lines = [
#        f"[{rx_name}]",
#        "TYPE=Local",
#        f"AUDIO_DEV={audio_dev}",
#        "AUDIO_CHANNEL=0",
#        "SQL_DET=GPIOD" if method == "gpiod" else "SQL_DET=CTCSS",
#        f"SQL_HANGTIME={model.get('sql_hangtime', 20)}",
#        f"SQL_TAIL_ELIM={model.get('sql_tail_elim', 270)}",
#    ]
#
#    if method == "gpiod":
#        sql_gpio = gpio.get("cos", f"RX_{port_id}")
#
#        if gpio.get("cos_invert"):
#            sql_gpio = f"!{sql_gpio}"
#
#        lines.extend([
#            f"SQL_GPIO={sql_gpio}",
#        ])        
#    if method == "ctcss" and ctcss_mode in ("rx", "rx_tx") and ctcss_freq:
#        lines.extend([
#            f"CTCSS_FQ={ctcss_freq}",
#            "CTCSS_SNR_OFFSET=0",
#            "CTCSS_OPEN_THRESH=15",
#            "CTCSS_CLOSE_THRESH=9",
#        ])
#
#    return "\n".join(lines)
#
#
#def render_port_tx_section(model, port_id, node):
#    """
#    Render one Tx section for an ICS port.
#    """
#
#    audio = node.get("audio", {})
#    gpio = node.get("gpio", {})
#    squelch = node.get("squelch", {})
#
#    tx_name = f"Tx{port_id}"
#    audio_dev = audio.get("tx_audio", f"alsa:tx{port_id}")
#
#    ctcss_mode = squelch.get("ctcss_mode", "radio")
#    ctcss_freq = squelch.get("ctcss_freq")
#
#    ptt_gpio = gpio.get("ptt", f"TX_{port_id}")
#
#    if gpio.get("ptt_invert"):
#        ptt_gpio = f"!{ptt_gpio}"
#
#    lines = [
#        f"[{tx_name}]",
#        "TYPE=Local",
#        f"AUDIO_DEV={audio_dev}",
#        "AUDIO_CHANNEL=0",
#        "PTT_TYPE=GPIOD",
#        f"PTT_GPIO={ptt_gpio}",
#    ]
#
#    if ctcss_mode == "rx_tx" and ctcss_freq:
#        lines.extend([
#            f"CTCSS_FQ={ctcss_freq}",
#            "CTCSS_LEVEL=9",
#        ])
#
#    return "\n".join(lines)


# def render_multiport_rx_tx_sections(model):
#     """
#     Render all Rx and Tx sections for enabled ICS ports.
#     """
# 
#     nodes = model.get("nodes", {})
#     enabled_ports = model.get("ports", {}).get("enabled", [])
# 
#     rx_sections = []
#     tx_sections = []
# 
#     for port in enabled_ports:
#         port_id = str(port)
#         node = nodes.get(port_id, {})
# 
#         if not node:
#             continue
# 
#         rx_sections.append(
#             render_port_rx_section(model, port_id, node)
#         )
# 
#         tx_sections.append(
#             render_port_tx_section(model, port_id, node)
#         )
# 
#     return {
#         "rx_sections": "\n\n".join(rx_sections),
#         "tx_sections": "\n\n".join(tx_sections),
#     }

@app.route("/node", methods=["GET", "POST"])
def node_page():
    model = load_node_model()
    error = None

    if request.method == "POST":
        node_type = request.form.get("node_type")
        callsign = request.form.get("callsign", "").strip().upper()

        if node_type not in ("simplex", "repeater"):
            error = "Please select Simplex or Repeater."
        elif not callsign:
            error = "Please enter a callsign."
        else:
            model["node"]["type"] = node_type
            model["node"]["callsign"] = callsign
            save_node_model(model)
            return redirect(url_for("interface_page"))

    return render_template("node.html", model=model, error=error)


@app.route("/interface", methods=["GET", "POST"])
def interface_page():
    model = load_node_model()
    error = None

    platform_id = model.get("platform", {}).get("id", "unknown")
    supports_gpiod = platform_id in ("raspberry_pi", "nanopi_neo")

    gpio_data = prepare_gpio_lines(platform_id)

    gpio_lines = flatten_gpio_lines(
        data=gpio_data,
        chip_filter="gpiochip0",
    )

    if request.method == "POST":
        interface_mode = request.form.get("interface_mode")

        if interface_mode not in ("hidraw", "gpiod", "hybrid", "serial"):
            interface_mode = "hidraw"

        model.setdefault("interface", {})
        model.setdefault("serial", {})
        model.setdefault("gpio", {})
        model["gpio"].setdefault("sql", {})
        model["gpio"].setdefault("ptt", {})

        model["interface"]["mode"] = interface_mode

        if interface_mode == "hidraw":
            model["interface"]["sql_source"] = "hidraw"
            model["interface"]["ptt_source"] = "hidraw"

        elif interface_mode == "hybrid":
            model["interface"]["sql_source"] = "gpiod"
            model["interface"]["ptt_source"] = "hidraw"

        elif interface_mode == "serial":
            model["interface"]["sql_source"] = "serial"
            model["interface"]["ptt_source"] = "serial"

        else:
            model["interface"]["sql_source"] = "gpiod"
            model["interface"]["ptt_source"] = "gpiod"

        uses_sql_gpiod = (
            model["interface"]["sql_source"] == "gpiod"
        )

        uses_ptt_gpiod = (
            model["interface"]["ptt_source"] == "gpiod"
        )

        if interface_mode == "serial":
            model["serial"]["sql_port"] = request.form.get(
                "serial_sql_port",
                "/dev/ttyS0",
            ).strip()

            model["serial"]["sql_pin"] = request.form.get(
                "serial_sql_pin",
                "CTS",
            ).strip().upper()

            model["serial"]["ptt_port"] = request.form.get(
                "serial_ptt_port",
                "/dev/ttyS0",
            ).strip()

            model["serial"]["ptt_pin"] = request.form.get(
                "serial_ptt_pin",
                "RTS",
            ).strip().upper()

        sql_line = (
            request.form.get("sql_gpio_line")
            if uses_sql_gpiod
            else None
        )

        ptt_line = (
            request.form.get("ptt_gpio_line")
            if uses_ptt_gpiod
            else None
        )

        if (
            uses_sql_gpiod
            and uses_ptt_gpiod
            and sql_line
            and ptt_line
            and sql_line == ptt_line
        ):
            error = "SQL and PTT cannot use the same GPIO line."

            return render_template(
                "interface.html",
                model=model,
                error=error,
                gpio_lines=gpio_lines,
                supports_gpiod=supports_gpiod,
            )

        if uses_sql_gpiod and sql_line:
            model["gpio"]["sql"]["chip"] = "gpiochip0"
            model["gpio"]["sql"]["line"] = int(sql_line)

        if uses_ptt_gpiod and ptt_line:
            model["gpio"]["ptt"]["chip"] = "gpiochip0"
            model["gpio"]["ptt"]["line"] = int(ptt_line)

        save_node_model(model)
        return redirect(url_for("squelch_page"))

    return render_template(
        "interface.html",
        model=model,
        error=error,
        gpio_lines=gpio_lines,
        supports_gpiod=supports_gpiod,
    )
@app.route("/reconfigure/reset", methods=["GET", "POST"])
def reconfigure_reset_page():
    if request.method == "POST":
        confirmation = request.form.get("confirmation", "").strip()

        if confirmation != "RESET":
            return render_template(
                "reconfigure_reset.html",
                error="Type RESET to confirm the full reset.",
            )

        MODEL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        if MODEL_FILE.exists():
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = MODEL_BACKUP_DIR / f"node_model.json.bak-{timestamp}"
            shutil.copy2(MODEL_FILE, backup_path)
            MODEL_FILE.unlink()

        return redirect(url_for("start"))

    return render_template(
        "reconfigure_reset.html",
        error=None,
    )
    
@app.route("/squelch", methods=["GET", "POST"])
def squelch_page():
    model = load_node_model()
    error = None

    if "squelch" not in model:
        model["squelch"] = {}
        
    if request.method == "POST":
        squelch_method = request.form.get("squelch_method")
        valid_squelch_methods = {"hidraw", "gpiod", "ctcss", "serial", "vox"}
        
        if squelch_method not in valid_squelch_methods:
            error = "Please select a valid squelch method."
        else:
            model["squelch"]["method"] = squelch_method

            ctcss_freq = request.form.get("ctcss_freq", "").strip()
        
            valid_ctcss_values = {
                value
                for value, _label in CTCSS_FREQUENCIES
            }
        
            if ctcss_freq in valid_ctcss_values and ctcss_freq:
                model["squelch"]["ctcss_freq"] = ctcss_freq
            else:
                model["squelch"]["ctcss_freq"] = None
        
            model["squelch"]["ctcss_tx"] = (
                request.form.get("ctcss_tx", "no") == "yes"
            )
            if squelch_method != "ctcss":
                model["squelch"]["ctcss_freq"] = None
                model["squelch"]["ctcss_tx"] = False
            else:    
                if not model["squelch"]["ctcss_freq"]:
                    error = "Please select a valid CTCSS frequency for CTCSS squelch."
            if "serial" not in model:
                model["serial"] = {}

        model["serial"]["sql_port"] = request.form.get(
            "serial_sql_port",
            "/dev/ttyS0"
        ).strip()

        model["serial"]["sql_pin"] = request.form.get(
            "serial_sql_pin",
            "CTS"
        ).strip().upper()

        model["serial"]["sql_set_pins"] = request.form.get(
            "serial_sql_set_pins",
            "DTR!RTS"
        ).strip().upper()
        if "hidraw" not in model:
            model["hidraw"] = {}

        if "gpio" not in model:
            model["gpio"] = {}

        if "sql" not in model["gpio"]:
            model["gpio"]["sql"] = {}

        model["hidraw"]["sql_invert"] = (
            request.form.get("hidraw_sql_invert") == "yes"
        )
        model["hidraw"]["ptt_invert"] = (
            request.form.get("hidraw_ptt_invert") == "yes"
        )
        model["gpio"]["sql"]["invert"] = (
            request.form.get("sql_gpio_invert") == "yes"
        )
        save_node_model(model)
        return redirect(url_for("ident_page"))

    platform_id = model.get("platform", {}).get("id", "unknown")

    supports_gpiod = platform_id in (
            "raspberry_pi",
            "nanopi_neo",
        )
    return render_template(
        "squelch.html",
        model=model,
        supports_gpiod=supports_gpiod,
        error=error,
        ctcss_frequencies=CTCSS_FREQUENCIES,
        version_info=get_version_info(),
        )
@app.route("/ident", methods=["GET", "POST"])
def ident_page():
    model = load_node_model()
    error = None

    model.setdefault("ident", {})
    model["ident"].setdefault("short", {})
    model["ident"].setdefault("long", {})

    short_ident = model["ident"]["short"]
    long_ident = model["ident"]["long"]

    if request.method == "POST":
        try:
            short_ident["mode"] = request.form.get("short_ident_mode")
            short_ident["interval"] = int(
                request.form.get("short_ident_interval", "15")
            )

            long_ident["mode"] = request.form.get("long_ident_mode")
            long_ident["interval"] = int(
                request.form.get("long_ident_interval", "60")
            )

            short_ident["announce_enable"] = (
                request.form.get("short_announce_enable") == "1"
            )

            long_ident["announce_enable"] = (
                request.form.get("long_announce_enable") == "1"
            )

            short_upload = request.files.get("short_announce_file")
            long_upload = request.files.get("long_announce_file")

            short_file = save_ident_upload(
                short_upload,
                "single_short_ident",
            )

            long_file = save_ident_upload(
                long_upload,
                "single_long_ident",
            )

            if short_file:
                short_ident["announce_file"] = short_file
            else:
                short_ident["announce_file"] = short_ident.get(
                    "announce_file",
                    "",
                )

            if long_file:
                long_ident["announce_file"] = long_file
            else:
                long_ident["announce_file"] = long_ident.get(
                    "announce_file",
                    "",
                )

            save_node_model(model)
            return redirect(url_for("cw_page"))

        except ValueError:
            error = "Identification intervals must be numeric."

        except Exception as exc:
            error = f"Announcement file upload failed: {exc}"

    return render_template(
        "ident.html",
        model=model,
        error=error,
        version_info=get_version_info(),
    )
@app.route("/cw", methods=["GET", "POST"])
def cw_page():
    model = load_node_model()
    error = None
    reconfigure = request.values.get("mode") == "reconfigure"

    if "cw" not in model:
        model["cw"] = {
            "amp": -10,
            "pitch": 650,
            "cpm": 95,
        }

    if request.method == "POST":
        try:
            cw_amp = int(request.form.get("cw_amp", "-10"))
            cw_pitch = int(request.form.get("cw_pitch", "650"))
            cw_cpm = int(request.form.get("cw_cpm", "95"))
        except ValueError:
            error = "CW settings must be numeric."
        else:
            if cw_amp > -10 or cw_amp < -30:
                error = "CW amplitude must be between -10 and -30 dB."
            elif cw_pitch < 400 or cw_pitch > 1000:
                error = "CW pitch must be between 400 and 1000 Hz."
            elif cw_cpm < 60 or cw_cpm > 160:
                error = "CW speed must be between 60 and 160 CPM."
            else:
                model["cw"] = {
                    "amp": cw_amp,
                    "pitch": cw_pitch,
                    "cpm": cw_cpm,
                }

                save_node_model(model)

                return redirect(url_for("build_page" if reconfigure else "courtesy_page"))

    return render_template(
        "cw.html",
        model=model,
        error=error,
        reconfigure=reconfigure,
    )
    
@app.route("/courtesy", methods=["GET", "POST"])
def courtesy_page():
    model = load_node_model()
    error = None

    if "courtesy" not in model:
        model["courtesy"] = {
            "mode": "none",
            "frequency": 800,
        }

    node_type = model.get("node", {}).get("type", "simplex")

    if request.method == "POST":
        courtesy_mode = request.form.get("courtesy_mode", "").strip()
        tone_freq = request.form.get("tone_freq", "800").strip()

        if not courtesy_mode:
            error = "Please select a courtesy tone."

        elif node_type == "repeater" and courtesy_mode == "none":
            error = "Repeater systems require a courtesy tone."

        elif courtesy_mode not in ("none", "beep", "morse_t", "morse_k"):
            error = "Invalid courtesy tone selection."

        else:
            try:
                tone_freq = int(tone_freq)
            except ValueError:
                tone_freq = 800

            if tone_freq < 300 or tone_freq > 3000:
                error = "Beep frequency must be between 300 and 3000 Hz."
            else:
                model["courtesy"] = {
                    "mode": courtesy_mode,
                    "frequency": tone_freq,
                }

                save_node_model(model)
                if model.get("node", {}).get("type") == "repeater":
                    return redirect(url_for("repeater_page"))
                return redirect(url_for("modules_page"))

    return render_template(
        "courtesy.html",
        model=model,
        error=error,
    )
@app.route("/repeater", methods=["GET", "POST"])
def repeater_page():
    model = load_node_model()
    error = None

    if "repeater" not in model:
        model["repeater"] = {
            "idle_timeout": 10,
            "sql_timeout": 180,
            "idle_tone": "chime",
            "down_tone": "biboop",
        }

    if "online_control" not in model:
        model["online_control"] = {
            "enabled": False,
            "command": "998877",
        }

    if request.method == "POST":
        print("REPEATER FORM:", dict(request.form), flush=True)
        try:
            idle_timeout = int(request.form.get("idle_timeout", "10"))
            sql_timeout = int(request.form.get("sql_timeout", "180"))
        except ValueError:
            error = "Timeout values must be numeric."
        else:
            online_enabled = request.form.get("online_enabled") == "yes"
            online_command = request.form.get("online_command", "").strip()

            if idle_timeout < 1 or idle_timeout > 20:
                error = "Idle timeout must be between 1 and 20 seconds."

            elif sql_timeout < 120 or sql_timeout > 300:
                error = "SQL timeout must be between 120 and 300 seconds."

            elif online_enabled and not (
                online_command.isdigit()
                and len(online_command) == 6
                and online_command[0] in "34567"
            ):
                error = "Online control command must be six digits and begin with 3, 4, 5, 6, or 7."

            else:
                model["repeater"] = {
                    "idle_timeout": idle_timeout,
                    "sql_timeout": sql_timeout,
                    "idle_tone": request.form.get("idle_tone", "chime"),
                    "down_tone": request.form.get("down_tone", "biboop"),
                }

                model["online_control"] = {
                    "enabled": online_enabled,
                    "command": online_command or "998877",
                }

                save_node_model(model)

                return redirect(url_for("modules_page"))

    return render_template(
        "repeater.html",
        model=model,
        error=error,
    )
    
@app.route("/modules", methods=["GET", "POST"])
def modules_page():
    model = load_node_model()

    if request.method == "POST":
        modules = [
            "ModuleHelp",
            "ModuleParrot",
        ]

        echolink_enabled = request.form.get("module_echolink") == "yes"
        metar_enabled = request.form.get("module_metar") == "yes"

        if echolink_enabled:
            modules.append("ModuleEchoLink")

        if metar_enabled:
            modules.append("ModuleMetarInfo")

        model["modules"]["enabled"] = modules
        model["echolink"]["enabled"] = echolink_enabled
        model["metar"]["enabled"] = metar_enabled

        save_node_model(model)

        if echolink_enabled:
            return redirect(url_for("echolink_page"))

        if metar_enabled:
            return redirect(url_for("metar_default_page"))

        return_after_modules = model.get("build", {}).pop("return_after_modules", None)

        if return_after_modules:
            save_node_model(model)
            return redirect(url_for(return_after_modules))

        return_after_modules = model.get("build", {}).pop("return_after_modules", None)

        if return_after_modules:
            save_node_model(model)
            return redirect(url_for(return_after_modules))

        return redirect(url_for("reflector_page"))

    return render_template("modules.html", model=model)

@app.route("/echolink", methods=["GET", "POST"])
def echolink_page():
    model = load_node_model()
    error = None

    if request.method == "POST":
        callsign = request.form.get("echolink_callsign", "").strip().upper()
        password = request.form.get("echolink_password", "").strip()
        sysopname = request.form.get("echolink_sysopname", "").strip()
        location_text = request.form.get("echolink_location", "").strip()

        location = f"[Svx] {location_text}"

        if not callsign.endswith(("-L", "-R")):
            error = "EchoLink callsign must end in -L or -R."
        elif not password:
            error = "EchoLink password is required."
        elif not sysopname:
            error = "EchoLink sysop name is required."
        elif not location_text:
            error = "EchoLink location is required."
        elif len(location_text) > 12:
            error = "EchoLink location must be 12 characters or fewer after [Svx]."
        else:
            model["echolink"] = {
                "enabled": True,
                "callsign": callsign,
                "password": password,
                "sysopname": sysopname,
                "location": location,
            }

            save_node_model(model)

            if model["metar"]["enabled"]:
                return redirect(url_for("metar_default_page"))

            return redirect(url_for("reflector_page"))

    return render_template("echolink.html", model=model, error=error)

@app.route("/metar-default", methods=["GET", "POST"])
def metar_default_page():
    model = load_node_model()
    error = None

    if "metar" not in model:
        model["metar"] = {}

    region = model["metar"].get("region") or "ukwide"

    if region not in METAR_REGIONS:
        region = "ukwide"
        model["metar"]["region"] = region
        save_node_model(model)

    airports = dict(METAR_REGIONS[region])
    for code in [model["metar"].get("startdefault", ""), *model["metar"].get("airports", [])]:
        if code:
            airports.setdefault(code, "Configured airport")

    if request.method == "POST":
        startdefault = (request.form.get("custom_airport", "").strip() or request.form.get("startdefault", "")).strip().upper()

        if not startdefault:
            error = "Please select a default airport."
        elif len(startdefault) != 4 or not startdefault.isascii() or not startdefault.isalpha():
            error = "Enter a four-letter ICAO airport code, for example EDDG."
        else:
            model["metar"]["startdefault"] = startdefault
            save_node_model(model)
            return redirect(url_for("metar_airports_page"))

    return render_template(
        "metar_default.html",
        model=model,
        airports=airports,
        error=error,
        version_info=get_version_info(),
    )

@app.route("/metar-airports", methods=["GET", "POST"])
def metar_airports_page():
    model = load_node_model()
    error = None

    region = model["metar"].get("region", "ukwide")
    airports = dict(METAR_REGIONS.get(region, {}))
    for code in [model["metar"].get("startdefault", ""), *model["metar"].get("airports", [])]:
        if code:
            airports.setdefault(code, "Configured airport")

    startdefault = model["metar"].get("startdefault", "")

    if request.method == "POST":
        selected_airports = request.form.getlist("airports")

        if len(selected_airports) > 6:
            error = "Please select no more than 6 additional airports."
        else:
            model["metar"]["airports"] = selected_airports

            build = model.setdefault("build", {})

            return_after_metar = build.pop(
                "return_after_metar",
                None,
            )

            return_after_modules = build.pop(
                "return_after_modules",
                None,
            )

            save_node_model(model)

            if return_after_metar:
                return redirect(url_for(return_after_metar))

            if return_after_modules:
                return redirect(url_for(return_after_modules))

            return redirect(url_for("reflector_page"))
    return render_template(
        "metar_airports.html",
        model=model,
        airports=airports,
        startdefault=startdefault,
        error=error,
        version_info=get_version_info(),
    )
    
@app.route("/reflector", methods=["GET", "POST"])
def reflector_page():
    model = load_node_model()
    error = None

    reflectors = {
        "north_america": {
            "name": "North America",
            "host": "north.america.svxlink.net",
            "port": 35300,
            "url": "https://north.america.svxlink.net",
            "monitor_tgs": 3100,
        },
        "ukwide": {
            "name": "UKWide",
            "host": "uk.wide.svxlink.uk",
            "port": 35300,
            "url": "https://ukwide.svxlink.net",
            "monitor_tgs": 235,
        },
        "australia_nz": {
            "name": "Australia / New Zealand",
            "host": "australia.svxlink.net",
            "port": 35300,
            "url": "https://au.svxlink.net",
            "monitor_tgs": 505,
        },
        "yorkshire": {
            "name": "YorkshireNet Reflector",
            "host": "yorkshire.svxlink.uk",
            "port": 5310,
            "url": "https://svxlink.qsos.uk/",
            "monitor_tgs": 235,
        },
    }

    if request.method == "POST":
        connect = request.form.get("connect")

        if connect == "no":
            model["reflector"]["enabled"] = False
            model["reflector"]["name"] = None
            model["reflector"]["host"] = None
            model["reflector"]["port"] = None
            model["reflector"]["auth_key"] = None

            save_node_model(model)
            return redirect(next_after_reflector(model))

        reflector_id = request.form.get("reflector")
        password = request.form.get("password", "").strip()

        if reflector_id not in reflectors:
            error = "Please select a reflector."
        elif len(password) != 16:
            error = "Reflector password must be exactly 16 characters."
        else:
            selected = reflectors[reflector_id]

            model["reflector"]["enabled"] = True
            model["reflector"]["name"] = selected["name"]
            model["reflector"]["host"] = selected["host"]
            model["reflector"]["port"] = selected["port"]
            model["reflector"]["auth_key"] = password

            save_node_model(model)
            return redirect(next_after_reflector(model))

    return render_template(
        "reflector.html",
        model=model,
        reflectors=reflectors,
        error=error,
    )

@app.route("/node-info", methods=["GET", "POST"])
def node_info_page():

    model = load_node_model()

    if "node_info" not in model:
        model["node_info"] = {}

    node_info = model["node_info"]

    error = None

    if request.method == "POST":

        node_info["nodeLocation"] = request.form.get(
            "node_location",
            ""
        ).strip()

        node_info["qth_name"] = request.form.get(
            "qth_name",
            ""
        ).strip()

        node_info["sysop"] = request.form.get(
            "sysop",
            ""
        ).strip().upper()

        node_info["lat"] = request.form.get(
            "lat",
            ""
        ).strip()

        node_info["long"] = request.form.get(
            "long",
            ""
        ).strip()

        node_info["locator"] = request.form.get(
            "locator",
            ""
        ).strip().upper()

        node_info["lat_dms"] = request.form.get(
            "lat_dms",
            ""
        ).strip()

        node_info["long_dms"] = request.form.get(
            "long_dms",
            ""
        ).strip()

        node_info["rx_freq"] = request.form.get(
            "rx_freq",
            ""
        ).strip()

        node_info["tx_freq"] = request.form.get(
            "tx_freq",
            ""
        ).strip()

        node_info["tx_power"] = request.form.get(
            "tx_power",
            ""
        ).strip()

        node_info["antenna"] = request.form.get(
            "antenna",
            ""
        ).strip()

        node_info["antenna_height"] = request.form.get(
            "antenna_height",
            ""
        ).strip()

        node_info["antenna_direction"] = request.form.get(
            "antenna_direction",
            ""
        ).strip()

        save_node_model(model)

        return redirect(url_for("setup_auth_page"))

    return render_template(
        "node_info.html",
        node_info=node_info,
        error=error,
    )
## Wifi
@app.route("/wifi", methods=["GET", "POST"])
def wifi_page():
    screen = []
    ssid = ""
    password = ""

    if request.method == "POST":
        ssid = request.form.get("ssid", "").strip()
        password = request.form.get("password", "").strip()

        if "btnScan" in request.form:
            screen = wifi_scan()

        elif "btnConnList" in request.form:
            screen = connection_list()

        elif "btnWifiStatus" in request.form:
            screen = wifi_status()

        elif "btnWifiOn" in request.form:
            screen = wifi_on()

        elif "btnAdd" in request.form:
            screen = connect_wifi(ssid, password)

        elif "btnSwitch" in request.form:
            screen = switch_wifi(ssid)

        elif "btnDelete" in request.form:
            screen = delete_wifi(ssid)

        elif "btnHotspotStatus" in request.form:
            screen = hotspot_status()

        elif "btnStartHotspot" in request.form:
            screen = start_hotspot()

        elif "btnStopHotspot" in request.form:
            screen = stop_hotspot()

    return render_template(
        "wifi.html",
        screen=screen,
        ssid=ssid,
        password=password,
    )
## End Wifi
@app.route("/edit/node-info", methods=["GET", "POST"])
def node_info_edit_page():
    saved = request.args.get("saved") == "1"
    if not session.get("authorised"):
        return redirect(url_for("authorise_page", next=request.path))

    model = load_node_model()

    if "node_info" not in model:
        model["node_info"] = {}

    node_info = model["node_info"]
    error = None

    if request.method == "POST":

        node_info["nodeLocation"] = request.form.get("node_location", "").strip()
        node_info["qth_name"] = request.form.get("qth_name", "").strip()
        node_info["sysop"] = request.form.get("sysop", "").strip().upper()
        node_info["lat"] = request.form.get("lat", "").strip()
        node_info["long"] = request.form.get("long", "").strip()
        node_info["locator"] = request.form.get("locator", "").strip().upper()
        node_info["lat_dms"] = request.form.get("lat_dms", "").strip()
        node_info["long_dms"] = request.form.get("long_dms", "").strip()
        node_info["rx_freq"] = request.form.get("rx_freq", "").strip()
        node_info["tx_freq"] = request.form.get("tx_freq", "").strip()
        node_info["tx_power"] = request.form.get("tx_power", "").strip()
        node_info["antenna"] = request.form.get("antenna", "").strip()
        node_info["antenna_height"] = request.form.get("antenna_height", "").strip()
        node_info["antenna_direction"] = request.form.get("antenna_direction", "").strip()

        save_node_model(model)
        write_node_info_json(model)
        restart_svxlink()

        return redirect(url_for("node_info_edit_page",saved="1"))

    return render_template(
        "node_info_edit.html",
        node_info=node_info,
        error=error,
        saved=saved
    )
@app.route("/review", methods=["GET", "POST"])
def review_page():
    model = load_node_model()
    if not model.get("dashboard_auth", {}).get("password_hash"):
        return redirect(url_for("setup_auth_page"))
    if request.method == "POST":
        return redirect(url_for("build_page"))

    return render_template("review.html", model=model)


@app.route("/build", methods=["GET", "POST"])
def build_page():
    model = load_node_model()
    result = None

    hardware = model.get("hardware", {})

    enabled_ports = [
        str(port)
        for port in model.get("ports", {}).get("enabled", [])
    ]

    if not enabled_ports:
        enabled_ports = ["1"]

    is_multi_port = (
        hardware.get("family") == "ics"
        or len(enabled_ports) > 1
    )

    if request.method == "POST":
        result = build_svxlink_configuration(
            model,
            restart=True,
        )

        return render_template(
            "done.html",
            model=model,
            svxlink_status=result.get("service_status"),
            build_result=result,
            error=None if result.get("success") else "Build or launch failed.",
            is_multi_port=is_multi_port,
            version_info=get_version_info(),
        )

    return render_template(
        "build.html",
        model=model,
        build_result=result,
        is_multi_port=is_multi_port,
        version_info=get_version_info(),
    )

@app.route("/setup-auth", methods=["GET", "POST"])
def setup_auth_page():

    model = load_node_model()

    auth = model.get(
        "dashboard_auth",
        {}
    )

    error = None

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        if not username or not password:

            error = "Username and password are required."

        else:

            model["dashboard_auth"] = {
                "username": username,
                "password_hash": generate_password_hash(password),
            }

            save_node_model(model)
            session.permanent = True
            session["authorised"] = True 
            return redirect("/start")

    return render_template(
        "setup_auth.html",
        auth=auth,
        error=error,
    )

@app.route("/done", methods=["GET"])
def done():
    model = load_node_model()

    return render_template(
        "done.html",
        model=model,
        svxlink_status=svxlink_status(),
    )


@app.route("/launch", methods=["POST"])
def launch():
    model = load_node_model()

    write_node_info_json(model)

    result = build_svxlink_configuration(
        model,
        restart=True,
    )

    return render_template(
        "done.html",
        model=model,
        svxlink_status=result.get("service_status"),
        build_result=result,
        error=None if result.get("success") else "Build or launch failed.",
    )

@app.route("/status", methods=["GET"])
def status_page():
    model = load_node_model()

    system_info = get_system_info()

    enabled_ports = [
        str(port)
        for port in model.get("ports", {}).get("enabled", [])
    ]

    if not enabled_ports:
        enabled_ports = ["1"]

    selected_port = request.args.get("port", enabled_ports[0])

    if selected_port not in enabled_ports:
        selected_port = enabled_ports[0]

    status = get_runtime_status(
        model,
        selected_port=selected_port,
    )

    monitor_tgs = model.get(
        "reflector",
        {}
    ).get(
        "monitor_tgs",
        []
    )

    activity = get_reflector_activity()

    environment = model.get(
        "environment",
        {}
    ).get(
        "region",
        "british_isles"
    )

    talkgroups = load_talkgroups(environment)

    selected_node = model.get("nodes", {}).get(str(selected_port), {})

    port_modules = []

    if selected_node:
        selected_node_modules = selected_node.get("modules", {})

        if selected_node_modules.get("echolink"):
            port_modules.append("EchoLink")

        if selected_node_modules.get("metar"):
            port_modules.append("MetarInfo")

    else:
        enabled_modules = model.get("modules", {}).get("enabled", [])

        module_display_names = {
            "ModuleHelp": "Help",
            "ModuleParrot": "Parrot",
            "ModuleEchoLink": "EchoLink",
            "ModuleMetarInfo": "MetarInfo",
        }

        port_modules = [
            module_display_names.get(module, module.replace("Module", ""))
            for module in enabled_modules
        ]

    return render_template(
        "status.html",
        model=model,
        status=status,
        activity=activity,
        port_modules=port_modules,
        talkgroups=talkgroups,
        monitor_tgs=monitor_tgs,
        active_talkgroup=status.get("active_talkgroup"),
        system_info=system_info,
        enabled_ports=enabled_ports,
        selected_port=selected_port,
        port_count=len(enabled_ports),
        version_info=get_version_info(),
    )
@app.route("/sound-levels", methods=["GET", "POST"])
def sound_levels_page():
    result = None
    error = None

    if request.method == "POST":
        action = request.form.get("action", "").strip()

        try:
            if action == "baseline":
                card_index = int(request.form.get("card_index", "").strip())
                result = apply_safe_baseline(card_index)

            elif action == "set_slider":
                card_index = int(request.form.get("card_index", "").strip())
                numid = int(request.form.get("numid", "").strip())
                raw_value = int(request.form.get("raw_value", "").strip())

                result = set_slider_control(card_index, numid, raw_value)

            else:
                error = "Unknown sound-level action."

        except ValueError as exc:
            error = str(exc)

        except Exception as exc:
            error = f"Failed to update sound levels: {exc}"

    cards = discover_sound_cards()

    return render_template(
        "sound_levels.html",
        cards=cards,
        result=result,
        error=error,
    )

@app.route("/sound-calibration", methods=["GET", "POST"])
def sound_calibration_page():
    error = None
    result = None
    config_file = DEFAULT_SVXLINK_CONFIG
    devcal_values = {
        "mode": "txcal",
        "section": "",
        "modfqs": "1000",
        "caldev": "2405",
        "maxdev": "5000",
        "headroom": "6",
        "audiodev": "",
        "flat": False,
        "wide": False,
    }
    if request.method == "POST":
        action = request.form.get("action", "").strip()
        devcal_values["mode"] = request.form.get("mode", devcal_values["mode"]).strip()
        devcal_values["section"] = request.form.get("section", devcal_values["section"]).strip()
        devcal_values["modfqs"] = request.form.get("modfqs", devcal_values["modfqs"]).strip()
        devcal_values["caldev"] = request.form.get("caldev", devcal_values["caldev"]).strip()
        devcal_values["maxdev"] = request.form.get("maxdev", devcal_values["maxdev"]).strip()
        devcal_values["headroom"] = request.form.get("headroom", devcal_values["headroom"]).strip()
        devcal_values["audiodev"] = request.form.get("audiodev", devcal_values["audiodev"]).strip()
        devcal_values["flat"] = request.form.get("flat") == "on"
        devcal_values["wide"] = request.form.get("wide") == "on"
        try:
            if action == "stop_svxlink":
                result = stop_svxlink_for_calibration()

            elif action == "restart_svxlink":
                result = restart_svxlink_after_calibration()

            elif action == "start_devcal":
                config_file = request.form.get(
                    "config_file",
                    DEFAULT_SVXLINK_CONFIG
                ).strip()

                section = request.form.get("section", "").strip()
                mode = request.form.get("mode", "").strip()
                modfqs = request.form.get("modfqs", "1000.0").strip()
                caldev = request.form.get("caldev", "2404.8").strip()
                maxdev = request.form.get("maxdev", "5000").strip()
                headroom = request.form.get("headroom", "6").strip()
                audiodev = request.form.get("audiodev", "").strip()
                flat = request.form.get("flat") == "on"
                wide = request.form.get("wide") == "on"

                result = start_devcal_session(
                    config_file=config_file,
                    section=devcal_values["section"],
                    mode=devcal_values["mode"],
                    modfqs=devcal_values["modfqs"],
                    caldev=devcal_values["caldev"],
                    maxdev=devcal_values["maxdev"],
                    headroom=devcal_values["headroom"],
                    audiodev=devcal_values["audiodev"],
                    flat=devcal_values["flat"],
                    wide=devcal_values["wide"],
                )

            elif action == "toggle_devcal_tx":
                result = toggle_devcal_tx()

            elif action == "stop_devcal":
                result = stop_devcal_session()

            else:
                error = "Unknown calibration action."

        except Exception as exc:
            error = f"Calibration service action failed: {exc}"

    try:
        audio_sections = discover_audio_sections(config_file)
    except Exception as exc:
        audio_sections = {
            "config_file": config_file,
            "rx_sections": [],
            "tx_sections": [],
        }

        if not error:
            error = f"Could not read SvxLink audio sections: {exc}"

    svxlink_state = get_svxlink_service_state()

    return render_template(
        "sound_calibration.html",
        audio_sections=audio_sections,
        svxlink_state=svxlink_state,
        error=error,
        result=result,
        devcal_running=devcal_is_running(),
        devcal_mode=get_devcal_mode(),
        devcal_tx_state=get_devcal_tx_state(),
        devcal_output=get_devcal_output(),
        devcal_values=devcal_values,
    )

@app.route("/authorise", methods=["GET", "POST"])
def authorise_page():
    error = None
    next_page = request.args.get("next", "")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        next_page = request.form.get("next", "").strip()

        auth = load_node_model().get(
            "dashboard_auth",
            {}
        )

        stored_user = auth.get("username", "")
        stored_hash = auth.get("password_hash", "")

        if (
            username == stored_user
            and stored_hash
            and check_password_hash(stored_hash, password)
        ):
            session.clear()
            session.permanent = True
            session["authorised"] = True

            if next_page and next_page.startswith("/") and not next_page.startswith("//"):
                return redirect(next_page)

            return redirect(url_for("status_page"))

        error = "Incorrect username or password."

    return render_template(
        "authorise.html",
        error=error,
        next_page=next_page,
    )
@app.route("/api/status", methods=["GET"])
def api_status_page():
    model = load_node_model()

    enabled_ports = [
        str(port)
        for port in model.get("ports", {}).get("enabled", [])
    ]

    if not enabled_ports:
        enabled_ports = ["1"]

    selected_port = request.args.get(
        "port",
        enabled_ports[0]
    )

    if selected_port not in enabled_ports:
        selected_port = enabled_ports[0]

    status = get_runtime_status(
        model,
        selected_port=selected_port,
    )

    activity = get_reflector_activity()
    system_info = get_system_info()

    return jsonify({
        "status": status,
        "activity": activity,
        "system_info": system_info,
        "enabled_ports": enabled_ports,
        "selected_port": selected_port,
        "port_count": len(enabled_ports),
    })
@app.route("/talkgroups", methods=["GET", "POST"])
def talkgroups_page():
    saved = request.args.get("saved")
    if not session.get("authorised"):
        return redirect(url_for("authorise_page", next=request.path))    
    model = load_node_model()
        

    environment = model.get(
        "environment",
        {}
    ).get(
        "region",
        "british_isles"
    )

    talkgroups = load_talkgroups(environment)

    if request.method == "POST":
        updated = []

        for index in range(len(talkgroups)):
            tg_id = request.form.get(f"id_{index}", "").strip()
            label = request.form.get(f"label_{index}", "").strip()
            colour = request.form.get(f"colour_{index}", "").strip()
            command = request.form.get(f"command_{index}", "").strip()

            if tg_id and label and colour and command:
                updated.append({
                    "id": tg_id,
                    "label": label,
                    "colour": colour,
                    "command": command,
                })

        save_talkgroups(environment, updated)

        return redirect(url_for("talkgroups_page", saved="1"))

    return render_template(
        "talkgroups.html",
        model=model,
        talkgroups=talkgroups,
        saved=saved,
    )
@app.route("/monitor-tgs", methods=["GET", "POST"])
def monitor_tgs_page():
    saved = request.args.get("saved")
    if not session.get("authorised"):
        return redirect(url_for("authorise_page", next=request.path))
    model = load_node_model()
    error = None

    if "reflector" not in model:
        model["reflector"] = {}

    existing = model["reflector"].get("monitor_tg_defs", [])
    selected = model["reflector"].get("monitor_tgs", [])

    monitor_rows = []

    for index in range(6):
        row = existing[index] if index < len(existing) else {}

        tg_id = row.get("id", "")
        label = row.get("label", "")

        monitor_rows.append({
            "id": tg_id,
            "label": label,
            "enabled": tg_id in selected,
        })

    if request.method == "POST":
        updated_defs = []
        updated_selected = []

        for index in range(6):
            tg_id = request.form.get(f"id_{index}", "").strip()
            label = request.form.get(f"label_{index}", "").strip()
            enabled = request.form.get(f"enabled_{index}") == "yes"

            if tg_id or label:
                updated_defs.append({
                    "id": tg_id,
                    "label": label,
                })

            if enabled and tg_id:
                updated_selected.append(tg_id)

        if len(updated_selected) > 6:
            error = "Please select no more than six monitoring talkgroups."
        else:
            model["reflector"]["monitor_tg_defs"] = updated_defs
            model["reflector"]["monitor_tgs"] = updated_selected

        save_node_model(model)

        result = build_svxlink_configuration(
            model,
            restart=True,
        )

        if not result.get("success"):
            error = "Monitoring talkgroups saved, but SvxLink rebuild/restart failed."
        else:
            return redirect(url_for("monitor_tgs_page", saved="1"))

    return render_template(
        "monitor_tgs.html",
        model=model,
        monitor_rows=monitor_rows,
        saved=saved,
        error=error,
    )
@app.route("/edit/echolink", methods=["GET", "POST"])
def echolink_edit_page():
    saved = request.args.get("saved")
    if not session.get("authorised"):
        return redirect(url_for("authorise_page", next=request.path))

    model = load_node_model()

    if "echolink" not in model:
        model["echolink"] = {}

    echolink = model["echolink"]

    error = None

    if request.method == "POST":

        echolink["enabled"] = (
            request.form.get("enabled") == "yes"
        )

        echolink["callsign"] = request.form.get(
            "callsign",
            ""
        ).strip().upper()

        echolink["password"] = request.form.get(
            "password",
            ""
        ).strip()

        echolink["sysopname"] = request.form.get(
            "sysopname",
            ""
        ).strip()

        echolink["location"] = request.form.get(
            "location",
            ""
        ).strip()

        save_node_model(model)
        echolink_conf = render_echolink_module(model)

        if echolink_conf:
            write_text_file(
                MODULE_DIR / "ModuleEchoLink.conf",
                echolink_conf
            )
    
        restart_svxlink()
    
        return redirect(
            url_for(
        "echolink_edit_page",
        saved="1"
    )
)
    
    return render_template(
                "echolink_edit.html",
                echolink=echolink,
                error=error,
                saved=saved
    )
@app.route("/edit/metar", methods=["GET", "POST"])
def metar_edit_page():
    saved = request.args.get("saved")
    if not session.get("authorised"):
        return redirect(url_for("authorise_page", next=request.path))

    model = load_node_model()

    if "metar" not in model:
        model["metar"] = {}

    metar = model["metar"]

    error = None

    if request.method == "POST":

        metar["enabled"] = (
            request.form.get("enabled") == "yes"
        )

        metar["startdefault"] = request.form.get(
            "startdefault",
            ""
        ).strip().upper()

        airports = request.form.get(
            "airports",
            ""
        )

        metar["airports"] = [
            x.strip().upper()
            for x in airports.split(",")
            if x.strip()
        ][:6]

        if "modules" not in model:
            model["modules"] = {"enabled": []}

        if "enabled" not in model["modules"]:
            model["modules"]["enabled"] = []

        if metar["enabled"]:
            if "ModuleMetarInfo" not in model["modules"]["enabled"]:
                model["modules"]["enabled"].append("ModuleMetarInfo")
        else:
            if "ModuleMetarInfo" in model["modules"]["enabled"]:
                model["modules"]["enabled"].remove("ModuleMetarInfo")

        save_node_model(model)

        result = build_svxlink_configuration(
            model,
            restart=True,
        )

        if result["validation_errors"] or result["platform_errors"] or result["deployment_errors"]:
            error = "; ".join(
                result["validation_errors"]
                + result["platform_errors"]
                + result["deployment_errors"]
            )

            return render_template(
                "metar_edit.html",
                metar=metar,
                error=error,
                saved=False,
            )

        return redirect(url_for("metar_edit_page", saved="1"))

    return render_template(
        "metar_edit.html",
        metar=metar,
        error=error,
        saved=saved
    )
@app.route("/log", methods=["GET"])
def log_page():

    if not session.get("authorised"):
        return redirect(url_for("authorise_page", next=request.path))

    log_file = get_svxlink_log_path()

    log_lines = []

    try:
        if log_file.exists():

            lines = log_file.read_text(
                encoding="utf-8",
                errors="ignore",
            ).splitlines()

            log_lines = lines[-250:]

    except Exception as exc:

        log_lines = [
            f"Failed to read log: {exc}"
        ]

    return render_template(
        "log.html",
        log_lines=log_lines,
    )
@app.route("/log-data", methods=["GET"])
def log_data():

    if not session.get("authorised"):
        return ""

    log_file = get_svxlink_log_path()

    try:

        if log_file.exists():

            lines = log_file.read_text(
                encoding="utf-8",
                errors="ignore",
            ).splitlines()

            return "\n".join(lines[-250:])

    except Exception as exc:

        return f"Failed to read log: {exc}"

    return ""

@app.route("/maintenance", strict_slashes=False)
def maintenance_page():

    if not session.get("authorised"):
        return redirect(url_for("authorise_page", next=request.path))

    return render_template(
        "maintenance.html"
    )
@app.route("/reconfigure", methods=["GET", "POST"])
def reconfigure_page():
    model = load_node_model()

    hardware = model.get("hardware", {})
    nodes = model.get("nodes", {})

    enabled_ports = [
        str(port)
        for port in model.get("ports", {}).get("enabled", [])
    ]

    if not enabled_ports:
        enabled_ports = ["1"]

    is_multi_port = (
        hardware.get("family") == "ics"
        or len(enabled_ports) > 1
    )

    reconfigure_targets = [
        {
            "id": "environment",
            "label": "Environment / Region",
            "route": "environment_page",
            "description": "Change the region/environment settings. The hardware platform is preserved.",
        },
        {
            "id": "timezone",
            "label": "Timezone",
            "route": "timezone_page",
            "description": "Change the configured timezone.",
        },
    ]

    if is_multi_port:
        reconfigure_targets.extend([
            {
                "id": "hardware_ports",
                "label": "Enabled Hardware Ports",
                "route": "hardware_ports_page",
                "description": "Change which hardware ports are enabled for this build.",
            },
            {
                "id": "port_roles",
                "label": "Port Roles",
                "route": "port_roles_page",
                "description": "Change whether each enabled port is simplex or repeater.",
            },
            {
                "id": "port_config",
                "label": "Port Configuration Menu",
                "route": "port_config_page",
                "description": "Return to the multi-port configuration menu.",
            },
            {
                "id": "port_final_review",
                "label": "Multi-port Final Review",
                "route": "port_final_review_page",
                "description": "Review the current multi-port model before rebuilding.",
            },
        ])


    else:
        reconfigure_targets.extend([
            {
                "id": "node",
                "label": "Node Details",
                "route": "node_page",
                "description": "Change callsign, node type, location, and related node identity settings.",
            },
            {
                "id": "interface",
                "label": "Radio Interface",
                "route": "interface_page",
                "description": "Change radio interface settings.",
            },
            {
                "id": "squelch",
                "label": "Squelch / COS",
                "route": "squelch_page",
                "description": "Change squelch, COS, or CTCSS settings.",
            },
            {
                "id": "ident",
                "label": "Ident",
                "route": "ident_page",
                "description": "Change ident settings.",
            },
            {
                "id": "cw",
                "label": "CW Settings",
                "route": "cw_page",
                "description": "Change CW pitch, speed, and level, then go directly to Build Configuration.",
                "route_args": {"mode": "reconfigure"},
            },
            {
                "id": "courtesy",
                "label": "Courtesy Tones",
                "route": "courtesy_page",
                "description": "Change courtesy tone settings.",
            },
        ])

        if model.get("node", {}).get("type") == "repeater":
            reconfigure_targets.append({
                "id": "repeater",
                "label": "Repeater Settings",
                "route": "repeater_page",
                "description": "Change repeater timing and behaviour settings.",
            })

        reconfigure_targets.append({
            "id": "review",
            "label": "Review Configuration",
            "route": "review_page",
            "description": "Review the current model before rebuilding.",
        })

    reconfigure_targets.extend([
        {
            "id": "metar",
            "label": "METAR airports (ICAO codes)",
            "route": "metar_edit_page",
            "description": "Edit the default and additional airports directly using ICAO codes, without the setup wizard.",
        },
        {
            "id": "build",
            "label": "Build Configuration",
            "route": "build_page",
            "description": "Regenerate the active SvxLink configuration.",
        },
        {
            "id": "full_reset",
            "label": "Full Reset and Start Again",
            "route": "reconfigure_reset_page",
            "description": "Archive the current node model and restart the setup wizard.",
        },
    ])

    if request.method == "POST":
        target_id = request.form.get("target", "").strip()

        for target in reconfigure_targets:
            if target["id"] == target_id:
                route_args = target.get("route_args", {})

                return redirect(
                    url_for(
                        target["route"],
                        **route_args,
                    )
                )

        return render_template(
            "reconfigure.html",
            reconfigure_targets=reconfigure_targets,
            is_multi_port=is_multi_port,
            enabled_ports=enabled_ports,
            error="Please select a valid reconfiguration option.",
            version_info=get_version_info(),
        )

    return render_template(
        "reconfigure.html",
        reconfigure_targets=reconfigure_targets,
        is_multi_port=is_multi_port,
        enabled_ports=enabled_ports,
        error=None,
        version_info=get_version_info(),
    )
@app.route("/maintenance/restart", methods=["POST"], strict_slashes=False)
def restart_services_page():

    if not session.get("authorised"):
        return redirect(url_for("authorise_page", next=request.path))

    try:
        restart_svxlink()
    except Exception:
        app.logger.exception("Maintenance SvxLink restart failed")
        return render_template(
            "message.html",
            title="Restart Failed",
            message="SvxLink could not be restarted. Check the service log."
        ), 500

    return render_template(
        "message.html",
        title="Restart Requested",
        message="The SvxLink restart command completed. Check its status on the dashboard."
    )

@app.route("/maintenance/reboot", methods=["POST"])
def reboot_device_page():

    if not session.get("authorised"):
        return redirect(url_for("authorise_page", next=request.path))

    reboot_device()

    return render_template(
        "message.html",
        title="Reboot Requested",
        message="The device is rebooting."
    )
@app.route("/maintenance/shutdown", methods=["POST"])
def shutdown_device_page():

    if not session.get("authorised"):
        return redirect(url_for("authorise_page", next=request.path))

    shutdown_device()

    return render_template(
        "message.html",
        title="Shutdown Requested",
        message="The device is shutting down."
    )

@app.route("/logout", methods=["GET"])
def logout_page():
    session.pop("authorised", None)
    return redirect(url_for("status_page"))

@app.route("/dtmf", methods=["POST"])
def dtmf_page():
    command = request.form.get("command", "").strip()


    try:
        send_dtmf(command)

    except Exception as exc:
        print(f"DTMF send failed: {exc}")
        return redirect(url_for("status_page"))

    return redirect(url_for("status_page"))
    
from pi3twe.routes import register as register_pi3twe
register_pi3twe(app)

if __name__ == "__main__":
    ensure_dirs()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )
