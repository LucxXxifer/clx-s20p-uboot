/* SPDX-License-Identifier: GPL-2.0 */
/* Host-only MMC transport. GPT types and functions come from the real source. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef unsigned long long u64;
typedef u16 __le16;
typedef u32 __le32;
typedef u64 __le64;
typedef u16 efi_char16_t;
typedef struct { u8 b[16]; } efi_guid_t;
#define __packed __attribute__((packed))
#define le16_to_cpu(x) (x)
#define le32_to_cpu(x) (x)
#define le64_to_cpu(x) (x)
#define cpu_to_le16(x) (x)
#define cpu_to_le32(x) (x)
#define cpu_to_le64(x) (x)
#define DIV_ROUND_UP(n, d) (((n) + (d) - 1) / (d))
#define GPT_PRIMARY_PARTITION_TABLE_LBA 1ULL
#define GPT_PRIMARY_PARTITION_ENTRY_LBA 2ULL
#define GPT_HEADER_SIGNATURE_UBOOT 0x5452415020494645ULL
#define GPT_HEADER_REVISION_V1 0x00010000
#define GPT_ENTRY_SIZE 128
#define MSDOS_MBR_SIGNATURE 0xAA55
#define MSDOS_MBR_BOOT_CODE_SIZE 440
#define EFI_PMBR_OSTYPE_EFI_GPT 0xEE
#define CONFIG_PARTITIONS 1
#define cprintln(...) ((void)0)

struct blk_desc { u64 lba; };
struct mmc { unsigned int read_bl_len, write_bl_len; };
static struct blk_desc desc;
static struct mmc card;
static int calls, fail_call, initialized;
static const char *outputs[2];

static struct blk_desc *mmc_get_blk_desc(struct mmc *mmc)
{
	(void)mmc;
	return &desc;
}

static struct mmc *_mmc_get_dev(u32 dev, int hwpart, bool write)
{
	(void)dev; (void)hwpart; (void)write;
	return fail_call == -1 ? NULL : &card;
}

static int _mmc_write(struct mmc *mmc, u64 offset, size_t max_size,
		      const void *data, size_t size, bool verify)
{
	FILE *out;
	(void)verify;
	calls++;
	if (calls == fail_call)
		return -EIO;
	if (calls > 2 || offset % mmc->write_bl_len ||
	    size % mmc->write_bl_len || (max_size && size > max_size) ||
	    size > desc.lba * mmc->write_bl_len ||
	    offset > desc.lba * mmc->write_bl_len - size)
		return -EINVAL;
	out = fopen(outputs[calls - 1], "wb");
	if (!out || fwrite(data, 1, size, out) != size)
		exit(71);
	fclose(out);
	return 0;
}

static void part_init(struct blk_desc *d)
{
	(void)d;
	initialized++;
}

static u32 crc32(u32 crc, const unsigned char *p, size_t len)
{
	crc = ~crc;
	while (len--) {
		crc ^= *p++;
		for (int bit = 0; bit < 8; bit++)
			crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1)));
	}
	return ~crc;
}
