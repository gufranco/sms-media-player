FMV_DIR ?= ../../build/bundle
FMV_BUILD := build/fmv
FMV_FIRST_BANK := 2
include $(FMV_DIR)/fmv.mk

.PHONY: all clean
all: build/cutscene.sms

build/main.rel: main.c $(FMV_ASSET_HDR)
	mkdir -p build
	sdcc $(FMV_SDCC_FLAGS) --no-std-crt0 --data-loc 0xC000 -c $< -o $@

build/cutscene.ihx: build/main.rel $(FMV_OBJECTS)
	sdcc -mz80 --sdcccall 1 --no-std-crt0 --data-loc 0xC000 $(FMV_BANK_FLAGS) -o $@ \
	    $(CRT0)/crt0_sms.rel build/main.rel $(FMV_OBJECTS) $(FMV_BANK_RELS) $(SMSLIB)/SMSlib.lib

build/cutscene.sms: build/cutscene.ihx
	ihx2sms $< $@
	@echo "built $@ ($$(stat -c %s $@) bytes)"

clean:
	rm -rf build
