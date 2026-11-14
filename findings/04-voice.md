# 04 — Voice control / speech system / microphones

Scope: BMW Intelligent Personal Assistant ("Hey/Hello BMW", PTT button, "Active speech processing"), online (hybrid) speech, Alexa/third-party assistant, microphone consumers.
Method: static, read-only analysis of a stock MGU eMMC image (root fs p8, speech data on p9 `/dataro1/spe`, persistence p10), extracted `/etc`, and OAP apps / someipInterfaces pulled from the car. Nothing was executed. The car's actual setting values are in encrypted (ecryptfs) personal storage and were **not** read, so what the car is doing right now is not known.

Labels: **[code]** = code/config present · **[default]** = default value shown by evidence · **[gated: X]** · **[inferred]** = my reading, not proven · **[unknown]**. Confidence: H/M/L.

---

## Direct answers

### Is it always listening?
- **Only if a wake-word or "Active speech processing" feature is switched on. Then yes: the mic is processed all the time, on the head unit.** Two always-on modes exist:
  1. **Wake word** ("Hello/Hey BMW" or a personal wake word). The Nuance/Cerence VoCon recognizer runs a "gate" grammar on the live mic stream and never times out. [code, H]
  2. **"Active speech processing"** (`ALWAYS_LISTENING`, recognizer use cases `ALWAYS_ON` / `ALWAYS_ON_WUW`, NLU "JUST_TALK"). It recognises commands without a button press or wake word, using a vocabulary downloaded from the BMW backend. [code, H]
- Wake-word detection is **on-device** (local grammar `wuw.fcf`, local acoustic model, local speech-enhancement configs `*_wuw.scd`). I found no sign that audio is streamed off the car *before* detection. [code, H for on-device; M for "nothing leaves before detection", because absence was checked in config only]
- Audio before the wake word sits in RAM buffers only: the Nuance AudioInput buffer defaults to 30 s (`buffer_time` default 30000 ms; the car's config doesn't override it), and the prompt-sync buffer is 1.5 s. I found no code path that saves pre-wake-word audio to disk. [code, M]
- The privacy-manager logic sets **all three speech settings off by default** ("sensitive" settings start disabled and need confirmation). Whether the user has turned them on is unknown. [default, M-H]

### Is voice sent to BMW?
- **Yes, when "Online speech processing" (`SPEECH`) is on.** The system is **hybrid**: recognition and NLU run locally first, and an on-device "server gate" grammar plus an `Offboard` domain decide when an utterance goes to the cloud. [code, H]
- **What goes:** **compressed audio** (Opus in Ogg, 16 kHz). The upload templates also name SPEEX_16K. Along with the audio go request metadata: the **VIN** (`BMW-VIN` header), a speech UUID, a guest flag, language, **current position, destination, route coordinates, ETA**, time/timezone, parking/IPA context, and the wake-up phrase / "prefix phrase to remove". [code, H for the fields being defined; the values actually sent are unknown]
- **Path:** NATP (Nuance engine) → local HTTP proxy inside `speechd` at `127.0.0.1:2031` → libcurl, using a client certificate → URLs from **BMW telematics provisioning** (`speech2text.hvd_url`, `htts_url`, `dictation`, `third_party_keywords`). The UI text says audio is processed "on BMW servers". The protocol is Nuance/Cerence ("NVC", "DRAGON_NLU_*", "Cerence Studio" JSON), so the backend is probably BMW-fronted Cerence (inferred). **No hostnames are hard-coded**: they come from provisioning. [code, H for the path; M for the vendor behind it]
- **Other uploads (gated separately):** phonebook names (to "provider Cerence"; default **off**), favourite POIs, and a "VCM" vehicle profile. Downloads: wake-word/"Always On" vocabulary, third-party keywords, language lists. [code, H]
- **Alexa / third-party assistant:** audio is recorded locally to `/tmp/speech/third_party.pcm`, encoded to Opus and sent over HTTP to a provider set by provisioning. The UI says "every spoken word is processed by the third party provider (e.g. Amazon Alexa)". This needs account linking in the BMW app. [code, H]

### Can I turn it off?
Yes. There are three separate privacy toggles (managed by `dataprivacyd`, shown under My Vehicle → Data privacy):

| Toggle (UI) | Setting ID | Effect when OFF (UI text) |
|---|---|---|
| Wake word / "Activation word" | `WAKEUP_WORD` | "You can no longer start voice control with 'Hello BMW' or your personal wake word." |
| Active speech processing | `ALWAYS_LISTENING` | No recognition "without previous activation via button … or saying the wake word" |
| Online speech processing | `SPEECH` | "Online speech processing is not carried out" (local-only recognition) |

There is also a per-phone toggle for sending contact names to Cerence. With all of these off, the mic is used for speech only after the PTT button is pressed, and only by local recognition. (Inferred from the UI text and the use-case design; not verified at runtime.)

---

## Summary table

| # | Claim | Label | Conf. |
|---|---|---|---|
| 1 | Embedded Nuance/Cerence stack: VoCon3200 ASR, embedded NLU (SLM grammars per language), SSE speech enhancement, TTS, all on-device (~880 MB in `/dataro1/spe`) | code | H |
| 2 | Wake-word ("Hello BMW" + personal word) detection runs locally; gate never times out while active | code | H |
| 3 | "Active speech processing" (ALWAYS_ON / JUST_TALK) = continuous local recognition without wake word; vocabulary downloaded from backend; its top-level use case includes the `Offboard` domain | code | H |
| 4 | Wake word, active listening and online speech all start disabled (sensitive → `initialEnabled=false`; `wakeup_word_setting.json` missing → `enabled=false`) | default | M-H |
| 5 | Pre-wake-word audio: RAM ring buffers (AudioInput default 30 s, prompt-sync 1.5 s); no persistence found | code / inferred | M |
| 6 | Online speech = hybrid; audio Opus/Ogg 16 kHz via local proxy 127.0.0.1:2031 → provisioned BMW speech URLs (mTLS client cert) | code | H |
| 7 | Request metadata fields include VIN, position, destination, route, ETA, time, parking/IPA context, wake phrase | code (fields) | H / values unknown |
| 8 | Online speech gated by privacy `SPEECH` ("offboard flag"), a backend subscription ("No subscription to online speech processing"), provisioning, and signal quality; otherwise it falls back to local recognition | code | H |
| 9 | Phonebook-name upload to Cerence: separate per-device "phonebookSync"; code default false | code/default | H |
| 10 | Local persistent speech data: phonetic DBs of contacts/media, context DB, ASR caches incl. automatic speaker/environment adaptation, downloaded vocab JSONs; on `/var/opt/public/spe` (ecryptfs) and personal storage | code | M-H |
| 11 | Debug logger configured to write last ASR utterance PCM to `/tmp/utterance.pcm` (RAM tmpfs, ≤1 MB ≈ 31 s) | code; active at runtime unknown | M |
| 12 | Temp audio files for Alexa/cloud TTS in `/tmp/speech/` (tmpfs, RAM) | code | H |
| 13 | Voice biometry (speaker ID / voiceprint) engine + config present, but the model file `NVSLv5_*.nsrpkg` is not in the image → probably inactive | code / inferred | M |
| 14 | China: a separate embedded NLU (ENLU, `cmn_CN/model`); Tencent audio sources/sinks named in speechd; Baidu CarLife | code | M |
| 15 | OS-level mic access (`mgu_alsa` group): speech (spe_9000), BT hands-free (wicome/psse), CarPlay, Android Auto, CarLife, media/SXM processes. OAP app UIDs are **not** in it | code | H |
| 16 | OAP apps get speech access only at intent/command level (Recognizer, ExternalDialog, IPAMaster, Dialog.wakeUpWordEvent) via SOME/IP. No raw-audio interface found | code | M-H |

---

## Evidence

### E1. Speech processes and engine (on-device)
- `/lib/systemd/system/speechd.service` (root p8):
  ```
  ExecStart=/usr/bin/speechd
  Group=mgu_speech
  User=spe_9000
  ```
  `natp.service`: `ExecStart=/usr/bin/natp -f /etc/natp/natp.cfg …` (Nuance "NATP" host for DragonDrive ASR/Prompter/ENLU services). Both start only on hwvariant high/highf/mid and only when `/mnt/dataro/data/spe/dialog/BMW_MGU*.gdd` exists. Both are `WantedBy=late.target`, i.e. they run on every boot.
- `/usr/lib/natp/`: `libvocon3200_asr.so`, `libdragondriveasrservice.so`, `libhybrid_nlu.2.0.0.so`, `libnds_cloudservices.so`, `libsse.so`, `libdragondrivebiometryservice.so`, `libNVSLEngineLib.so`, `libenluservice.so`.
- Data on p9 `/dataro1/spe/`: `bsd/` (SSE tunings incl. `bmw_mgu_sse_generic_generic_1mic_wuw.scd`, `…_2mic_wuw_pic.scd`), `grammar/<21 languages>/` (acoustic models `acmod/model.dat`, NLU `.s3c/.fcf`, `wuw.fcf`, `just_talk.fcf`, `Gate_Intents.*`, `Strict_Server_Gate.fcf`, `CloudRef.s3c`), `dialog/BMW_MGU.gdd`, `tts/`.
- `speechd` NEEDED libs include `libNuanceApi.so libNmeSDK.so libopus.so.0 libogg.so.0 libcurl.so.4 libcertmanager.so …dataprivacy.privacysettings.proxy… …contactbook.proxy… …calllist.proxy… …telematic.provisioning.proxy… …TMUSSO.proxy… …navigation.positioning.proxy…`.

### E2. Wake word / always-on use cases
- `/dataro1/spe/grammar/en_US/json/usecases.json`, use case `UC_WUW`:
  ```
  "type": "wuw", "wuw": {"block_on_wuw": "true", … "context": [{"uses": "WAKE_UP_WORD_CONTEXT"}], "usecase": {"uses": "UC_TopLevel_WUW"}
  "comment_1": "… A gate recognition should never stop, unless the gate is recognized"
  "LH_AUDIOSOURCE_PARAM_TIMEOUT": 0, "LH_FX_PARAM_TIMEOUT_SPEECH": 0, …
  ```
  `UC_TopLevel_WUW` domains: `Intent_Groups, Gate_Intents, Navigation, …, POI`, with **no** `Offboard` (it is processed locally). `UC_TopLevel` (normal dialog) **does** include `Offboard`.
- `usecases_jt.json`: `UC_JUST_TALK` (`"FB_RECOG_BACKGROUND_WUW_AND_JUST_TALK"`, same never-stop parameters, `just_talk.fcf` + local wake word). `UC_TopLevel_JUST_TALK` uses context `Strict_Server_Gate.fcf` and domain list `["Offboard","Intent_Groups",…]`. So in active-listening mode, a local strict gate decides, and matching utterances can then go to the cloud. [code H; flow inferred M]
- The Recognizer SOME/IP interface (`oap_12203/someipInterfaces/de_bmw_infotainment_speech_recognizer_Recognizer.json`): `switchUsecase` enum `{"ALWAYS_ON": 4, "ALWAYS_ON_WUW": 5, "DIALOG": 1, "MESSAGE_DICTATION": 2, "NOT_ACTIVE": 0, "WAKE_UP_WORD": 3}`; event `commandDetected.origin {"DEFAULT","JUSTTALK","KEYWORD","PTT","SOFTKEY"}`.
- speechd strings: `Start switching use case to wake up word`, `Start switching use case to always on`, `Pausing WuW (if running)`, `Not in Dialog/WAKE_UP_WORD/ALWAYS_ON use case - rejecting`, `New Always On vocabulary available`, `Always On vocabulary from joynr provider returned`, `alwaysonvocab.json`.
- The AudioManager gives speechd a `NoWakeUpWord` / `MicrophoneReady` sound property (`Current WuW properties: noWakeUpWord =`), so the wake word is suspended while the mic is busy, e.g. during calls. [code M]
- The audio path for wake word (`/etc/natp/json/audioconfig_hw.json`, scenario `audioscenario_asr_with_signals_wuw`): `SDS_1mic_6ref` (`plug:smartx:SpeechSink_CF_1MIC_6REF`, 24 kHz 7ch = 1 mic + 6 loudspeaker references for echo cancellation) → `ASR_src_6ch` → `SDS_sse_wuw` → `audio_signal_analysis` → `SDS_asr`. There is no file sink in this path.

### E3. Pre-wake-word buffering
- `audioconfig_hw.json`: `{"type": "PromptSyncedInput", "name": "psi", … "buffer_time": 1500}`. The `AudioInput` modules have no `buffer_time` set.
- `libnds_audio.so` embedded schema: `"nuance::audio::IAudioInputConfig" … "buffer_time":{"default":30000,…}`; `ICutterConfig … "desired_audio":{"default":"ALL","enum":["ALL","WUW","COMMAND"]}, "ring_buffer_time":{"default":10000}`. No `Cutter` module is configured. Strings: `nuance::audio::RingBuffer`, `CUTTING_WAKE_UP_WORD`, `CUTTING_ALL_AFTER_WUW`, `BoWuW=%d ms`.
- Reading: the capture buffer holds up to about 30 s of mic audio **in RAM**. When the wake word is detected, the recognizer uses audio from the beginning of the wake word onward. The cloud request has `wake_up_phrase` / `prefix_phrase_to_remove` fields, which suggests that cloud-bound utterances may include the wake phrase and the server strips it. **I found nothing that writes pre-detection audio to storage or sends it anywhere.** [inferred M]

### E4. Hybrid / cloud path
- `/etc/natp/json/en_US/cloud_services.jsoc` (binary JSOC; readable tokens): `BMW_MGU_CLOUD … http … ENCODING_OPUS encoding CONTAINER_OGG container … http_url_callback http://127.0.0.1:2031/`, sample rate 16000.
- `/dataro1/spe/grammar/en_US/json/connection_info.json`:
  ```
  "domain": {"name": "Offboard", "type": "cloud", "cloud": {"cloud_services_name": "BMW_MGU_CLOUD", "query": {"command": "DRAGON_NLU_ASR_CMD", …
  ```
  REQUEST_INFO fields (flattened): `location_points.route.coordinates`, `location_points.destination.coordinates`, `…destination.eta`, `appserver_data.locationContext.currentPosition`, `…custom.genericBmw` (parking callback), `…custom.ipaBmw`, `…custom.oemPayload`, `time`, `timezone`, `wake_up_phrase`, `prefix_phrase_to_remove`, `return_nlu_results=1`. Several of these default to `"off"`, which suggests they are filled at runtime by callbacks.
- speechd (`speechd/offboard/speechproxy.cpp`): `Only chunked transfer encoding is supported in Speech Proxy`, `Accepted new connection from`, `127.0.0.1`, `forwardBackendReply`. Headers: `BMW-VIN`, `X-Speech-uuid`, `X-Speech-Guest`. TLS: `/tmp/speech/offboard/client.crt`, `initCertificate` (contents not read).
- Provisioning keys (speechd `offboard/configuration.cpp`): `speech2text`, `hvd_url`, `dictation`, `htts_url`, `ext_providername`, `ext_poi`, `ptt_version`, `third_party_keywords`, `cd_account`/`homecountry`; log `Use the Urls from provisionings:`. A joynr interface `com.bmw.cc.inf.speech.hvd.v03` is used for vocab/keyword downloads.
- Templates inside speechd: `"cmdName": "NVC_SERVICE_CMD"`, `"inCodec": "SPEEX_16K"`, `"cmdName": "DRAGON_NLU_DATA_UPLOAD_CMD"`, `"name": "bmw_vcm_server"`; plus `Cerence Studio Json _session cookie`.
- `libnds_cloudservices.so`: `Audio UP-stream config: codec(cloud)=%s`, `AudioToHttpChannel.cpp`, and modules `NvcCloudDataUpload`, `NcsCloudDataUpload`, `CloudLogger/Log2Cloud`. No Log2Cloud consumer is configured in `/etc/natp/json/logger.json` (only DLT and the file below). [code; Log2Cloud apparently unused, M]
- Signal/connectivity: `Too weak signal, set active connection flag as false`, `Offboard recognition is not possible.`, `Could not start fallback to onboard`, `Failure while playing the chunk, retrying onboard`. Offline, the system falls back to the embedded engine; `UC_TopLevel_NoRemote` = top level without `Offboard`.
- Transport: speechd uses libcurl to provisioned URLs. Its links to `conntelematicssync`, `TMUSSO` (single sign-on via the telematics unit) and `signalquality` indicate that the data goes out over the telematics modem link. [inferred M; routing is covered by the network agent]

### E5. Gating / consent
- `/etc/dataprivacyd/dataprivacyd-default-settings.json`: `"SPEECH": "USER", "WAKEUP_WORD": "USER", "ALWAYS_LISTENING": "USER"`. These values are the **scope** (per driver profile vs per vehicle), not on/off. Defaults come from coding/code (`dataprivacyd`: `Coding failed to initialize, using default values!`).
- Car app `privacy_manager/javascript/app.js`:
  ```
  SpeechAssistants_SpeechRecognition:{sensitive:!0,levels:{default:3,…},…settings:["SPEECH"]}
  SpeechAssistants_SpeechActivation:{sensitive:!0,levels:{default:3},…settings:["WAKEUP_WORD"]}
  SpeechAssistants_ActiveSpeechRecognition:{sensitive:!0,levels:{default:4},…settings:["ALWAYS_LISTENING"]}
  ```
  ```
  get initialEnabled(){… return this.sensitive&&!…TC114…?(…,!1):level<3}
  ```
  ```
  'Looks like file "wakeup_word_setting.json" doesn't exist. Hence applying default value enabled=false'
  ```
  → All three are sensitive, so they start **disabled** and require user confirmation. CHANGELOG: `DPMINTERN-796 - Hotfix for speech setting WAKEUP_WORD`. [default M-H; the user's current values are unknown]
- speechd ↔ privacy: `setOffboardFlagForPrivacyProxy`, `offboardFlagChangedByDataPrivacy`, `offboardFlagChangedByHMI`, `Offboard flag setting is false.`, `Not preconnecting since offboard recognition is not possible.` → the `SPEECH` privacy setting = speechd's "offboard flag". [code H]
- Contract/backend: UI `No subscription to online speech processing.`, `Sending text messages not possible as online speech processing is deactivated.`; speechd `Speech provisioning is still missing`, `Third party is not enabled from provisioning.`
- UI text (`/dataro1/hmi/bmw/db/text.db`): "Set your personal wake word. By using a personal wake word, every spoken word is processed by the speech system locally in the vehicle or possibly online on BMW servers." / "By saying 'Hello BMW' … the voice control listens for the wake word." / "Active speech processing recognizes voice commands without previous activation via button on the steering wheel or saying the wake word."
- China: `natp.cfg` `ENLUService.DataStorage = /mnt/dataro/data/spe/grammar/cmn_CN/model/` (encrypted `*.model.Enc`), speechd `Is China :`, `TencentSpeechSource`, `TencentSpeechSink`, `TencentVoiceNotesSink`, `TencentTTSSource`. I did not find which cloud vendor serves China; it is set by provisioning. [code M; vendor unknown]

### E6. Data uploaded for recognition ("data upload")
- Phonebook: speechd `offboard/phonebookuploader.cpp`, `Sending Phonebook HTTP request`, `Sending the HTTP request to delete all phonebook data from backend`, `DRAGON_NLU_RESET_USER_PROFILE_CMD`, `Setting default values(false) for phonebookSync`. UI (mobile-device menu): "Transferring the names of your contacts to provider Cerence improves speech recognition." [code H; default off H]
- Favourite POIs: `favoritepoiuploader.cpp`, `FavouritePois successfully uploaded`, `pal_favouritepoi.json`.
- VCM: `vcmuploader.cpp`, `Sending VCM upload HTTP request`, input `/mnt/share/hmi/vcmprofile` (+`vcmisteps`; present on p10 `hdshare/hmi`, 232 B binary). Meaning of VCM (probably a vehicle capability/config profile for the cloud NLU) is unknown.
- Media/radio/contacts are also **phonetized locally** for the on-device grammar (`PhonetizeAddressBook`, `PhonetizeMedia`, harvesters for contactbook/calllist/tuner) → `/tmp/speech/eco/%1-%2.eco`, `phoneticdata/index-*.db`.

### E7. Local storage / retention
- Persistent (speechd/natp): `contextdatabase-*.db`, `phoneticdata/%1-%2-%3-*.db` (phonetic index per device/domain; table `index(… "deviceId" BLOB, … "lastAccess" DATETIME …)` → contacts/media vocab per phone), `loaded_addressbooks.json`, `keywords.json`, `alwaysonvocab.json`, `*languages.json`, `loaded_vcm.json`, `checksum.json`. speechd links `libFileStoragePersonal`/`libKeyValueStoragePersonal` (per-driver-profile storage).
- ASR caches (`/etc/natp/json/toplevel.json`): `context_cache`, `lexcache`, `envadapt`, `spell_tree`, `dictionary_cache`, all with default `/var/opt/public/spe/%LANG%/`. `asr.json`: `"LH_REC_PARAM_SPEAKER_ADAPTATION" : "LH_REC_SPEAKER_PROFILE_AUTOMATIC"` → an acoustic speaker/environment adaptation profile is learned and cached on the device. [code H; contents unknown]
- `/var/opt` = p10 (`fstab`), and `/var/opt/public` + `/var/opt/personal` are ecryptfs (device key). On the stock image the plaintext dirs `/personal/{guest,valet}/spe` and `/hdshare/spe` are empty. Encrypted contents were not inspected.
- Removal of vocab data: `unloadByDeviceId`, `Purging old records...`, `DELETE FROM %1 WHERE %2 IN (SELECT … ORDER BY … LIMIT 0, %3)` → LRU purge of phonetic data (limit unknown). Vehicle reset clears it (`Vehicle has not been reset.` / `checkVehicleResetPersistencyData`).
- **Audio on disk:** nothing persistent found. RAM-only (tmpfs, `tmp.mount` `Type=tmpfs`) temp files:
  - `/etc/natp/json/logger.json`:
    ```
    "name": "log_audio_utterance", "output": "/tmp/utterance.pcm", "max_file_size": 1000000,
    "modules": "nuance.audio.SinkPad.SDS_asr", "zones": "LOG_DATA"
    ```
    If this logger zone is active, the last ≤1 MB (~31 s at 16 kHz/16-bit mono) of recognizer input is kept in RAM until overwritten or the unit reboots. Whether it is active at runtime is unknown; check on the car with `ls -l /tmp/utterance.pcm`.
  - speechd: `/tmp/speech/third_party.pcm`, `/tmp/speech/thirdParty_encoded.opus` (Alexa forwarding), `/tmp/speech/soundofbmw.opus`, `/tmp/speech/converted.mp3.wav` (cloud TTS), `/tmp/speech/vcmdata.json`.
  - `audioconfig_hw.json` defines `audioscenario_asr_to_file*` scenarios (tee to `toFile`), but no `toFile` module is defined in the hw config. This looks like a dev/diagnostic leftover. [inferred M]
  - Recognizer has a `storeRecognitionFiles()` method (no params, granted to trigger_service). Its purpose is unknown; possibly a diagnostic dump.
- Voice biometry: `/etc/natp/json/biometry.json` `"model_file": "NVSLv5_TD_MOB_16kHz_v1.2.nsrpkg", "persistent_storage_directory": "../dynvocab/"`. Intents `INTENT_Gen_CreateVoiceprint/DeleteVoiceprint` exist. The model file is **absent** from `/dataro1/spe` → the feature is probably not functional on this build. [inferred M]

### E8. Microphone consumers
- OS level: smartx shared-memory audio, group `mgu_alsa` (`/etc/smartx_config.txt` `[shm] group=mgu_alsa`). Members (`/etc/group`): `spe_9000` (speechd/natp), `con_2026` (wicome BT/HFP), `con_2033` (psse "SimpleHandsfree Process (Speech Signal Enhancement)", `com.nuance.handsfree`), `cia_13002/13005/13006` (= `carplay`, `aapd` Android Auto, `carlife`), `ent_mapp/ent_meng/ent_msxm/ent_waveplayer/ent_alsaroutingadapters`. HFP PCM devices in `/etc/asound.conf` (`HFPSource_1_CF_24_MONO` …).
- Hands-free SSE tunings: `/etc/simplehandsfree/type*/…_bt_tel_wb.bsd`, `…_carplay_siri.bsd`, `…_onlydriver_carplay_siri.bsd` → the car mic feeds BT calls, CarPlay calls, and Siri/Google Assistant on the phone (that audio goes to the phone vendor).
- eCall: no MGU-side eCall audio service found (only the speech intent `INTENT_Com_OutOfAction_PlaceEmergencyCall`). eCall is probably handled by the telematics unit. [unknown]
- ANC/road-noise: nothing found on the MGU. [unknown]
- **OAP apps:** their UIDs (122xx) are not in `mgu_alsa`/`audio`. Their SOME/IP speech permissions (per-app `someipInterfaces`, trigger_service `manifest.json`) are at intent level:
  - `Recognizer` (startRecognition → intents, `commandDetected`, `microphoneLevel`, `switchUsecase`, `storeRecognitionFiles`): oap_12203 (trigger_service), oap_12218 (smartinterior)
  - `Dialog` incl. `wakeUpWordEvent`, `wakeUpWordRecognition`: trigger_service
  - `IPAMaster.setIPAState`: 12203, 12218, 12220
  - `ExternalDialogService/Instance` (register dialog, global intents, `newRecognitionResult`): 10 apps
  - `org.genivi.am.commandinterface.CommandControl` (audio routing connect/disconnect): 7 apps
  - `Telephone`/`VoiceCall*`: up to 19 apps (call control, not audio)
  
  No interface that delivers raw mic PCM to an app was found. An app with Recognizer access could switch the recognizer use case, e.g. to ALWAYS_ON (inferred; whether speechd enforces the privacy settings for such calls is unknown). OAP SDK `StartReason.SPEECH_COMMAND` = apps can be launched by voice. (For uid 12203 the uid↔name mapping is less certain.)

---

## Open questions / runtime checks (on the car, read-only)
1. The actual current values of `SPEECH` / `WAKEUP_WORD` / `ALWAYS_LISTENING` for the active profile (shown in the Data privacy menu; or the privacy_manager personal JSON incl. `wakeup_word_setting.json`).
2. Does `/tmp/utterance.pcm` exist and keep growing? That would show whether the debug audio logger is active.
3. The provisioned `speech2text` URLs (hostnames only), i.e. whether they point at a BMW domain or a Cerence domain. The network/telemetry agent could capture them from provisioning or DNS.
4. Whether speechd re-checks the privacy flags when an OAP app (trigger_service/smartinterior) calls `switchUsecase(ALWAYS_ON)`, or trusts the HMI.
5. What `storeRecognitionFiles()` writes, and where.
6. What the VCM profile upload contains, and how often phonebook/POI uploads happen.
7. The China cloud vendor (Tencent?) and whether Tencent sinks receive mic audio.
8. The exact transport (TCU APN vs Wi-Fi hotspot) for speech traffic.

