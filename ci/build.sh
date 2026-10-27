#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0
set -euo pipefail

# Run inside the pinned image, without network, against one fresh source tree.
cd /source
export SOURCE_DATE_EPOCH
SOURCE_DATE_EPOCH=$(python3 -c 'import json; print(json.load(open("source.json"))["source_date_epoch"])')
source_sha=$(python3 -c 'import json; print(json.load(open("source.json"))["upstream_sha"])')
export KBUILD_BUILD_USER=builder KBUILD_BUILD_HOST=clx-s20p KBUILD_BUILD_VERSION=1
export KBUILD_BUILD_TIMESTAMP
KBUILD_BUILD_TIMESTAMP=$(date --utc --date="@$SOURCE_DATE_EPOCH" '+%Y-%m-%d %H:%M:%S')
export BUILD_STRING="s20p-${source_sha:0:12}-gptfix1"
export BUILD_MESSAGE_TIMESTAMP
BUILD_MESSAGE_TIMESTAMP="\"$KBUILD_BUILD_TIMESTAMP\""
export LOCALVERSION=-s20p-gptfix1
export BOARD=clx_s20 SOC=mt7986 VERSION=SP2 VARIANT=default
export FSTHEME=bootstrap FIXED_MTDPARTS=0 MULTI_LAYOUT=0 COPY_BL2=0
export FIP_COMPRESS=0 SIMG=0 UBIMNG=0 TELNETD=0 NAND_RAW=0 SILENT=Y

bash build.sh
cp atf-20260123/build/mt7986/release/fip.bin /out/fip.bin
cp atf-20260123/build/mt7986/release/bl31.bin /out/bl31.bin
cp uboot-mtk-20250711/u-boot.bin /out/u-boot.bin
cp uboot-mtk-20250711/u-boot.dtb /out/u-boot.dtb
cp uboot-mtk-20250711/.config /out/uboot.config
cp atf-20260123/build/.config /out/atf.config
cp source.json /out/source.json
fdtget -t x /out/u-boot.dtb /memory@40000000 reg > /out/dtb-memory.txt
{
    aarch64-linux-gnu-gcc --version
    node --version
    npm --version
    dpkg-query -W -f='${Package} ${Version}\n'
} > /out/toolchain.txt
