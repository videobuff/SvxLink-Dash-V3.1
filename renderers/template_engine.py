#!/usr/bin/env python3

"""
Simple template engine for SvxLink-Dash-V3.1.

Purpose:
- load framework-owned config templates
- replace explicit placeholders
- return rendered text

This module contains no SvxLink policy.
"""

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
CONFIG_TEMPLATE_DIR = APP_ROOT / "templates" / "config"


class TemplateRenderError(Exception):
    """
    Raised when a template cannot be rendered safely.
    """


def load_template(template_name):
    """
    Load a template from templates/config/.
    """

    template_path = CONFIG_TEMPLATE_DIR / template_name

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    return template_path.read_text(encoding="utf-8")


def render_template_text(template_text, values):
    """
    Replace {{PLACEHOLDER}} markers with supplied values.

    values example:
        {
            "CALLSIGN": "G7ABC",
            "LOGICS": "SimplexLogic",
        }
    """

    rendered = template_text

    for key, value in values.items():
        marker = "{{" + key + "}}"
        rendered = rendered.replace(marker, str(value))

    return rendered


def assert_no_unresolved_markers(rendered_text):
    """
    Prevent accidentally writing config files with unresolved markers.
    """

    if "{{" in rendered_text or "}}" in rendered_text:
        raise TemplateRenderError(
            "Rendered template still contains unresolved markers."
        )


def render_config_template(template_name, values):
    """
    Load and render a named config template.
    """

    template_text = load_template(template_name)
    rendered = render_template_text(template_text, values)

    assert_no_unresolved_markers(rendered)

    return rendered