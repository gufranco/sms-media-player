PROJECT      := sms-media-player
ROM          := build/$(PROJECT).sms
DOCKER_IMAGE := $(PROJECT)-toolchain
DOCKER_USER  := $(shell id -u):$(shell id -g)

SRC_DIR      := src
INC_DIR      := include
ASSET_DIR    := assets
BUILD_DIR    := build
ASSET_OUT    := $(BUILD_DIR)/assets
GEN_DIR      := $(BUILD_DIR)/generated
ASSET_FILES  := $(wildcard $(ASSET_DIR)/*)
ASSET_HDR    := $(ASSET_OUT)/assets.h
HEADERS      := $(wildcard $(INC_DIR)/fmv/*.h)
VERSION_HDR  := $(GEN_DIR)/version_numbers.h

SDCC         := sdcc
SDCC_STD     := --std-c23
SDCC_ARCH    := -mz80 --sdcccall 1 --no-std-crt0 --data-loc 0xC000
SDCC_WARN    := --Werror --max-allocs-per-node 50000
SDCC_INC     := -I$(INC_DIR) -I$(GEN_DIR) -I$(SMSLIB)/src
SDCC_FLAGS   := $(SDCC_ARCH) $(SDCC_STD) $(SDCC_WARN) $(SDCC_INC)

SOURCES      := $(wildcard $(SRC_DIR)/*.c)
ASM_SOURCES  := $(wildcard $(SRC_DIR)/*.s)
OBJECTS      := $(patsubst $(SRC_DIR)/%.c,$(BUILD_DIR)/%.rel,$(SOURCES)) \
                $(patsubst $(SRC_DIR)/%.s,$(BUILD_DIR)/%.rel,$(ASM_SOURCES))

ifdef DEVKITSMS

.PHONY: all rom assets analyse timing example clean
all: rom

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

assets: $(ASSET_HDR)

$(ASSET_HDR): $(ASSET_FILES) | $(BUILD_DIR)
	rm -rf $(ASSET_OUT)
	mkdir -p $(ASSET_OUT)
	cd $(ASSET_OUT) && assets2banks $(CURDIR)/$(ASSET_DIR) \
	    --firstbank=2 --singleheader=assets.h --compile --allowsplitting

$(VERSION_HDR): $(INC_DIR)/fmv/version.h
	mkdir -p $(GEN_DIR)
	awk -F'[".]' '/^#define FMV_VERSION "/ { printf "#define FMV_VERSION_MAJOR %du\n#define FMV_VERSION_MINOR %du\n", $$2, $$3; found = 1 } END { exit !found }' $< > $@.tmp
	mv $@.tmp $@

$(BUILD_DIR)/%.rel: $(SRC_DIR)/%.c $(ASSET_HDR) $(HEADERS) $(VERSION_HDR) | $(BUILD_DIR)
	$(SDCC) $(SDCC_FLAGS) -I$(ASSET_OUT) -c $< -o $@

$(BUILD_DIR)/%.rel: $(SRC_DIR)/%.s | $(BUILD_DIR)
	sdasz80 -l -o $@ $<

BANK_NUMS = $(shell ls $(ASSET_OUT)/bank*.rel 2>/dev/null \
                    | sed 's#.*/bank##; s#\.rel##' | sort -n)
BANK_RELS = $(foreach n,$(BANK_NUMS),$(ASSET_OUT)/bank$(n).rel)
BANK_FLAGS = $(foreach n,$(BANK_NUMS),-Wl-b_BANK$(n)=0x8000)

rom: $(ASSET_HDR) $(OBJECTS)
	$(SDCC) $(SDCC_ARCH) $(SDCC_STD) $(BANK_FLAGS) \
	    -o $(BUILD_DIR)/$(PROJECT).ihx \
	    $(CRT0)/crt0_sms.rel \
	    $(OBJECTS) $(BANK_RELS) \
	    $(SMSLIB)/SMSlib.lib
	ihx2sms $(BUILD_DIR)/$(PROJECT).ihx $(ROM)
	@echo "built $(ROM) ($$(stat -c %s $(ROM)) bytes)"

timing:
	@echo "timing runs on the host, not in the image: see the outer target"

example:
	$(MAKE) --no-print-directory -C examples/cutscene

analyse:
	cppcheck --std=c23 --enable=warning,style,performance,portability \
	    --check-level=exhaustive --inline-suppr --error-exitcode=1 --quiet \
	    --suppress=missingInclude --suppress=missingIncludeSystem \
	    --suppress=unmatchedSuppression \
	    -I$(INC_DIR) $(SRC_DIR)
	@echo "static analysis clean"

clean:
	rm -rf $(BUILD_DIR) examples/cutscene/build

else

.PHONY: all rom image shell analyse timing example hooks clean distclean
all: rom

image:
	docker build --target toolchain -t $(DOCKER_IMAGE) .

rom: image
	docker run --rm --user $(DOCKER_USER) -v "$(CURDIR):/work" -w /work $(DOCKER_IMAGE) \
	    make --no-print-directory rom

analyse: image
	docker run --rm --user $(DOCKER_USER) -v "$(CURDIR):/work" -w /work $(DOCKER_IMAGE) \
	    make --no-print-directory analyse

timing:
	uv --project tools run python tools/scripts/check_vdp_timing.py

example: image
	docker run --rm --user $(DOCKER_USER) -v "$(CURDIR):/work" -w /work $(DOCKER_IMAGE) \
	    make --no-print-directory example

hooks:
	git config core.hooksPath .githooks

shell: image
	docker run --rm -it --user $(DOCKER_USER) -v "$(CURDIR):/work" -w /work $(DOCKER_IMAGE) bash

clean:
	rm -rf $(BUILD_DIR) examples/cutscene/build

distclean: clean
	-docker rmi $(DOCKER_IMAGE)

endif
