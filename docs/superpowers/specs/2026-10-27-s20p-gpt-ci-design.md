# CLX-S20P GPT repair and reviewed builds

## Goal and context

Maintain a fork of Yuzhii0718/bl-mt798x-dhcpd for the CLX-S20P MT7986A,
2-GiB DDR4, eMMC board. The user requested the fork, daily upstream detection,
the known GPT repair, compilation and strict checks before distributing images.
The existing firmware and provisioning skill remain in LucxXxifer/clx-s20p-firmware.

Reviewed baseline: e4cf4dc72d451dc7a86c9508390ad5a2e50743c4, SP2,
board selector clx_s20. The secondary header inherits the primary alternate_lba,
so it points to itself. mmc_write_gpt also ignores adjust_gpt failures; header
length and entry-array validation are insufficient before writes.

## Boundaries

Only publish an uncompressed FIP candidate for this board. Do not publish BL2,
GPT images or factory data. No router connection or flashing is part of CI.
Do not equate a successful build with physical boot/recovery/GPT validation.
Keep the upstream license and attribution. Existing upstream workflows must
not bypass this fork's release gates.

## Repair and regression evidence

Validate the primary-only 512-byte-sector image, revision/header size, header
CRC, entry-array bounds/CRC, usable LBAs and non-overlapping partition ranges
before the first write. Support at most 128 standard 128-byte entries. Reject
truncated, padded/whole-disk, unsupported and corrupt inputs. Preserve entry
bytes and partition boundaries. Derive secondary placement from entry metadata,
not arbitrary upload length; set secondary alternate_lba to 1 and recompute CRC.
Propagate validation, primary write and secondary write errors.

A host C harness compiles the actual adjust_gpt, backup_secondary_gpt and
mmc_write_gpt implementations extracted from the source. Only MMC transport
and console output are substituted. Python independently checks the captured
wire format. Test both 241696768- and 244277248-sector devices, resizing,
malformed inputs, error propagation and zero writes after rejection. Run with
address/undefined-behavior sanitizers. Demonstrate failure against unpatched
upstream before claiming regression coverage.

## Daily workflow and review

At 03:37 Asia/Shanghai daily, resolve the upstream master SHA. A cache marker
bound to the trusted fork revision and upstream SHA prevents unchanged builds.
The trusted workflow materializes the exact upstream commit and applies the
maintained patch without fuzzy matching. A patch conflict is a failure.

Run tests, then two independent clean SP2 builds in parallel. Pin Actions by
commit, the Ubuntu build image by digest, APT to a dated signed snapshot and
Node by version/SHA-256; npm ci uses the checked-in integrity lock and disables
lifecycle scripts. Compile with networking disabled, fixed timestamps and build
identity. Compare FIP, BL31, BL33 and configuration digests. Inspect FIP TOC,
component identity, bounds, board device tree and FIP partition size limits.

The reviewed upstream SHA in ci/source.lock.json is an additional release gate.
New upstream code is tested and compiled for review, but cannot publish a binary
until that exact SHA is reviewed and committed into the lock on the default
fork branch. Reports include the comparison URL and changed paths. Unknown
future bugs are not silently auto-fixed. A deliberate lock update is the source
review record; there is no automatic PR approval or stable promotion.

Only after all gates pass does a separate job with contents:write publish an
immutable prerelease with FIP, SHA256SUMS and audit reports. Build jobs have no
write credentials. Unreviewed builds expose reports only. Stable release is a
later, explicit operation after physical validation; this task does not create
a stable-promotion workflow.

## Done criteria and limits

Fork exists under LucxXxifer/clx-s20p-uboot; daily schedule is active on the
default branch; regression and policy tests pass; two GitHub Actions builds
match; a first reviewed candidate and its checksums/reports are available.
Keep the previous GPT readback procedure until physical testing demonstrates
that the fixed bootloader writes a valid primary/secondary pair. Updating FIP
does not repair an already-invalid on-disk GPT. Power loss during two separate
writes remains a physical risk.
