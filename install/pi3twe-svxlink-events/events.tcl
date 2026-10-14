# SPDX-License-Identifier: GPL-2.0-or-later
# SvxLink 26.05 may load CW.tcl before Logic.tcl. Create its namespace first.
namespace eval Logic {}
set script_path /usr/share/svxlink/events.tcl
# Pi3tweLogic inherits RepeaterLogic and uses its standard event handlers.
if {$::logic_type eq "Pi3twe"} { set ::logic_type "Repeater" }
source $script_path
namespace eval ${::logic_name}::Pi3twe { variable news_file "" }
proc RepeaterLogic::pi3twe_news {} {
    variable Pi3twe::news_file
    playFile $news_file
}
proc RepeaterLogic::pi3twe_policy {minutes} {
    set ::Logic::short_ident_interval $minutes
    set ::Logic::long_ident_interval $minutes
}

# Use the configured repeater ID. Message audio is queued only to local TX.
proc RepeaterLogic::pi3twe_call {} {
    Logic::send_short_ident
    set ::Logic::prev_ident [clock seconds]
}
