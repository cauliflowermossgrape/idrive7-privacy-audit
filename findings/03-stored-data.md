# 03 — Personal data the stock MGU keeps on its own storage

Scope: what the stock iDrive 7 MGU keeps at rest, where it is, whether it is encrypted, and whether a factory reset or "delete personal data" removes it. Sending data to BMW is covered in another report.

Source: a 32 GB image of a stock MGU eMMC. I read it only with `debugfs` at partition offsets. I did not mount or change it, and I ran no binaries from it. The car's HDD (`sda`) is **not** in this image.

I copied no content values (names, numbers, addresses, coordinates, VIN, MACs, IDs, keys). This report lists only paths, owners, sizes, counts, schemas and config.

Confidence: **H** = seen directly in config, file or binary. **M** = strong inference from owner, size or strings. **L** = guess. "Inference" is marked wherever it applies.

Evidence was gathered as metadata only: a listing of mode, uid, gid, size and path for all 11,949 entries on `/var/opt` (file names still encrypted), the same for `/var/sys`, and strings from the service binaries.

---

## 0. Storage layout (where things can live)

| Partition | Mount | FS | Writable | Holds user data? | Evidence |
|---|---|---|---|---|---|
| p8 (sector 5269504) | `/` rootfs | ext4 | ro | no | `/etc/fstab` `/dev/root / auto ro` |
| p9 (8949760) | `/mnt/dataro` | ext4 | ro | no (maps, HMI assets, speech models) | fstab |
| **p10 (37238784)** | **`/var/opt`** ("pers") | ext4 + **ecryptfs** | rw | **yes, all persistent user data** | fstab `/dev/mmcblk0p10 /var/opt ext4 ...,discard,...acl` |
| p12 (61007872) | `/var/sys` ("dat_sys") | ext4 | ro at runtime | vehicle and coding data, keys. Not user data | fstab; tree in `p12-list.tsv` |
| p1/p3/p5/p6/p7/p11 | ABL self-update, RSU/bolo recovery rootfs, empty | ext4 | — | no | `debugfs stats` (volume names `ablupdate`, last-mounted `/tmp/rsuRootFS`, `/tmp/boloRootFS`) |
| HDD `sda1` | `/mnt/dataro/hddata` (`MGU_HDD_DATA`) | ext4 (inference) | ro | no (map/HMI data) | `hddmgr` strings `/dev/disk/by-bus/ata/MGU_HDD_DATA` |
| **HDD `sda2`** | **`/mnt/share` ≈ `/var/opt/hdshare`** (`MGU_HDD_SHARE`) | ext4 (inference) | rw | **yes: media DB, covers, Spotify cache, drive-recorder dir, nav/tm/oap/sin traces** | `hddmgr` strings; `/etc/tmpfiles.d/high/10-recovery-hdshare.conf`; mediaonoff XML |

RAM-only (tmpfs, gone at power-off), from `/etc/fstab` and units in `/lib/systemd/system`:
- `/var/cache/contactbook`: `var-cache-contactbook.mount`, tmpfs 50 MB, uid 2000 (pim).
- `/var/cache/mapramdisk`, `/var/cache/mediaramdisk`, `/var/cache/projectedmodes`.
- `/tmp/navi`, which holds `ti_llr_persistence.sqlite`, `/tmp/speech` and `/tmp/utterance.pcm`.
- The systemd journal: `/etc/systemd/journald.conf` sets `Storage=volatile`, `RuntimeMaxUse=12M`.
- The DLT live log `/tmp/dlt.log`, from `/etc/dlt.conf`.

The sizes below are **ecryptfs ciphertext sizes**. ecryptfs adds an 8 KiB header and pads to 4 KiB, so a file of 8192 B is empty, 12288 B holds at most 4 KiB, and so on.

---

## 1. Summary table

| Data type | Location (plaintext path, as seen by the running unit) | Encrypted at rest? | Cleared by factory reset? | Conf. |
|---|---|---|---|---|
| Phone PIM DB: SMS, e-mail, calendar, call lists; contacts probably (see §2) | `/var/opt/public/con/PIM.db` + `PIM_BACKUP.db`; on disk one ~200 KB file (con_2000), modified on the last drive | yes (ecryptfs "public" key) | yes (not whitelisted) | H path/schema, M contents |
| Outgoing message drafts (BMessage) | `/var/opt/public/con/BMessageOutbox*` | yes | yes | M |
| Contact pictures | `/var/opt/public/con/pictures/` (empty dir on disk) and `/var/cache/contactbook` (RAM) | yes / RAM | yes | M |
| BT paired-device list, local BD address, BT stack DB | `/var/opt/public/con/wicome/{pdl.dat,bdaddr.txt,bss.ddb,pss_iuk.cfg}`, 6 files (con_2036) | yes | yes | H path, M meaning |
| Device manager / Wi-Fi hotspot settings | `/var/opt/public/con/con_2010/kvs/kvsdb-*` (3 files); `kvsdb-WifiDefault` = "default wifi password" | yes | **kvsdb-WifiDefault kept**; rest deleted | H (whitelist) |
| Telephony settings | `/var/opt/public/con/con_2011/...` (1 file) | yes | yes | M |
| CarPlay / Android Auto / SDIP data | `/var/opt/public/cia/cia_13002/data/icons/` (CarPlay app icons), `cia_13006` (1 file), `cia_13010/kvs/kvsdb-acl` + 39 files | yes | yes | H path |
| Learning Navigation: trips, trails, destination trees, aggregates | `/var/opt/public/nav/{trips,trails,trees,aggregator,downloaded}.sqlite`. On disk 3 nav_hbnavicore files: 7.3 MiB, 9.3 MiB, 456 KiB | yes | yes (only `nav/hdmap` is whitelisted) | H config, M which file is which |
| Destination memory: last destinations, favourites, home/work | `/var/opt/personal/<profile>/nav/nav_controller/...`, 12 KVS files (8–20 KB) in the active profile | yes ("personal" key, a separate key) | yes (all personal data deleted) | M |
| Last position / positioning calibration | `/var/opt/public/nav/nav_hbpositioning/...` (2 files) | yes | yes | M |
| Media library index for USB, phone and HDD (titles, folders, playlists, favourites, bookmarks, imported device names) | `/mnt/share/ent/database/{default,external,persistent,cdda}`, covers in `/mnt/share/ent/covers` (**HDD**) | **not shown to be encrypted** (no crypto in `hddmgr`) | yes, if the reset is started by the user or a diag job ("Ent: Starting HDD deletion") | H path/schema, M HDD plaintext |
| Spotify / online-media cache | `/mnt/share/ent/oe/spotify` (HDD), `/var/opt/public/ent/...` (ent_spotify dir, empty) | HDD: probably not; eMMC: yes | probably yes (HDD content deletion) | M |
| Media per-profile state (last source, audio settings) | `/var/opt/personal/<profile>/ent/{ent_mapp,ent_audiomanager}` (2 files) | yes | yes | M |
| Driver profiles / BMW ID account metadata (GCID, display name, PIN protection, avatar, key↔profile mapping) | `/var/opt/public/sps/sps_8000/kvs/kvsdb-default`, `.../data/avatars/`, `.../data/prefetch/` (persyncd) | yes | **yes on factory reset**; kept by "delete public data" (`[public]` whitelist) | H |
| Per-profile settings (HMI, OAP apps, speech, tm, os) | `/var/opt/personal/{guest,valet,i01..i07}/<domain>/<app>/...` | yes | yes | H structure |
| Privacy switches (per-feature consent) | `/var/opt/public/sps/sps_8003/...` (1 file) + `/var/opt/personal/<p>/sps/sps_8003` | yes | yes | H |
| Digital-key table from BDC | `/var/opt/public/sps/sps_8004/kvs/kvsdb-group` | yes | **kept** | H (whitelist) |
| Voice: dynamic vocabulary / speaker biometry; possibly contact-name grammars | `/var/opt/public/spe/natp/...`: 90 files, 1.7 MB (spe_9000); `/var/opt/personal/<p>/spe/...` (1 file) | yes | yes | H path, L/M contents |
| Voice: raw audio | only `/tmp/utterance.pcm`, `/tmp/speech/*` (RAM). No persistent audio path found | n/a | n/a | M |
| Drive Recorder clips | `/var/opt/public/ent/driverecorder` (eMMC, **empty**) and `/mnt/share/ent/driverecorder` (HDD) | eMMC yes / HDD probably no | persod calls `SVSRecorder::factoryReset()` | H paths, M reset |
| Remote 3D View / theft-recorder images | no persistent path found on the head unit (only privacy switches `REMOTE_360`, `REMOTE_THEFT_RECORDER`) | — | — | L |
| OAP app data (weather, cmusic, news, smartinterior, privacy_manager, ...) | `/var/opt/public/oap/oap_<uid>/...` (19 app trees, ~295 MB incl. code) + `/var/opt/personal/<p>/oap/<uid>/data` (small) | yes | yes | H |
| **Crash core dumps** (process memory) | `/var/opt/public/sin/crashhandler/{coredumps,gpu_hangs,iDLT}`: 30 files, 22 MB, 4 real dumps of 0.3–9 MB | yes | **NO, whitelisted** (`sin/crashhandler`, `sin/dlt-cdh`). `MaxOldCoreDumps=10` | H |
| Health telemetry events | `/var/opt/public/sin/health_telemetry/event_*.json` (20 files) + `health_sessions.db` | yes | yes | H |
| Recovery-manager stats | `/var/opt/public/sin/recmgr/recmgr_stats.db`, `*.xml` | yes | **kept** | H |
| Internal DLT traces | `/var/opt/public/sin/dlt-daemon` (empty), `/mnt/share/sin/internaltrace` (HDD, size-capped `-d HDDMaxSize`) | eMMC yes / HDD probably no | unknown for HDD | M |
| Telematics provisioning + data-transfer statistics | `/var/opt/public/tm/tm_12000/data/{prov,acm}`, joynr MQTT client-id | yes | **kept** | H |
| Vehicle / coding NvM: VIN, mileage, service history, fault memory (DEM), PIA profile + PIA ID, KDS keys | `/var/opt/public/sf/aol/...` (305 files, 3.7 MB) + `/var/sys/sf/aol/BLOCKS/*`, `/var/sys/sf/aol/tvin_init.bin` | p10: yes; **p12 `/var/sys`: plaintext** | **kept** (whitelist: `block_458 # Vin`, `block_544 # MILE_KM`, `service-history`, `DEM_*`, `block_176 # PIA profile`, `block_192 # PIA ID`) | H |
| Device ID | `/var/opt/target/security-info/device.id` (64 B) | **plaintext** | not touched (outside public/personal) | H |
| GPU shader cache | `/var/opt/target/shader-cache` (616 files) | plaintext | not touched | H (no personal data) |

---

## 2. Phone / Bluetooth

- **PIM DB** (H path, M contents)
  - `pim` (uid con_2000) hard-codes `/var/opt/public/con/PIM.db` and `/var/opt/public/con/PIM_BACKUP.db`.
  - Strings: `initDataBase databaseName = %s ..., databaseBackupName`, `CacheDB backup result`, `Database was restored`.
  - Tables and views embedded in the binary:
    - `SMSTable(accountId,itemId,folderType,time,isRead,…,senderPhone,senderCbId,recipientName,recipientPhoneNumber,subject,body,…)` and `SMSThreadTable`.
    - `EmailTable(itemID,accountID,folder,time,senderEMail,senderEMailName,subject,body,…)`.
    - Views `CallSeparatedModel`, `CallUnifiedModel`, `Contact_names_viewModel`, `LastRecepientsModel`, `CalendarMonthlyViewModel`, `ReminderModel`.
    - Models `ContactModel`, `ContactDataModel`, `AccountModel`, `CalendarModel`, `CallModel`.
  - On disk, `/var/opt/public/con` has:
    - one 204,800 B file (con_2000), modified on the last drive;
    - one 40,960 B file and one empty 8 KB file;
    - a `pictures/` dir (empty);
    - a subdir with 5 small files.
  - Inference (M): the 200 KB file is `PIM.db`, so message, call-list and contact data **is persisted** in encrypted form.
  - `/var/cache/contactbook` is a RAM disk used as the contact-book working area. Whether full contacts persist across power cycles is not proven. The SMS view joins `ContactDataModel` inside the same DB, which points to yes.
- **Bluetooth pairing** (H path, M meaning)
  - `connhelper` (con_2036) lists `/var/opt/public/con/wicome/{bdaddr.txt,bdaddr_tmp.txt,bss.ddb,pdl.dat,pss_iuk.cfg,geniviConfig.cfg}`, `/var/opt/public/con/simplehandsfree` and `version.txt`.
  - On disk: a con_2036 dir with 6 files (≈80 KB), a symlink and a file.
  - `pdl.dat` = Paired Device List (wicome stack). That means MAC addresses, device names and, by inference, **link keys**.
- **devicemanager** (con_2010): 3 KVS files. One is `kvsdb-WifiDefault`, which the reset whitelist calls `# default wifi password to persist`. It survives reset by design (it is the factory hotspot key, not a user key). Personalised eSIM and Wi-Fi state is handled here (strings `Is ESIM personalized:`); I note this only to show it exists.
- **telephonymanager** (con_2011): 1 small file.
- No BlueZ `/var/lib/bluetooth` exists. `/var/lib` on the rootfs is read-only and holds only dbus, connman, udisks2 and nfs.

## 3. Navigation

- **Learning Navigation** (H)
  - `/etc/navcore-euusrow/navigation.ini`:
    ```
    ln-db-aggregator = /var/opt/public/nav/aggregator.sqlite
    ln-db-downloaded = /var/opt/public/nav/downloaded.sqlite
    ln-db-trails     = /var/opt/public/nav/trails.sqlite
    ln-db-trees      = /var/opt/public/nav/trees.sqlite
    ln-db-trips      = /var/opt/public/nav/trips.sqlite
    ln-maximum-databases-size = 104857600   (100 MiB cap)
    ln-maximum-mileage        = 100000000
    ```
  - The ini comments describe recorded trips with start and destination location, time-of-day and day-of-week similarity, commuter routes, and stop-as-destination detection (≥1800 s).
  - On disk: 3 nav_hbnavicore files directly in `/var/opt/public/nav` (7.6 MB, 9.7 MB, 467 KB ciphertext), all written on the last drive.
  - So this unit holds **about 17 MB of trip/trail history**, encrypted. Retention is capped by size and mileage, not by time.
  - Controlled by the privacy switch `LEARNING_NAVIGATION` (`/etc/dataprivacyd/dataprivacyd-default-settings.json`).
- **Destination memory** (M)
  - NavController strings: `destinationmemory`, `lastdestinations`, `LastDestinationsListController`, `Favourite`, `DestinationMemoryElementContact`, `DestinationMemoryPersistenceClient`.
  - It uses `persistence::PersistenceKvs::onUserChanged`, i.e. a per-user dataset.
  - Matching storage: `/var/opt/personal/<profile>/nav/nav_controller/<kvs>/`, 12 files of 8–20 KB in the active profile.
- **Positioning**: 2 small files under `/var/opt/public/nav` owned by nav_hbpositioning (M: last position / dead-reckoning state).
- Traffic-info persistence is in RAM (`ti-path-to-persistency-db = /tmp/navi/...`). Nav dumps go to `/var/dumps` and `/mnt/share/nav/dumm` (HDD).

## 4. Media

- **Media index** (H schema)
  - `/etc/mediaconfig/mediaindexer-fs.sql`, `-oe.sql`, `-iap*.sql`.
  - Tables: `library(fid,folderid,filename,displayname,vfspath,title,artist_id,album_id,…)`, `folders(…foldername,basepath,…)`, `playlists`, `favourites(fid,userid,favourite)`, `bookmarks(bookmarkid,Userid,fid,time,type)`, `imported_devices(device_unique_id,devicename,displayname)`, `imported_device_partitions`, plus the Gracenote tables.
  - Location (H): `/mnt/share/ent/database/{default,external,persistent,cdda,rse}`, covers in `/mnt/share/ent/covers/hu`, online-entertainment cache in `/mnt/share/ent/oe/{default,spotify}/{appcache,content,covers}`. All on the **HDD** share, which is not in this image.
  - `hddmgr` has no cryptsetup, LUKS or ecryptfs strings, so the HDD share is **probably plaintext ext4** (M).
- **Spotify**: dir `ent_spotify` exists in `/var/opt/public/ent` (empty) and `/mnt/share/ent/oe/spotify`. No account token file was visible on eMMC. Contents are encrypted and unseen.

## 5. Profiles, accounts, settings

- **Profile slots** (H): `persistencydeletiontool` names `UserAccountManager.guest`, `.valet`, `.i01`…`.i07`. `/etc/tmpfiles.d/high/10-recovery-datarw.conf` creates `/var/opt/personal/{guest,valet}/{cia,con,dr,ent,hmi,nav,nodomain,oap,os,sf,sin,spe,sps,tm}`.
- **This unit**: `.personal` holds only 2 profile dirs, so no i0x profile exists.
  - The first dir holds data: 44 files, 557 KB, in hmi, nav, ent, con, oap, sps, spe, tm and os.
  - The second is empty.
  - Inference (M): the first is `guest`, the second `valet`.
- **Account metadata** (H): persod strings `An account with the GCID`, `Authorized account GCID:`, `Changing PIN`, `Cannot save custom avatar`, `Assigned NFC token ID`, `BDC identity mapping table`. The whitelist describes `sps/sps_8000/kvs/kvsdb-default # User account metadata` and `data/avatars # Custom avatars of user accounts`.
- Seat and mirror memory is not stored here. POM (`pomd`, sps_8002) triggers `ResetAll` in other ECUs. Its own `kvsdb-default` ("PIA POM configuration and pending tasks") is **kept** on reset (H).

## 6. Voice

- **natp (Nuance)** (H config)
  - `biometry.json`: speaker-biometry engine (NVSL) with `persistent_storage_directory: ../dynvocab/`.
  - `natp.cfg`: `eco_dirname='/var/opt/public/spe/'`.
  - On disk: `/var/opt/public/spe/natp/...`, 90 files, 1.7 MB, plus 1 file per profile.
  - Inference (L/M): dynamic vocabulary (often built from contact names and media titles) and possibly voice-biometry enrolment.
- **Raw audio**: `logger.json` writes `log_audio_utterance` to `/tmp/utterance.pcm`, capped at 1 MB, RAM only. speechd uses `/tmp/speech/*` and has a `Purging old records...` string. **No persistent recording path was found** (M).

## 7. Cameras / Drive Recorder / Remote 3D View

- `mediaonoff_config_hu.xml`: `DriveRecorderHDD=/mnt/share/ent/driverecorder` and `DriveRecorderEMMC=/var/opt/public/ent/driverecorder` (group `mgu_driverec`).
  - The eMMC dir is **empty** on this unit, which has no Drive Recorder (H).
  - The HDD dir is unknown.
- Recording itself is done by the SVS recorder (`de.bmw.dass.svsrecorder`). persod calls `SVSRecorder::factoryReset()` during a reset (H).
- Remote 3D View / theft recorder: only the privacy switches `REMOTE_360` and `REMOTE_THEFT_RECORDER` were found. No image store on the head unit was found (L, the HDD is unseen).

## 8. OAP apps

- `/var/opt/public/oap/`: 19 app trees (uid 12201 + 12203–12220). Total ≈295 MB of ciphertext, mostly app code.
  - App names by uid (from the running unit): 12208 privacy_manager, 12212 weather, 12214 connected-onboard, 12215 cmusic, 12217 bon-newsnext, 12218 smartinterior, ...
- Per-profile app data: `/var/opt/personal/<p>/oap/<uid>/data/*`, 1–4 small files for 12201, 12208, 12212, 12214, 12215, 12217 and 12218 (≤49 KB each).
- Code and data cannot be separated without decryption, because file names are FNEK-encrypted. All of it is deleted on factory reset, since `oap` is not whitelisted.

## 9. Logs, crash dumps, telemetry

| Item | Path | Limit | Reset |
|---|---|---|---|
| Core dumps, GPU hangs, iDLT | `/var/opt/public/sin/crashhandler/{coredumps,gpu_hangs,iDLT/storage,transfer/.tosend}`, `/var/opt/public/sin/dlt-cdh` | `/etc/crashhandler.ini` `MaxOldCoreDumps=10`; `ArchiveCleanup/MaxCoreDumpSpaceMb` | **kept** (`sin/dlt-cdh`, `sin/crashhandler` whitelisted "core-dumps and context files") |
| Health telemetry | `/var/opt/public/sin/health_telemetry/event_*.json`, `health_sessions.db` | ~20 events on disk (inference: rolling) | deleted |
| Recovery manager | `/var/opt/public/sin/recmgr/{recmgr_stats.db,*.xml}` | — | kept |
| DLT persistent | `PersistanceStoragePath=/var/opt/public/sin/dlt-daemon` (empty) | — | deleted |
| Internal trace | `/mnt/share/sin/internaltrace/` (HDD) | `log-trace-manager -d HDDMaxSize` | unknown |
| journald | volatile | 12 MB, RAM | n/a |

On this unit there are 4 real core dumps (0.3, 0.37, 8.9 and 9.0 MB) (H). A core dump is a copy of process memory, so it can hold whatever that process had loaded. **Which processes crashed is unknown**, because the names are encrypted.

## 10. Vehicle data

- `/var/opt/public/sf/aol/` (AUTOSAR-on-Linux NvM, sf_autosaronlinux): 305 files, 3.7 MB, encrypted.
  - Whitelist entries:
    ```
    block_458 # Vin
    block_544 # MILE_KM
    service-history # Service History File
    block_112 # DEM UDS data
    block_592 # DEM_Admin
    block_176 # PIA profile
    block_192 # PIA ID
    block_5136 # Trusted VIN block
    ```
  - All of these **survive factory reset** by design.
- `/var/sys/sf/aol/BLOCKS/*` (≈20 files) and `/var/sys/sf/aol/tvin_init.bin` (852 B, inference: trusted-VIN init) are **plaintext** on p12. They are mostly coding data and not user data. The VIN is the main identifier here.
- No trip-computer or eDrive efficiency history file was identified on the head unit (L). Those values usually live in the instrument cluster or other ECUs.

---

## 11. Encryption

- **Mechanism** (H)
  - `persistencydecryptiontool(-personal).service` run at boot: `-k /var/opt/.public.edeka -m /var/opt/public -c /var/opt/.public` and the same for `.personal`.
  - `libedeka.so` mounts with `ecryptfs_cipher=aes,ecryptfs_key_bytes=32,ecryptfs_fnek_sig=…,ecryptfs_passthrough,ecryptfs_unlink_sigs`. That is AES-256 with **file-name encryption**: all 11,800+ lower names are `ECRYPTFS_FNEK_ENCRYPTED.*`, and no plaintext passthrough files were found.
  - Two separate keys: public and personal.
- **Key protection** (H/M)
  - The 146-byte `.edeka` files hold the disk key wrapped by a "keystore key". Strings: `Cannot read keystore key. Edeka corrupted`, `Loading edeka from disk...`.
  - The services depend on `dev-keystore.device`, so the key is device-bound in hardware. Earlier work on a live unit confirmed it cannot be recovered offline.
  - **The key is unlocked automatically at every boot, with no user secret.** So the encryption only protects against reading the eMMC or a dump offline. It does not protect against anyone who runs code on the unit.
- **Plaintext on eMMC** (H)
  - `/var/sys/*`: coding blocks, VIN-related, keys/certs (existence only).
  - `/var/opt/target/security-info/device.id`.
  - The shader cache.
  - Empty mount-point skeletons `/var/opt/personal/{guest,valet}`.
  - Quota files.
  - No personal content is in plaintext on eMMC.
- The **HDD share** is probably not encrypted (M), which means the media index, covers, Spotify cache, drive-recorder clips and traces may be plaintext.
- `.edeka` sits outside `public/` and `personal/`, so **the disk key is not rotated by a factory reset** (H, inference from the deletion tool's scope). p10 is mounted with `discard`, so freed blocks are TRIMmed (lowers the chance of recovering deleted files).

## 12. Reset / delete behaviour

Flow (H, from strings):
1. HMI or a diagnosis job calls `DeletionManager.deleteAllData(DeletionCause)`. Other entry points: `deleteAllDataForCurrentUser`, `deleteAllPublicData`, `deleteApplicationPublicData`.
2. persod (`factoryreset.cpp`) runs these steps:
   - Backend: "Dissociating VIN" (if the backend URL is known).
   - POM `ResetAll` (only if the user started it).
   - Ent: `Starting HDD deletion` via `MediaContentManager.deleteDeviceContent`. This runs only if the initiator is the user or a diag job, and only if an HDD is fitted.
   - AuthProvider: delete key-to-profile mappings (skipped if started by diag).
   - `SVSRecorder::factoryReset()`.
   - Then it writes the flag file `/var/opt/public/sps/sps_8000/data/factoryreset.ini` and requests a node restart (`nsmRequestNodeRestart`).
3. On the next boot, `persistencydeletiontool.service` starts only if `ConditionPathExists=…/factoryreset.ini`. It runs `persistencydeletiontool --use-config-file -v` before `basic.target`, with the volumes already decrypted, then runs `systemd-tmpfiles --create` to rebuild the skeleton.
   - It removes everything under `/var/opt/personal` and `/var/opt/public` **except** the `[factory_reset]` list in `/etc/factoryreset_whitelist.ini`.
   - Deletion is a plain recursive unlink (`removeDirUseWhitelist`, `Removed file`). There is no shredding, only TRIM through `discard`.
   - Failure sets `DTC_UNABLE_DELETE_PERSONAL_DATA`.
4. **Kept on factory reset** (the whitelist): Wi-Fi default password, HD map, graphics coding, NvM blocks (VIN, mileage, service history, fault memory, PIA profile/ID, KDS keys), `sf/CodingHWPKey`, core dumps (`sin/dlt-cdh`, `sin/crashhandler`), ethernet port map, IPsec config, recmgr XML/DB, trace flags, the reset flag itself, POM tasks, BDC digital-key table, necema certificates, RSU session, sps_secdiag debug token, telematics `acm` statistics and `prov` provisioning, joynr client-id settings.
5. Never touched by the eMMC deletion tool: `/var/sys` (p12), `/var/opt/target`, `.edeka` keys, and HDD dirs other than the media-content deletion (nav/tm/sin/oap on `/mnt/share` — unknown).

## 13. What a used-car buyer, a workshop, or someone holding the unit could recover

- **Offline (eMMC chip-off / dd, no running unit):**
  - Visible: the file tree shape, owners, sizes and timestamps. For example, that a ~200 KB PIM DB exists, that ~17 MB of Learning-Nav history exists, and when each was last written. Also the 20 health-event timestamps and the core-dump dates.
  - Plaintext: `/var/sys` coding/VIN-related blocks and the device ID.
  - Not visible: any content of contacts, messages, trips or destinations, which are AES-256 with a device-bound key.
- **With the unit powered and a root shell** (as was done during this research): everything is decrypted live at boot, so all of the above is readable in plaintext. This includes the PIM DB, BT paired list (with link keys), Learning-Nav trips and trails, destination memory, voice data and app data. If the previous owner did **not** factory-reset, the buyer gets all of it.
- **After a proper factory reset:** personal data is unlinked. What remains is VIN, mileage, service history, fault memory, core dumps, telematics provisioning and stats, recmgr stats, and the BDC key table. **Core dumps** are the main remaining privacy risk, since they hold process memory that may include personal data.
- **HDD** (if fitted): probably plaintext. It is wiped of user media content only when the reset is started by the user or a diag job. It is a separate disk that can be pulled.
- **Workshop:** diagnosis jobs can trigger a reset (`DiagServiceFactoryResetMgu/Rse`). The NvM data that persists (service history, DEM, mileage) is by design workshop-readable through diagnosis.

## 14. Open questions

1. Is the HDD share really unencrypted? Needs an HDD image or a `mount`/`dmsetup` listing on the live unit.
2. Exact plaintext names and contents of the encrypted files: is the 200 KB con file `PIM.db`? Are contacts persisted or rebuilt by PBAP each time? Which nav file is `trips` vs `trails`? A file listing of decrypted `/var/opt/public` from the live unit (names only) would settle this.
3. Which processes the 4 core dumps belong to, and whether they contain PIM or nav memory.
4. Whether `deleteAllDataForCurrentUser` also removes Learning-Nav data, which is public and not per-profile, or only the profile dir.
5. What spe/natp's 90 files are: dynamic vocabulary vs voice biometry enrolment.
6. Whether the HDD `nav/dumm`, `tm/dumm`, `sin/internaltrace` and `oap` dirs are cleared on reset.
7. Snapshot caveat: one point-in-time image. The car has no user profile (only guest/valet) and no Drive Recorder, so those stores are empty here but would fill on other cars.
