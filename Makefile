PROJECT      := smsgg-media-player
ROM_NAME     := smsggmedia
TARGET       ?= sms
ifeq ($(TARGET),gg)
TARGET_DIR   := build/gg
TARGET_FLAGS := -DTARGET_GG
TARGET_LIB   := SMSlib_GG.lib
else ifeq ($(TARGET),sms)
TARGET_DIR   := build
TARGET_FLAGS :=
TARGET_LIB   := SMSlib.lib
else
$(error TARGET must be sms or gg, got $(TARGET))
endif
ROM          := build/$(ROM_NAME).$(TARGET)
DOCKER_IMAGE := $(PROJECT)-toolchain
DOCKER_USER  := $(shell id -u):$(shell id -g)
EXAMPLE_FMV_DIR ?= ../../build/bundle

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
SDCC_INC     := -I$(INC_DIR) -I$(SRC_DIR)/$(TARGET) -I$(GEN_DIR) -I$(SMSLIB)/src
SDCC_FLAGS   := $(SDCC_ARCH) $(SDCC_STD) $(SDCC_WARN) $(SDCC_INC) $(TARGET_FLAGS)

CPPCHECK     := cppcheck --std=c23 --enable=warning,style,performance,portability \
                --check-level=exhaustive --inline-suppr --error-exitcode=1 --quiet \
                --suppress=missingInclude --suppress=missingIncludeSystem \
                --suppress=unmatchedSuppression '-D_Noreturn=[[noreturn]]' -I$(INC_DIR)

SOURCES      := $(wildcard $(SRC_DIR)/*.c)
TARGET_SOURCES := $(wildcard $(SRC_DIR)/$(TARGET)/*.c)
TARGET_HDR   := $(SRC_DIR)/$(TARGET)/fmv_target.h
ASM_SOURCES  := $(wildcard $(SRC_DIR)/*.s)
OBJECTS      := $(patsubst $(SRC_DIR)/%.c,$(TARGET_DIR)/%.rel,$(SOURCES)) \
                $(patsubst $(SRC_DIR)/$(TARGET)/%.c,$(TARGET_DIR)/%.rel,$(TARGET_SOURCES)) \
                $(patsubst $(SRC_DIR)/%.s,$(TARGET_DIR)/%.rel,$(ASM_SOURCES))

ifdef DEVKITSMS

.PHONY: all rom assets analyse timing example clean
all: rom

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(TARGET_DIR)/.made: | $(BUILD_DIR)
	mkdir -p $(TARGET_DIR)
	touch $@

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

$(TARGET_DIR)/%.rel: $(SRC_DIR)/%.c $(ASSET_HDR) $(HEADERS) $(TARGET_HDR) $(VERSION_HDR) | $(TARGET_DIR)/.made
	$(SDCC) $(SDCC_FLAGS) -I$(ASSET_OUT) -c $< -o $@

$(TARGET_DIR)/%.rel: $(SRC_DIR)/$(TARGET)/%.c $(ASSET_HDR) $(HEADERS) $(TARGET_HDR) $(VERSION_HDR) | $(TARGET_DIR)/.made
	$(SDCC) $(SDCC_FLAGS) -I$(ASSET_OUT) -c $< -o $@

$(TARGET_DIR)/%.rel: $(SRC_DIR)/%.s $(SRC_DIR)/$(TARGET)/target.inc | $(TARGET_DIR)/.made
	sdasz80 -l -I$(SRC_DIR)/$(TARGET) -o $@ $<

BANK_NUMS = $(shell ls $(ASSET_OUT)/bank*.rel 2>/dev/null \
                    | sed 's#.*/bank##; s#\.rel##' | sort -n)
BANK_RELS = $(foreach n,$(BANK_NUMS),$(ASSET_OUT)/bank$(n).rel)
BANK_FLAGS = $(foreach n,$(BANK_NUMS),-Wl-b_BANK$(n)=0x8000)

rom: $(ASSET_HDR) $(OBJECTS)
	$(SDCC) $(SDCC_ARCH) $(SDCC_STD) $(BANK_FLAGS) \
	    -o $(TARGET_DIR)/$(ROM_NAME).ihx \
	    $(CRT0)/crt0_sms.rel \
	    $(OBJECTS) $(BANK_RELS) \
	    $(SMSLIB)/$(TARGET_LIB)
	ihx2sms $(TARGET_DIR)/$(ROM_NAME).ihx $(ROM)
	@echo "built $(ROM) ($$(stat -c %s $(ROM)) bytes)"

timing:
	@echo "timing runs on the host, not in the image: see the outer target"

example:
	$(MAKE) --no-print-directory -C examples/cutscene FMV_DIR=$(EXAMPLE_FMV_DIR)

analyse:
	$(CPPCHECK) -I$(SRC_DIR)/sms $(SRC_DIR)/*.c $(SRC_DIR)/sms/*.c
	$(CPPCHECK) -DTARGET_GG -I$(SRC_DIR)/gg $(SRC_DIR)/*.c $(SRC_DIR)/gg/*.c
	@echo "static analysis clean"

clean:
	rm -rf $(BUILD_DIR) examples/cutscene/build

else

.PHONY: all rom image shell analyse timing example hooks clean distclean
all: rom

image:
	docker build --target toolchain -t $(DOCKER_IMAGE) .

rom: image
	docker run --rm --user $(DOCKER_USER) -e HOME=/tmp -v "$(CURDIR):/work" -w /work $(DOCKER_IMAGE) \
	    make --no-print-directory rom TARGET=$(TARGET)

analyse: image
	docker run --rm --user $(DOCKER_USER) -e HOME=/tmp -v "$(CURDIR):/work" -w /work $(DOCKER_IMAGE) \
	    make --no-print-directory analyse

timing:
	uv --project tools run python tools/scripts/check_vdp_timing.py --target $(TARGET)

example: image
	docker run --rm --user $(DOCKER_USER) -e HOME=/tmp -v "$(CURDIR):/work" -w /work $(DOCKER_IMAGE) \
	    make --no-print-directory example EXAMPLE_FMV_DIR=$(EXAMPLE_FMV_DIR)

hooks:
	git config core.hooksPath .githooks

shell: image
	docker run --rm -it --user $(DOCKER_USER) -e HOME=/tmp -v "$(CURDIR):/work" -w /work $(DOCKER_IMAGE) bash

clean:
	rm -rf $(BUILD_DIR) examples/cutscene/build

distclean: clean
	-docker rmi $(DOCKER_IMAGE)

endif
