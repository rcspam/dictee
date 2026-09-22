#!/usr/bin/env bash
# Should dictee mute the playback while recording from the microphone?
#
# It always did, to keep the speakers out of the microphone. On headphones
# there is nothing to keep out and the music stopped for nothing (#37).
# DICTEE_MUTE_OUTPUT now decides: auto (mute unless the active output is a
# headset), true (always), false (never).
#
# Extracts _should_mute_output() from the dictee script and feeds it the
# `pactl list sinks` output of real devices: the built-in jack on speakers,
# Bose Sport Earbuds over Bluetooth, an HK Onyx Studio 4 speaker over
# Bluetooth, and a sink whose port carries no usable type.
#
# Usage: bash tests/test-mute-output.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/dictee"

fn=$(awk '/^_sink_is_headset\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$SCRIPT")
[[ -n "$fn" ]] || { echo "FAIL: _sink_is_headset() not found in $SCRIPT"; exit 1; }
eval "$fn"
fn2=$(awk '/^_should_mute_output\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$SCRIPT")
[[ -n "$fn2" ]] || { echo "FAIL: _should_mute_output() not found in $SCRIPT"; exit 1; }
eval "$fn2"

fails=0
check() {  # label, got, expected
    if [[ "$2" == "$3" ]]; then echo "PASS $1"; else echo "FAIL $1: got '$2', expected '$3'"; fails=$((fails+1)); fi
}

# --- recorded `pactl list sinks` fragments (LC_ALL=C), one per device --------

JACK_SPEAKERS='Sink #59
	Name: alsa_output.pci-0000_00_1f.3.analog-stereo
	Description: Built-in Audio Analog Stereo
		device.form_factor = "internal"
	Ports:
		analog-output-speaker: Speakers (type: Speaker, priority: 10000, availability unknown)
		analog-output-headphones: Headphones (type: Headphones, priority: 9900, not available)
	Active Port: analog-output-speaker'

JACK_HEADPHONES='Sink #59
	Name: alsa_output.pci-0000_00_1f.3.analog-stereo
	Description: Built-in Audio Analog Stereo
		device.form_factor = "internal"
	Ports:
		analog-output-speaker: Speakers (type: Speaker, priority: 10000, availability unknown)
		analog-output-headphones: Headphones (type: Headphones, priority: 9900, available)
	Active Port: analog-output-headphones'

BT_EARBUDS='Sink #300043
	Name: bluez_output.60_AB_D2_9B_99_21.1
	Description: Bose Sport Earbuds
		device.bus = "bluetooth"
		device.form_factor = "headphone"
		device.icon_name = "audio-headphones-bluetooth"
	Ports:
		headphone-output: Headphone (type: Headphones, priority: 0, available)
	Active Port: headphone-output'

BT_SPEAKER='Sink #300168
	Name: bluez_output.04_FE_A1_D4_86_B8.1
	Description: HK Onyx Studio 4 D
		device.bus = "bluetooth"
		device.form_factor = "speaker"
		device.icon_name = "audio-speakers-bluetooth"
	Ports:
		speaker-output: Speaker (type: Speaker, priority: 0, available)
	Active Port: speaker-output'

# A USB interface (the SSL 2 of #37): one nameless port, no type, no form factor.
NO_TYPE='Sink #71
	Name: alsa_output.usb-Solid_State_Logic_SSL_2-00.analog-stereo
	Description: SSL 2 Analog Stereo
	Ports:
		analog-output: Analog Output (type: Analog, priority: 9900, availability unknown)
	Active Port: analog-output'

HEADSET_TYPE='Sink #77
	Name: bluez_output.AA_BB_CC_DD_EE_FF.1
	Description: Jabra Evolve
	Ports:
		headset-output: Headset (type: Headset, priority: 0, available)
	Active Port: headset-output'

# --- _sink_is_headset: reads the sink description on stdin ------------------

check "jack on speakers is not a headset"      "$(printf '%s' "$JACK_SPEAKERS"    | _sink_is_headset)" "no"
check "jack on headphones is a headset"        "$(printf '%s' "$JACK_HEADPHONES"  | _sink_is_headset)" "yes"
check "bluetooth earbuds are a headset"        "$(printf '%s' "$BT_EARBUDS"       | _sink_is_headset)" "yes"
check "bluetooth speaker is not a headset"     "$(printf '%s' "$BT_SPEAKER"       | _sink_is_headset)" "no"
check "headset port type counts too"           "$(printf '%s' "$HEADSET_TYPE"     | _sink_is_headset)" "yes"
check "no usable type: not a headset"          "$(printf '%s' "$NO_TYPE"          | _sink_is_headset)" "no"
check "empty input: not a headset"             "$(printf '' | _sink_is_headset)" "no"

# --- _should_mute_output: setting + headset answer --------------------------

check "auto + speakers: mute"        "$(_should_mute_output auto  no)"  "yes"
check "auto + headset: no mute"      "$(_should_mute_output auto  yes)" "no"
check "unset behaves as auto"        "$(_should_mute_output ''    yes)" "no"
check "true + headset: mute anyway"  "$(_should_mute_output true  yes)" "yes"
check "true + speakers: mute"        "$(_should_mute_output true  no)"  "yes"
check "false + speakers: no mute"    "$(_should_mute_output false no)"  "no"
check "false + headset: no mute"     "$(_should_mute_output false yes)" "no"
check "garbage value behaves as auto" "$(_should_mute_output banana no)" "yes"

# --- _duck_target: ceiling, not percentage ----------------------------------
# DICTEE_DUCK_LEVEL empty keeps the historical mute. Set to a number, the
# output is capped at that percentage while recording and left alone when it
# is already lower, so a user at 19% does not end up at 4%.

fn3=$(awk '/^_duck_target\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$SCRIPT")
[[ -n "$fn3" ]] || { echo "FAIL: _duck_target() not found in $SCRIPT"; exit 1; }
eval "$fn3"

check "no duck level: mute as before"      "$(_duck_target ''    0.50)" "mute"
check "level above current: nothing to do" "$(_duck_target 10    0.05)" "keep"
check "level equal to current: nothing"    "$(_duck_target 10    0.10)" "keep"
check "level below current: cap"           "$(_duck_target 10    0.50)" "10"
check "level 0 is a mute"                  "$(_duck_target 0     0.50)" "mute"
check "level 100 never caps"               "$(_duck_target 100   0.50)" "keep"
check "garbage level: mute as before"      "$(_duck_target abc   0.50)" "mute"
check "negative level: mute as before"     "$(_duck_target -5    0.50)" "mute"
check "level over 100: mute as before"     "$(_duck_target 150   0.50)" "mute"
check "unreadable volume: cap anyway"      "$(_duck_target 10    '')"   "10"

# --- _pct_to_fraction: what wpctl is actually given -------------------------
# "0.$level" would send 0.5 for a level of 5, i.e. 50%: the opposite of what
# was asked. And a comma decimal separator makes wpctl set the volume to 0.

fn4=$(awk '/^_pct_to_fraction\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$SCRIPT")
[[ -n "$fn4" ]] || { echo "FAIL: _pct_to_fraction() not found in $SCRIPT"; exit 1; }
eval "$fn4"

check "10% is 0.10"  "$(_pct_to_fraction 10)" "0.10"
check "5% is 0.05"   "$(_pct_to_fraction 5)"  "0.05"
check "1% is 0.01"   "$(_pct_to_fraction 1)"  "0.01"
check "99% is 0.99"  "$(_pct_to_fraction 99)" "0.99"
check "a dot even in a comma locale" "$(LC_ALL=fr_FR.UTF-8 _pct_to_fraction 10)" "0.10"

# --- on a headset, its own level ---------------------------------------------
# A headset has nothing to keep out of the recording, so auto leaves it alone.
# DICTEE_DUCK_LEVEL_HEADSET lowers it anyway for those who want to keep hearing
# a call at a lower volume. Empty means untouched; it never mutes.

fn5=$(awk '/^_output_action\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$SCRIPT")
[[ -n "$fn5" ]] || { echo "FAIL: _output_action() not found in $SCRIPT"; exit 1; }
eval "$fn5"

# args: setting, is_headset, duck level, headset level, current volume
check "speakers, auto, no level: mute"        "$(_output_action auto  no  ''  ''  0.50)" "mute"
check "speakers, auto, level 10: cap"         "$(_output_action auto  no  10  ''  0.50)" "10"
check "headset, auto, no headset level: keep" "$(_output_action auto  yes 10  ''  0.50)" "keep"
check "headset, auto, headset level 30: cap"  "$(_output_action auto  yes 10  30  0.50)" "30"
check "an explicit 0 mutes the headset too"   "$(_output_action auto  yes ''  0   0.50)" "mute"
check "100 on a headset leaves it alone"      "$(_output_action auto  yes ''  100 0.50)" "keep"
check "100 on speakers leaves them alone"     "$(_output_action auto  no   100 ''  0.50)" "keep"
check "headset already below its level"       "$(_output_action auto  yes ''  30  0.20)" "keep"
check "headset wins over the speaker level in always mode" \
      "$(_output_action true  yes 10  30  0.50)" "30"
check "always on a headset without its level: the speaker level applies" \
      "$(_output_action true  yes 10  ''  0.50)" "10"
check "always on a headset, no level at all: mute" \
      "$(_output_action true  yes ''  ''  0.50)" "mute"
check "never: nothing, whatever the levels"   "$(_output_action false no  10  30  0.50)" "keep"
check "speakers ignore the headset level"     "$(_output_action auto  no  ''  30  0.50)" "mute"

if [[ $fails -gt 0 ]]; then echo "$fails FAILED"; exit 1; fi
echo OK
