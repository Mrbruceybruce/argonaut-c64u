# SPDX-License-Identifier: GPL-3.0-or-later
"""Small GTK presentation conventions; call on the GTK main thread.

Use native heading/title classes for headings, dim-label for supporting metadata
(never essential warnings), and selectable normal labels for technical identifiers.
Ordinary buttons remain native; suggested-action/destructive-action are explicit
call-site choices, never inferred from text. Prefer widget layout properties and
4/8/12/16 logical-pixel spacing for new work, without rewriting existing layouts.
Ordinary symbolic icons may use 16 logical pixels; preserve the branded 24-pixel
Ultimate Power artwork. Do not override native focus, selection or disabled states.
"""
from gi.repository import Gtk
from .diagnostics import diagnostic_event


APPLICATION_CSS = (
    b'.argonaut-file-pane { border: 2px solid transparent; border-radius: 6px; padding: 4px; }\n'
    b'.argonaut-file-pane-active { border-color: alpha(@theme_selected_bg_color, 0.55); }\n'
    b'.argonaut-error-message { color: #c01c28; font-size: 1.083333em; }')

# Keep the display wrapper alive while its provider is registered. A weak-key
# cache could disappear while the native display still owns the provider.
_providers = {}


def _parsing_error(_provider, _section, _error):
    # Report the failure without logging CSS contents or arbitrary parser prose.
    diagnostic_event('gtk', 'application_css', 'style_provider', 'error',
                     error_kind='css-parse')


def _display_closed(display, _is_error):
    provider = _providers.pop(display, None)
    if provider is not None:
        Gtk.StyleContext.remove_provider_for_display(display, provider)


def install_styles(display):
    """Return the single application provider for an open GTK display."""
    if display.is_closed():
        raise ValueError('Cannot install styles on a closed display')
    if display in _providers:
        return _providers[display]
    provider = Gtk.CssProvider()
    provider.connect('parsing-error', _parsing_error)
    provider.load_from_data(APPLICATION_CSS)
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    display.connect('closed', _display_closed)
    _providers[display] = provider
    return provider


def set_error(label, failed):
    """Set an explicit label error state without changing text or sensitivity."""
    change = label.add_css_class if failed else label.remove_css_class
    change('error')
    change('argonaut-error-message')
