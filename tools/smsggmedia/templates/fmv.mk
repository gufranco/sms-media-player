FMV_CALLER_GOAL := $(.DEFAULT_GOAL)
FMV_DIR ?= fmv
FMV_BUILD ?= build/fmv
FMV_FIRST_BANK ?= 2
FMV_C_SOURCES := mediaplayer screen assert seek
FMV_ASM_SOURCES := replay psg vdp
FMV_OBJECTS := $(FMV_C_SOURCES:%=$(FMV_BUILD)/%.rel) $(FMV_ASM_SOURCES:%=$(FMV_BUILD)/%.rel)
FMV_ASSETS := $(FMV_BUILD)/assets
FMV_ASSET_HDR := $(FMV_ASSETS)/assets.h
FMV_INCLUDES := -I$(FMV_DIR)/include -I$(FMV_DIR)/movie -I$(FMV_ASSETS)
FMV_SDCC_FLAGS := -mz80 --sdcccall 1 --std-c23 $(FMV_INCLUDES) -I$(SMSLIB)/src

$(FMV_ASSET_HDR): $(FMV_DIR)/movie/assets/movie.bin
	rm -rf $(FMV_ASSETS)
	mkdir -p $(FMV_ASSETS)
	cd $(FMV_ASSETS) && assets2banks $(abspath $(FMV_DIR)/movie/assets) \
	    --firstbank=$(FMV_FIRST_BANK) --singleheader=assets.h --compile --allowsplitting

$(FMV_BUILD)/%.rel: $(FMV_DIR)/src/%.c $(FMV_ASSET_HDR)
	mkdir -p $(FMV_BUILD)
	sdcc $(FMV_SDCC_FLAGS) -c $< -o $@

$(FMV_BUILD)/%.rel: $(FMV_DIR)/src/%.s
	mkdir -p $(FMV_BUILD)
	sdasz80 -l -I$(FMV_DIR)/src -o $@ $<

FMV_BANK_NUMS = $(shell ls $(FMV_ASSETS)/bank*.rel 2>/dev/null \
                        | sed 's#.*/bank##; s#\.rel##' | sort -n)
FMV_BANK_RELS = $(foreach n,$(FMV_BANK_NUMS),$(FMV_ASSETS)/bank$(n).rel)
FMV_BANK_FLAGS = $(foreach n,$(FMV_BANK_NUMS),-Wl-b_BANK$(n)=0x8000)

.DEFAULT_GOAL := $(FMV_CALLER_GOAL)
