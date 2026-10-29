# Simpul

Simpul mengatur tugas coding yang dikerjakan beberapa worker di bawah pengawasan pengguna. Kamu dapat mengirim tujuan, memantau tugas, memeriksa hasil, dan membatalkan pekerjaan dari host yang mendukung Model Context Protocol (MCP).

Nama produknya Simpul. Repository, paket Python, dan pengaturan teknis tetap menggunakan `SubagentBridge` atau `subagentbridge` untuk menjaga kompatibilitas.

Rilis publik: [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4). Simpul memerlukan pengawasan pengguna. Worker secara default memakai identitas OS yang sama, sehingga jangan menjalankan kode yang tidak dipercaya seolah-olah terkurung dalam sandbox.

## Mulai pakai

Siapkan Python 3.11 sampai 3.13 dan Git. Contoh untuk Windows PowerShell:

```powershell
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout v1.1.4
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Lanjutkan [panduan menghubungkan Simpul ke Antigravity IDE](docs/public/GETTING_STARTED.md). Gunakan path absolut Python virtual environment di konfigurasi host. Server ini berkomunikasi melalui MCP stdio; menjalankannya di terminal tidak membuka aplikasi chat.

Untuk Linux dan konfigurasi lain, baca [panduan instalasi](docs/INSTALLATION_QUICKSTART.md).

## Yang tersedia

| Kebutuhan | Dukungan |
| --- | --- |
| Membagi dan memantau pekerjaan | Run, task, worker, antrean, dan status tersimpan lokal |
| Meninjau hasil | Bukti hasil, log audit, dan pemeriksaan kesesuaian tugas |
| Menjalankan tugas dengan pengawasan | Pemeriksaan izin, batas workspace, dan pembatalan |
| Memisahkan pekerjaan Git | Worktree per worker dan pemulihan status |
| Menghubungkan host/model | Adapter yang memeriksa kemampuan sebelum eksekusi |

Pengiriman tujuan saja tidak membuktikan tugas telah dijalankan. Tugas tanpa perintah eksekusi yang valid tidak boleh dianggap terverifikasi. Dukungan protokol MCP juga tidak membuktikan semua interaksi pada IDE sudah diuji.

## Batas penggunaan

- Autonomi tetap dimatikan (`AUTONOMY: OFF`). Perubahan berizin memerlukan keputusan pengguna yang sesuai.
- Model dan worker tidak boleh menyetujui tindakan mereka sendiri. `approve_action` dan `apply_code_fix` tidak diekspos sebagai tool yang bisa dipanggil model.
- Isolasi worker berbahaya (E18) dan autentikasi operator independen masih menjadi batas keamanan terbuka.
- Kontrol Linux dengan identitas worker khusus bersifat eksperimental. Worktree atau proses terpisah bukan sandbox OS.
- Pengujian otomatis tidak menggantikan validasi pada host pengguna atau sertifikasi enterprise.

Baca [keamanan](docs/public/SECURITY.md), [batas kompatibilitas](docs/COMPATIBILITY_LIMITATIONS.md), dan [kesiapan penggunaan organisasi](docs/ENTERPRISE_READINESS.md) sebelum mengizinkan eksekusi.

## Dokumentasi

| Tujuan | Bacaan |
| --- | --- |
| Instalasi dan tugas pertama | [Mulai pakai](docs/public/GETTING_STARTED.md) |
| Memahami status dukungan | [Status proyek](docs/SIMPUL_STATUS.md) dan [kemampuan serta roadmap](docs/public/PARITY_AND_ROADMAP.md) |
| Memahami desain sistem | [Arsitektur](docs/ARCHITECTURE.md) |
| Integrasi teknis | [MCP](docs/MCP_INTEGRATION.md), [API](docs/API_REFERENCE.md), [konfigurasi](docs/CONFIGURATION.md) |
| Operasional dan pemulihan | [Panduan insiden](docs/OPERATIONAL_INCIDENT_RUNBOOK.md) dan [pemulihan data](docs/PERSISTENCE_RECOVERY.md) |
| Pengembangan dan rilis | [Kontribusi](docs/CONTRIBUTING.md), [pengujian](docs/TESTING_QA_GUIDE.md), [provenance rilis](docs/RELEASE_ATTESTATION.md) |

[Indeks dokumentasi](docs/public/README.md) memisahkan panduan penggunaan dari referensi teknis. Rilis menggunakan [GitHub Releases](https://github.com/rzqllh/SubagentBridge/releases); riwayat perubahan ada di [CHANGELOG.md](CHANGELOG.md).

## Lisensi dan penghargaan

Simpul menggunakan [MIT](LICENSE). Implementasi Python ini berdiri sendiri dan mempelajari pola arsitektur Cindy/Orca; lihat [third-party notices](THIRD_PARTY_NOTICES.md). Kesamaan pola tidak berarti seluruh kemampuan atau antarmuka upstream sudah tersedia.
