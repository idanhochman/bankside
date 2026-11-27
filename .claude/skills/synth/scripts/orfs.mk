# Flow settings every module shares (the synth skill). A module that needs
# different ones sets them in its own syn/orfs.mk, which is read first; these
# are defaults (?=), so the module's win.
export PLATFORM         = asap7
export CORE_UTILIZATION ?= 40
export PLACE_DENSITY    ?= 0.60
