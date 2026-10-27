# CLX-S20P fork

- Scope: MT7986A, 2-GiB DDR4, eMMC, upstream board selector `clx_s20`, SP2.
- Default branch: `clx-s20p`. Never push fixes into upstream `master`.
- Keep the GPT source change and `ci/patches/s20p-gpt.patch` identical relative
  to the reviewed upstream SHA in `ci/source.lock.json`.
- Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s ci/tests -v`,
  `shellcheck ci/build.sh`, and actionlint on the dedicated workflow.
- CI artifacts are prerelease candidates. Do not claim hardware acceptance or
  promote stable without physical S20P evidence. Never include unit backups,
  factory data, BL2 or a generic GPT image in a release.
- Unreviewed upstream changes and any failed check prevent binary publication.
- Do not restore upstream release workflows on this branch; they bypass gates.
