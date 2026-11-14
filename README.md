# How much does the stock BMW MGU (iDrive 7) collect?

A static privacy audit of the stock head-unit software: what it reads, what it sends to BMW and others, what it keeps on its own storage, and how voice control works.

- **Firmware:** BMW MGU P18_23w44.2, OAP MainApp 8.3.2
- **Sources:** the stock eMMC image (read-only), the 18 OAP apps pulled from the car, and the extracted OAP SDK
- **Method:** the code and config were read, never run. The stored privacy settings and BMW's configuration were also read from one car's decrypted storage. Nothing was captured on the network, and no personal values (VIN, coordinates, names, keys) are reproduced.
- **Date:** 2026-11-14

The whole study is also one PDF: [MGU-privacy-report.pdf](MGU-privacy-report.pdf). Details and evidence are in four reports:

| File | Covers |
|---|---|
| [findings/01-oap-apps.md](findings/01-oap-apps.md) | The 18 BMW JavaScript apps and the app platform: per-app data, destinations, triggers and switches |
| [findings/02-system-services.md](findings/02-system-services.md) | Native services: internet path, firewall, crowd data, telemetry, OTA, debug access |
| [findings/03-stored-data.md](findings/03-stored-data.md) | What is stored on the unit, encryption, what a factory reset removes |
| [findings/04-voice.md](findings/04-voice.md) | Voice control, wake word, online speech, Alexa, microphone users |

---

## Possibly unlawful practices

These findings may conflict with EU privacy law (GDPR and the ePrivacy rules). They describe what the code does. They are not legal conclusions and say nothing about intent; a data protection authority or a court decides what is lawful.

### 1. Data-collection switches turned on without consent

*Confirmed in the code and on the examined car.*

- **The insert:** the crowd-data app (oap-cdc-2018) adds five privacy-menu entries at start-up with `enabled: true, confirmed: false`: product quality, service quality, map quality, online traffic and parking.
  ```
  PrivacyMenuKeys=["CDC_ONLINE_TRAFFIC","CDC_PARKING","CDC_PRODUCT_QUALITY","CDC_SERVICE_QUALITY","CDC_MAP_QUALITY"]
  addOrUpdateSetting({setting:{name:key,enabled:!0,...,confirmed:!1}})
  ```
- **Only when missing:** the app adds an entry only if it does not exist yet, which happens on a new car and after a factory reset. A switch the user turns off stays off.
- **Sent regardless:** every job request carries the VIN, a position rounded to about 5 km and all privacy states, whatever the switches say. No check inside the app blocks job results on these switches. BMW's backend appears to choose jobs from the reported states, but that could not be verified.
- **BMW's own rule:** BMW's privacy app classes these groups as **sensitive**, which means they should stay off until the user agrees.
- **The confirmed flag is ignored:** when the settings are passed to other apps, any switch that is on is reported as `UserEnabled`, the same as a switch the user turned on.
  ```
  someipPrivacySettingToTsPrivacySettingState(s){ return s.available ? s.enabled ? "UserEnabled" : "UserDisabled" : "Unavailable" }
  ```
- **On the examined car:** all five entries were stored as enabled and unconfirmed.
- **What it unlocks:** "product quality" is the switch that gates app analytics, and BMW's configuration on that car had analytics switched on.
- **What was sent:** probably nothing on that car. Its logs show analytics events being dropped, and its crowd-data jobs ran 1,185 times and produced no events.
- **Why it matters:** consent under GDPR must be an active opt-in. The EU Court of Justice held that a pre-ticked box is not valid consent (Planet49, C-673/17).

### 2. Location access switched back on

*Confirmed in the code. Whether it overrides a saved "off" still needs a test on a car.*

- **The reset:** on every privacy-settings change, the privacy app sets Global Location Access to `enabled=true, confirmed=true` whenever the home country is not China, and logs that it did so.
  ```
  glaSetting.confirmed=!0, glaSetting.enabled=!0 ... "GLOBAL_LOCATION_ACCESS set to confirmed=true, enabled=true because home country is ..."
  ```
- **The drive-data app:** it treats location as allowed unless it reads exactly `UserDisabled`.
- **Open question:** it is not clear from the code whether the forced value is written back over the user's saved choice. If it is, the user's "off" is overridden.

### 3. Collection with no switch

*Confirmed in the code.* These flows have no privacy switch:

| Flow | What it sends |
|---|---|
| Weather | Exact position about every 20 minutes or 10 km in the background, whenever BMW enables the service |
| News | Registration, and a position to about 11 km, with the VIN as ID when nobody is logged in |
| Native crowd-data collector | Data for BMW's collection jobs; it is controlled only by the car's factory coding |
| Health telemetry | Hashed VIN and crash data. A hashed VIN is still personal data |
| Software-update report | GPS position when an update fails. The software-update switch is never checked |
| Spotify song recognition | Audio fingerprint, without checking the music statistics switch |

Some of this may rest on a "legitimate interest". GDPR still requires transparency, collecting only what is needed, and privacy-friendly defaults (Article 25). Background location polling with no off switch is the hardest to justify.

### 4. Tracking on by default

The per-drive record (VIN, account ID, exact start and end GPS, driving-style scores) belongs to the History setting, which is **on by default**. That conflicts with data protection by default (GDPR Article 25). On the examined car, BMW's configuration had this use case switched off.

### 5. Smaller points

- **Drive counter:** while sending is not allowed, the drive-data app counts the drives and sends the count with the next record that is allowed.
- **Factory reset:** crash dumps survive it, and deleted files are unlinked, not overwritten.

### What owners can do

- **Ask BMW for your data:** a GDPR **Article 15** request to BMW AG must return everything BMW holds for your account and VIN, including anything these apps uploaded.
- **Complain:** to your national data protection authority, or to BMW's lead authority, BayLDA in Bavaria.
- **Check your switches:** in *My Vehicle → Data privacy*, after any change to the privacy settings.

---

## The short answer

1. **The MGU is built to report a lot, but the BMW backend decides how much of it runs.** Almost every upload needs a signed configuration ("provisioning") pushed by BMW, and most need a working connection through the car's telematics unit. The hostnames are not in the code; BMW sends them.
2. **With ConnectedDrive active, the default is a lot of data.** After every drive the car can send a record with the **VIN, your BMW account ID, the exact start and end GPS position**, times, distance, fuel or electric use and driving-style scores. This "History" use case is **on by default**.
3. **The VIN goes with almost everything**, in clear text.
4. **Some flows have no switch at all:**
   - the weather app sends the exact position about every 20 minutes or 10 km
   - remote diagnosis is started by the backend
   - the software-update report
   - the crowd-data collector, which runs data-collection jobs BMW sends to the car
   - the upload of your privacy settings themselves, every 15 days at most
5. **Voice:** the car is **not** always listening unless you turn on the wake word or "Active speech processing". Both are off by default. Wake-word detection runs on the head unit. When **online speech processing** is on, the **recorded audio of your command is sent to BMW** with the VIN and your position, destination and route.
6. **Stored on the unit:** messages and call lists from your phone, Bluetooth pairings, about 17 MB of learned trip history, destinations and voice vocabulary. It is encrypted, but the key unlocks itself at every boot. A factory reset deletes it, except crash dumps, VIN, mileage, service history and fault memory.

**The examined car** was not signed in to ConnectedDrive, so most of these flows are dormant. Four BMW apps still start without a login (emergency/breakdown call, remote diagnosis, crowd-data collector, trigger engine). Whether they send anything depends on BMW's provisioning for that car, which could not be read.

---

## Voice control

| Question | Answer | Confidence |
|---|---|---|
| Is the car always listening? | Only with **wake word** ("Hey BMW") or **Active speech processing** turned on. Then the microphone is processed continuously, **on the head unit**. Without them, the mic is used for speech only after you press the voice button. | High |
| Does wake-word audio leave the car? | No sign of it. Detection is local (Cerence/Nuance VoCon engine, local models). Audio before the wake word sits in a RAM buffer of up to about 30 s and is never written to disk. | High for local detection, medium for "nothing leaves" |
| Is my voice sent to BMW? | **Yes, if "Online speech processing" is on.** Recognition is hybrid: it starts locally, and a local gate decides when an utterance goes to the cloud. Then compressed audio (Opus, 16 kHz) goes to BMW speech servers set by provisioning. The servers use the Cerence protocol. | High |
| What goes with the audio? | VIN, a request ID, a guest flag, language, current position, destination, route, ETA, time zone and the wake phrase. | High that these fields are defined; values not observed |
| Are recordings kept? | No persistent recording path was found. Temporary audio files live in RAM (`/tmp`) and are gone at power-off. The unit keeps a learned speaker/room adaptation profile and vocabulary built from your contacts and media. | Medium |
| Contacts? | Sending contact names to Cerence is a separate per-phone option, **off by default**. Contact names are also turned into local vocabulary on the unit. | High |
| Alexa? | Audio goes to the third-party provider (Amazon). It needs account linking in the BMW app. | High |
| Defaults | `WAKEUP_WORD`, `ALWAYS_LISTENING` and `SPEECH` are "sensitive" settings, so they start **off** and need your confirmation. | Medium-high |

**To keep voice local:** in *My Vehicle → Data privacy*, turn off the activation word, Active speech processing and Online speech processing. The voice button still works with on-board recognition.

One caveat: two BMW apps (the trigger engine and the smart-interior assistant) can ask the speech system to switch to an always-on mode. Whether the speech system then re-checks your privacy settings could not be confirmed without running it.

---

## What leaves the car

All of this needs BMW's provisioning and a telematics connection. **Default** is the privacy-menu state on a new car outside China.

| What | Data | When | Switch | Default |
|---|---|---|---|---|
| Drive history ("RideHistory") | VIN, account ID, **exact start/end GPS**, times, km, consumption, driving-mode shares, acceleration/braking scores, low-emission zones | End of every drive; keeps up to 300 unsent records for 28 days | `HISTORY` (Mobility). GPS also needs Global Location Access | **ON** |
| Global Location Access | — | — | Has a button, but the privacy app sets it back to on outside China whenever settings change. Whether your "off" survives needs a test on the car | **ON** |
| Privacy settings | All switch states, account ID, VIN | Any change, and at least every 15 days | none | always |
| Crowd Data Collector (app and native) | Job request: VIN, position to ~5 km, options, all privacy states. Jobs can read 169 interfaces, logs, crash dumps and fault codes | Start-up, every privacy change, job conditions (area, mileage, time) | Native part: vehicle coding only. App part: own entries, which it creates as on | depends on campaigns |
| Emergency / breakdown call | VIN, **precise position and recent trail**, destination, vehicle status, passenger count | You press SOS, an accident, or a backend request | none (by design) | per provisioning |
| Remote diagnosis | VIN, ECU data, fault codes; heartbeat with speed bucket, gear, lock state | Started by the backend | none | per provisioning |
| Automatic service call | VIN, mileage, battery, tank, service items, warning messages | Service due, warnings | `AUTOMATIC_SERVICE_CALL` | ON |
| Battery guard | VIN, battery low/deep-sleep flags | Battery wake-up | `BATTERY_GUARD` | ON |
| Software-update report | VIN, update status; **GPS on a failed update** | Around each OTA update | none found | — |
| Software update (OTA) | VIN, mileage, vehicle configuration; logs on backend request | Updates | `REMOTE_SOFTWARE_UPDATE` | ON |
| Weather | **Exact position**, destination, search text | App use and background wake every 20 min / 10 km | none | when provisioned |
| News | Position to ~11 km, account ID or VIN | App use | Interaction events: `MY_PERSONAL_NEWS` (off). Position: none | — |
| Online speech | Audio, VIN, position, route (see above) | Voice commands | `SPEECH` | OFF |
| App analytics | App starts, foreground time, CPU/memory, crashes; one channel uses SHA-1 of the VIN as ID | Continuous | `CDC_PRODUCT_QUALITY` | OFF |
| Health telemetry | Hashed VIN, crash records, reset reasons, eMMC wear | Continuous | none | collected locally, sent through the crowd collector |
| Spotify song recognition | 4 s audio fingerprint, VIN | You ask for it | none | — |
| Nearby dealers | Current position | You search | — | user action |
| BMW messages | Read/clicked/deleted receipts with VIN and account ID | You act on a message | none | — |

**Network facts:**
- The head unit reaches the internet only through the telematics unit (one VLAN).
- A firewall lets only a list of user IDs out: the telematics service, the BMW apps, the messaging bus, speech and a few media services.
- Phone Wi-Fi does not give the head unit internet.

---

## What is stored on the unit

| Data | Encrypted | Removed by factory reset |
|---|---|---|
| Phone messages, e-mail, calendar, call lists (PIM database, about 200 KB here) | yes | yes |
| Bluetooth paired devices (names, addresses, probably link keys) | yes | yes |
| Learned trips and destinations (about 17 MB here, capped at 100 MiB, no time limit) | yes | yes |
| Last destinations, favourites, home/work per profile | yes | yes |
| Voice vocabulary from contacts and media, speaker adaptation | yes | yes |
| Driver profiles, account metadata, avatars | yes | yes |
| Media library index and covers (hard disk, if fitted) | probably **no** | only if you start the reset |
| **Crash dumps** (process memory; 4 on the examined unit) | yes | **no** |
| VIN, mileage, service history, fault memory | partly plaintext | **no** (by design) |
| Telematics provisioning and statistics | yes | no |

- **Encryption:** AES-256 with a device-bound key, but the key **unlocks automatically at every boot** with no PIN. It protects against someone reading a removed chip. It does not protect against anyone who can run code on the unit.
- **Factory reset:** the reset deletes files without shredding them. The disk key is not changed.

**Before you sell the car:** do a factory reset from the menu. Crash dumps survive it and can hold fragments of personal data.

---

## How to reduce what is sent

1. In *My Vehicle → Data privacy*, turn off at least:
   - **Mobility / History**: per-drive GPS records
   - **Online speech processing**, **Activation word**, **Active speech processing**
   - Product quality, service quality and map-quality data
   - Learning navigation, if you don't want trips stored
2. Check **Global Location Access** again after any settings change, because the privacy app may switch it back on.
3. Keep **Send contacts to Cerence** off for each phone.
4. Without a ConnectedDrive sign-in, most apps are de-provisioned. The four autostart apps above remain.
5. Nothing in the menu covers the emergency call, remote diagnosis, the crowd-data collector's native part, health telemetry or the settings upload.

---

## Limits of this study

- **Static analysis only.** Nothing was run and no traffic was captured, so "can send" is not the same as "did send".
- **Provisioning is the main unknown.** BMW's live configuration for the examined car, which turns services on and sets the URLs, sits in encrypted storage and was not read.
- **The current switch states** on the car were not read. "Default ON" means the state on a new car, not the examined car's state.
- **Not covered:** the telematics unit (modem, eCall) and other ECUs. They can collect data on their own and were not part of this image.
- **Partly covered:** about 3000 system libraries were only partly scanned, and the hard disk was not in the image.
- **Open questions** are listed at the end of each findings file. The ones that matter most:
  - Does a Global Location Access "off" survive?
  - Is crowd data collection coded on in the examined car?
  - Do the crowd-data jobs respect the privacy switches?

---

## About this study

- **Independent research.** It is not affiliated with, endorsed by or checked by BMW AG, Harman or Cerence. BMW, iDrive, ConnectedDrive and other names are trademarks of their owners and are used here only to identify the products.
- **Purpose:** to help owners understand and control what their car shares. It is not a security exploit, and it contains no keys, certificates, credentials or personal data.
- **Quoted code:** short excerpts of the stock software are quoted as evidence. No BMW software is redistributed.
- **Accuracy:** findings come from reading one firmware version (P18_23w44.2) and can differ on other versions, markets or cars. Corrections are welcome as GitHub issues, with the firmware version and evidence.
- **Rebuilding the PDF:** `python3 tools/md2html.py report.html README.md findings/*.md`, then `node tools/pdf.cjs report.html MGU-privacy-report.pdf` (needs Playwright with Chromium).

