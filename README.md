# CLX-S20P U-Boot：GPT 修復與嚴格建置

CLX-S20P **MT7986A／2-GiB DDR4／eMMC** 專用維護分支，fork 自
[Yuzhii0718/bl-mt798x-dhcpd](https://github.com/Yuzhii0718/bl-mt798x-dhcpd)。
沿用上游 `clx_s20` board、SP2 ATF 及網頁救援功能，修正 GPT 寫入流程。
不是 Breed 移植，亦不保證 bootloader 被破壞後仍可透過 Reset 救援。

- [從 0 到 1 刷機 skill 與固件](https://github.com/LucxXxifer/clx-s20p-firmware)
- [每日檢查與建置](https://github.com/LucxXxifer/clx-s20p-uboot/actions/workflows/s20p-reviewed.yml)
- [候選版本與 SHA-256](https://github.com/LucxXxifer/clx-s20p-uboot/releases)
- [上游原始說明](docs/UPSTREAM-README.md)

## 修復內容

上游產生副 GPT 時，`alternate_lba` 沿用主 GPT 的值，導致副表指向自己。
本分支將副表回指設為 LBA 1，重算 CRC，並按 entry metadata 推算副表位置。
刷寫前核對主表／entry CRC、長度、LBA 範圍、分區重疊及設備幾何；驗證失敗
立即拒寫。驗證／主表／副表寫入錯誤會傳回呼叫者。分區 entry 不移動、不擴容。

支援完整 primary-only、512-byte sector、最多 128 個標準 128-byte entry 的
GPT 上傳；其他格式拒絕。已測試 241696768／244277248 sectors 的合成設備。
**GPT 檔仍須按實機 sector 數與所需分區配置選擇，不能僅看「128GB」。**

## 每日流程

GitHub Actions 每日 **03:37（Asia/Shanghai）** 檢查上游 master；排程可能延遲。
來源 SHA 與本分支政策未變且上次完整檢查成功時跳過建置。首次、手動或本分支
更新會驗證已鎖定來源。閒置的公開 fork 可能被 GitHub 暫停排程，需在 Actions
重新啟用；cache 被清除時會安全地重跑。

1. 固定 upstream SHA，精確套用已知 GPT 修補；衝突即停止。
2. 用 ASan／UBSan 執行真正 C 寫入函式的回歸測試，再測損壞 FIP／發佈政策。
3. 兩個獨立 runner 以固定 Ubuntu digest、簽章 APT snapshot、Node SHA-256、
   npm integrity lock 建置；編譯階段禁止網路，不提供發佈憑證。
4. 核對 S20P 配置、2-GiB DTB、FIP TOC／內部 CRC／SHA-256、BL31／BL33，
   並要求兩次乾淨編譯的成品與配置完全一致。
5. 只有 `ci/source.lock.json` 內已審核的精確上游 SHA 才保留 binary 並產生
   **prerelease**；未知上游變更只保留差異／稽核報告，等待原始碼審核。

自動化會套用已知修補，不會猜測修復未知 bug、修改通過條件或自動批准來源。
本分支停用上游通用 BL2／GPT／FIP release workflows，避免繞過上述關卡。

## 成品狀態與使用

Release 僅提供未壓縮 FIP、`SHA256SUMS`、`audit.json`、來源 lock 和說明。
不提供 BL2、不包含原廠備份、不連線或刷寫設備。

**候選版尚未完成這個映像的實機開機、Reset 救援、GPT 寫入讀回、固件啟動及
原廠還原驗證。** CI 無法代替這些驗收；通過後才可另外建立 stable 版本。
兩次編譯一致證明可重現，並不證明所有硬體行為正確或沒有未知漏洞。

刷入修復版 FIP 不會自動修好之前已寫壞的 GPT。後續新刷 GPT 仍先讀回主副表；
確認有效後才可省略 agent 修復。原廠恢復依然依賴每臺設備獨有的備份、幾何和
原分區配置。寫主副表不是斷電原子操作，刷寫期間仍須穩定供電。

## 維護與本機測試

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s ci/tests -v
shellcheck ci/build.sh
actionlint .github/workflows/s20p-reviewed.yml
```

回歸 harness 只替換 MMC transport／console，直接編譯原始碼中的 GPT 函式；
Python 獨立檢查捕獲到的實際寫入 bytes，不需要百 GB 映像或接上路由器。

審核新版上游時：檢查 Actions 的 `source-review` 比較連結與 changed paths、
硬體配置／ATF／web 寫入路徑／依賴變化；更新已審核 SHA 及必要 input hashes，
維持 checked-in C 與 `ci/patches/s20p-gpt.patch` 一致，再提交 default branch。
任一測試、補丁或 reproducibility 失敗，先解決原因再重新執行。

來源、授權與上游作者署名依原專案保留，詳見 [LICENSE](LICENSE)。
