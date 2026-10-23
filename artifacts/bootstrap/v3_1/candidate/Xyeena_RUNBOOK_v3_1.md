# Runbook eksekusi — Subagent Bridge (v3.1 candidate; belum disahkan)

Urutan ini bikin agent lu jalan tanpa ngarang. Command Windows (PowerShell) di bawah **belum pernah gua jalankan di Windows**; yang sudah gua tes cuma `bve_tool.py selftest` di Linux (10/10 lulus pada kandidat v1.1 Linux). Jadi langkah 2 itu bukti pertama di mesin lu.

## 0. Isi paket (taruh di folder DI LUAR repo, mis. `C:\xyeena-pack\`)

1. `Xyeena_SubagentBridge_ANTIGRAVITY_GOAL_v3_1.md` — prompt untuk agent implementer
2. `Xyeena_SubagentBridge_Production_PR_Plan_v3_1.md` — plan v3.1 candidate (baru binding setelah ratifikasi)
3. `Xyeena_SubagentBridge_TEAM_RULES.md` — dari zip lu, TIDAK berubah (file `subagent-bridge-team-rules.md` dari gua isinya identik)
4. `bve_tool.py` — helper lintas-OS v1.1 candidate; menggantikan hash lama hanya setelah ratifikasi
5. `Xyeena_SubagentBridge_VERIFIER_PROMPT_v3_1.md` — dipakai di sesi terpisah, nanti
6. `Xyeena_Harness_PATCH_GOAL_v3_1.md` — repo harness, terpisah, nanti

Semua file v2 dan goal harness lama: abaikan. File v3 asli tetap arsip read-only; tidak boleh diam-diam ditimpa. Ratifikasi v3.1 dan pin helper baru memerlukan approval spesifik.

## 1. Cek hash (PowerShell, di folder paket)

```
Get-FileHash -Algorithm SHA256 .\bve_tool.py, .\Xyeena_SubagentBridge_Production_PR_Plan_v3_1.md, .\Xyeena_SubagentBridge_TEAM_RULES.md | Format-Table Hash, Path -AutoSize
```
Harus persis:
- `bve_tool.py` = `21f1ab40820b94c74daf8921ec9683fc18e3a38c5f4d2d67d27571b790cbfece`
- Plan v3.1 = `2b840256eb488cbaf1a404bf33ca28a2686b7b34cf062a4c26bb5c0fe7c39f0a`
- TEAM_RULES = `aa9e843bb2c13a369c5a26f4932f48418cf4b407e0e3a6659aaab5659f86272b`

Beda = biasanya line ending berubah (Git/unduhan Windows). Jangan lanjut; kirim ke gua.

## 2. Buktikan tool-nya jalan di mesin lu

```
python .\bve_tool.py selftest
```
Harus berakhir `SELFTEST PASSED (10/10)`. Kalau FAILED atau error, kirim outputnya ke gua sebelum lanjut: verifier bergantung ke tool ini.

## 3. Siapkan repo

```
cd <path repo SubagentBridge>
git status --porcelain      # harus kosong
git remote -v               # harus menunjuk rzqllh/SubagentBridge
```
Catat path absolut repo-nya; verifier butuh itu (verifier meng-clone dari path lokal ini, jadi commit yang belum di-push tetap ketemu).

## 4. Jalankan implementer (Antigravity)

1. Sesi agent BARU di repo itu. Buat 4 file (goal, plan, TEAM_RULES, bve_tool.py) bisa dibaca agent. Cara paling aman: tambahkan folder paket sebagai workspace/attachment tambahan. Gua belum verifikasi fitur attach Antigravity, jadi kalau nggak bisa, salin folder `xyeena-pack/` ke dalam repo lalu `echo xyeena-pack/ >> .git/info/exclude` (lokal, nggak ikut commit, `git status` tetap bersih).
2. Paste ini:
```
Execute the attached Antigravity /goal v3 (Xyeena_SubagentBridge_ANTIGRAVITY_GOAL_v3_1.md).
Respond with sections 1 and 3 only (integrity check, then AUDIT ONLY).
Do not edit, install, commit or push anything.
```

## 5. Nilai respons pertamanya (jangan langsung setuju)

Bagus kalau:
- ada bagian A1–A8 dan lima field Team Rules + `UNVERIFIED_CLAIMS`
- hash cocok dan `SELFTEST PASSED` tercantum
- tiap klaim bertag `[READ path:lines]` / `[RAN #n exit=X]` / `[UNKNOWN]`
- 10 klaim legacy dijawab CONFIRMED/REFUTED/PARTIAL/UNKNOWN dengan kutipan baris
- hal yang nggak bisa dikerjakan ditulis `NOT PERFORMED`

Tolak dan suruh ulang kalau:
- ada file yang diedit, dibuat, di-commit, atau ada yang di-install
- klaim tanpa tag, atau "all tests pass" tanpa command dan output
- path atau fungsi disebut tapi nggak pernah dibuka
Paste responsnya ke gua kalau mau gua cek klaim tak bertag.

## 6. Jawab keputusan A7 (ini approval Fase A)

Tulis eksplisit, satu per satu:
```
(i) Phase A chat-approval: CONFIRMED
(ii) Verifier: <nama model/tool>, repo path: <path absolut>   (atau "none available")
(iii) PR-00 scope: APPROVED exactly as written in A6   (atau tulis revisinya)
```
Approval hanya sah untuk operasi persis yang ditanyakan. Agent lalu menyajikan DP-00 (satu paket semua dependency, file CI, branch, command). Setujui atau tolak per item. Di Fase A blok `HUMAN-APPROVAL` ditulis agent sendiri, jadi cocokkan dengan chat asli lu sebelum merge.

## 7. Setelah agent selesai PR-00 (berhenti di commit lokal)

Agent memberi PR_ID, base SHA, head SHA, acceptance criteria, path repo. Lalu:
1. Buka sesi BARU, idealnya model beda dari implementer.
2. Paste `Xyeena_SubagentBridge_VERIFIER_PROMPT_v3_1.md`, isi placeholder-nya (`REPO_SOURCE: LOCAL` dengan repo path lokal, atau `REPO_SOURCE: GITHUB` dengan remote branch PR yang sudah di-push secara disetujui; `WORK_DIR` dan `LOG_DIR` folder kosong, `LOG_DIR` di luar checkout), attach paket.
3. Verifier harus mulai dengan hash check + `selftest`, menulis skenario dari AC sebelum baca diff, dan menjalankan semuanya lewat `bve_tool.py run --checkout-root <checkout>`. Jika commit sudah di-push dengan persetujuan pada branch PR, boleh gunakan `REPO_SOURCE: GITHUB` di verifier v3.1; remote branch HEAD harus sama persis dengan SHA yang diberikan, tanpa fallback.
4. Verdict `VERIFIED` + `INDEPENDENCE: FULL` → lu merge sendiri. `LIMITED` → review diff dulu. Push itu gate: lu yang approve.
5. Kasih tahu agent merge SHA, lalu suruh PR berikutnya.

## 8. Keputusan lu yang datang belakangan

- **D-03** sebelum PR-03: saluran approval. Rekomendasi gua (b), approval lewat perangkat terpisah (HP), karena nggak bergantung ke isolasi OS. Alternatif: worker di identitas OS/container terpisah, atau tetap approval via chat dan autonomy OFF.
- **D-01** di PR-04b: perilaku Windows kalau isolasi nggak tercapai. Rekomendasi gua: blokir autonomy untuk CLI eksternal dan pakai tool-proxy.
- **D-02** di PR-05: cek ToS provider upstream sebelum 9Router dipakai ke provider non-lokal (gua belum verifikasi).
- **H6** di repo harness: pilih lisensi. Agent dilarang memilih.

## 9. Jangan

- Jangan biarkan implementer memverifikasi kerjanya sendiri, dan jangan kasih verifier catatan implementer.
- Jangan nyalakan `autonomous_execution` sebelum gate AG-1 (Plan v3.1 §0 item 15) lulus. Sampai itu, semua run berlabel `AUTONOMY: OFF`.
- Jangan anggap hasil Fase A/B sebagai jaminan produk: itu Bootstrap evidence, bukan Executor receipt.
- Harness patch (repo terpisah) jalan dengan loop yang sama, pakai `Xyeena_Harness_PATCH_GOAL_v3_1.md`.
