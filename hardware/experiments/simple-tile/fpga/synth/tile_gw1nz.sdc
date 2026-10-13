# SPDX-License-Identifier: CERN-OHL-S-2.0
# Interior-only constraint sketch for the GW1NZ tile candidate.
# SCOPE LIMITATION (not full timing sign-off): these declare clocks and
# explicitly mark the async crossings as out of scope for STA; the external
# interface (board flight times, controller drive/return budget, latch
# recovery vs the scan cadence) is NOT constrained here and remains open
# (docs/clock_domains.md, ../../logic/timing/timing.json).

# board shift clock: pin -> fabric FFs (acceptance cadence 20 MHz nominal;
# the tile will also run slower)
create_clock -name shift_clk -period 50.0 [get_ports clk_pin]

# latch legs clock the shadow in SNAP_MODE=fall and async-clear the shift
# domain; declare them as clocks so NEXTPNR can report the latch domain:
create_clock -name latch_b -period 100000.0 [get_ports b_latch_pin]
create_clock -name latch_r -period 100000.0 [get_ports r_latch_pin]

# set_clock_groups is NOT supported by this nextpnr's SDC subset (probe
# recorded in results/logs/gw1nz_sdc.log); the latch<->shift-clock crossing
# (async clear / shadow->shreg first load) is therefore declared here in text
# and deliberately NOT closed by STA: it is covered by the documented
# quasi-static contract in docs/clock_domains.md, not by timing closure.
