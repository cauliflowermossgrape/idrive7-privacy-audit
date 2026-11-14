# MGU privacy audit: findings 01, the OAP JavaScript apps and platform

**Scope:** the 18 BMW "OAP" (Online App Platform) Node.js apps pulled from a car (`apps-from-car/`), the OAP MainApp (`oap-mainapp/`), the OAP SDK (`oap-sdk/`), and the per-app SOME/IP permission lists and registry state. Firmware: `BMW MGU P18_23w44.2`, MainApp `8.3.2`.

**Method:** static reading of the code only. Nothing was executed. Minified bundles were split into their browserify modules for reading. Credentials, keys and tokens were deliberately not inspected; where they exist, only their location is given. No personal data (VIN, coordinates, names, account IDs) from the dumps is reproduced here.

**Labels used:**
- **code present**: the logic exists in the shipped app
- **default on/off**: the state on a fresh car before the user touches the privacy menu
- **gated by X**: the condition that must hold before data leaves
- **unknown**: not determinable from the dumps
- Each claim carries a confidence: **H**igh, **M**edium or **L**ow
- Inferences are marked *(inference)*

**Important context for the examined car.** The car is **not signed in to ConnectedDrive**. In that state the BMW backend de-provisions the ConnectedDrive apps: message_handling, cmusic, weather, ts_*, data-collection and others. Only these four run autostart **without a login**:
- `trigger_service`
- `x_call`
- `ts_diagnostic_service`
- `oap-cdc-2018`

The registry dump still shows all 18 apps as `enabled/allowed=true`, but it is a snapshot from before de-provisioning. Most of the flows below are therefore *dormant* on the examined car. They would become active after a ConnectedDrive sign-in with a backend provisioning that enables them.

---

## 1. Summary table

| Component | Data collected (that leaves the car) | Destination | Trigger | Gating | Conf. |
|---|---|---|---|---|---|
| **OAP platform analytics** (SDK in every app + MainApp) | App start/stop/crash, foreground time (`APP_USAGE`), CPU/memory (`APP_CPU`/`APP_MEMORY`), install/update results, boot/shutdown; envelope = app name, versions, I-step, HW gen, session UUID. Countly variant adds **SHA-1(VIN)** device ID and per-drive `driveId` | (a) app-to-app to **oap-cdc-2018**, forwarded only if a CDC campaign job subscribes; (b) **Countly** via DUMM to provisioned URL (`insight.{prod,e2e}.cd-{emea,us,cn}.bmw`) | App lifecycle; CPU/memory every 100 s, 6 samples per event; Countly batches every 300 s | Provisioning `<analytics><active>` / `<app_analytics>` **and** privacy `CDC_PRODUCT_QUALITY`=UserEnabled (sensitive → **default off**). Otherwise dropped after 10 s ("Event APP_MEMORY discarded") | H |
| **data-collection** ("RideHistory") | Per drive: **VIN**, driver gcid, **start and end GPS coordinates** (full precision), times, km, odometer, fuel/electric consumption, SoC/tank, driving-mode shares, accel/brake "stars", eco-trainer, low-emission-zone IDs, temps. LSC: CBS service list, Check-Control messages, tyre target pressures, parking level/building names | joynr `rcc.lscfsu` / `lsc/CSU.updateRequest_V2` (BMW backend over MQTT) | End of each drive segment (CTC); on change, debounced (LSC); retries; backlog of up to 300 records / 28 days | Provisioning (`pmh`, `tripstatistics`, `fleetdataenergy`, `lsc`) **and** per-use-case privacy: `HISTORY` (**default ON**, non-sensitive), `FLEET_DATA_ENERGY`, `TRIP_STATISTICS`, `LAST_STATE_CALL` (default off). GPS additionally needs `GLOBAL_LOCATION_ACCESS` (treated as on unless explicitly disabled). PMH needs **no login** | H (mechanism) / M (default-on in practice) |
| **privacy_manager** (the car's Data-Privacy menu) | All privacy switch states + gcid + guest flag + **VIN** (in request ID) | joynr `sec.dpp` `PrivacySettingsBackend.updateSettings`; backend can push settings back (`FUPO_SYNC`/`VEHICLE_SYNC`) | Any change; re-upload whenever last upload is >15 days old | Runs whenever installed; no opt-out | H |
| **oap-cdc-2018** (Crowd Data Collector) | Job request: **VIN, position rounded to 0.05° (~5 km)**, home market, option codes, vehicle capabilities, **all privacy states**. Campaign jobs can read any of 169 granted interfaces (incl. driver face-tracking, journey history, call metadata, gcid), DLT logs, crash dumps, DTCs | `cmcs.{prod,e2e}.cd-{emea,us,cn}.bmw.cloud:6920/cmvs/v1/jobs` (DUMM) or joynr `vsd.cmcs`; events → native `CDCCoreService` → backend (endpoint unknown) | Start-up, every privacy change (30 s debounce), diag request; jobs fire on geo-polygon/mileage/time/date/power-state/CCM conditions | Signed, VIN-bound jobs; privacy states sent to backend (no in-app block found); creates CDC_* privacy entries **enabled:true, confirmed:false**; **no login needed; autostart**; GPS suppressed for CN/KR | H (mechanism) / unknown (actual campaigns) |
| **x_call** (Intelligent/Breakdown/Accident call) | **VIN, precise position + GNSS breadcrumb trail**, nav destination, odometer, tank, oil, tyres, temps, battery SoC, range, CCMs, passenger count, language; PDM diag on breakdown call | joynr `vs.xcs` `XCallBackend.notifyXCall`; voice call to call centre | User SOS button/speech, accident (damage stage ≥2, after a user-reaction CCM), HV battery guard, backend `requestXCall` | Per-service provisioning (all default disabled); **no login; no privacy toggle**; autostart | H |
| **ts_diagnostic_service** (remote diagnosis) | VIN, ECU key data, PDM diag-job results (UDS/DTCs), I-steps; heartbeat: speed bucket (0–6 / >6), gear, parking brake, lock state, signal strength | joynr `ts.diagservice`, `ts.pdmdata`, `ts.rtcservice`, `ts.pdmupdater`, `ts.wlupdater`, `ts.tsrd`; PDM file HTTP PUT via DUMM to backend-supplied URL | Mostly **backend-initiated** (wake-up-on-demand); also on request from other ts_* apps | **No privacy setting**; signed job whitelist (ODF); temp sessions ≤48 h, abort on speed; **autostart, no login** | M-H |
| **ts_servicecall** (automatic service call) | VIN, odometer, battery charge, tank, exterior temp, CBS list, CCM list, key data, versions | joynr `ts.scallservice` `notifyMaintenanceStatus` | CBS due / odometer threshold after ≥60 s driving; listed CCMs appear or resolve; backend request | Privacy `AUTOMATIC_SERVICE_CALL` (**default ON**) + provisioning `asc` | H |
| **ts_battery_guard** | VIN, low-voltage/deep-sleep flags, trigger reason, model, I-steps | joynr `ts.tsbgservice` `notifyBatterySleepStatus` | Battery-guard wake-up `OSFG_ERREICHT`; backend request | Privacy `BATTERY_GUARD` (**default ON**) | H |
| **ts_rsu_report** (software-update report) | VIN, update trigger point, key data, PDM result ID, SW version; **GPS only on update error** | joynr `ts.rsurservice` `notifyRSUStatus` | Called by the update gateway before/after an OTA update | **No privacy check found**; login required | H |
| **ts_service_partner** | VIN header, language, **current lat/lon when user searches nearby dealers**, chosen dealer | HTTPS via DUMM to provisioned `service_url` `/v1`, `/v1/search` | User action / speech; cold boot (GET without position, inferred) | User-initiated; login; no privacy setting | M-H |
| **trigger_service** | Nothing of its own beyond analytics (`PLATFORM_BOOT/SHUTDOWN`, `TRS_HEALTH_REPORT` per-app CPU/memory). Evaluates other apps' trigger scripts over ~157 interfaces in a sandbox without network access | SDK analytics only | Signal changes (≥1 s), health report hourly | Analytics gate (above) | H / M |
| **weather** | **Full-precision position**, nav destination, typed search text | HTTPS via DUMM to provisioned CDP `/vehicle/id7/rest/weather/{weather,reverseGeocoder,geocoder}/v1` | App use **and background wake every 20 min**, 10 km geofence exit, guidance change | Login + connectivity only; **no privacy setting** (only `WEATHER_ON_MAP` exists for the nav map layer, not used by this app) | M-H |
| **oap-bon-newsnext** (news) | gcid **or VIN**, country/language, position rounded to 0.1° (~11 km), drive duration; listening/like events | `ccis-ise.prod.cd-emea.bmw.cloud` `/news-next/api/v1` via DUMM | App use; event batches ~15 min | Events need `MY_PERSONAL_NEWS` (default off); **registration + location fetch not gated** | H |
| **message_handling** (BMW messages) | VIN, gcid, message/campaign IDs, read/clicked/dialled/deleted receipts | joynr `rcc.msgsvc` `notifyMessageStatus` | User action on a BMW message | Login; no privacy check (XCC_* settings control which messages are received) | H |
| **connected-onboard** (Send-to-car, Alexa) | gcid, VIN, trip activation status; Alexa driver-to-vehicle mapping; Countly usage | `myc-vehicle…` / `service.gateway.vehicle` `/api/gateway/*`; joynr `vcs.omg` | Login/logout, push, **hourly Alexa keep-alive** | Login/token; last-mile parking upload gated by `LAST_STATE_CALL` and is a stub (nothing sent) | M-H |
| **smartinterior** (IPA / Caring Car / smart window) | Seat-climate stages, window opening, geofence in/out for user-saved places (IDs/names), scene definitions, VIN + token | `CDCCoreService` campaign 5; joynr `vcs.vehicletask` (`pushSceneUD`, `requestScenesML`); Countly | User/scene/geofence events | `LEARN_DRIVE_BEHAVIOR` (+`LEARN_VEHICLE_POSITION` for window); default off; no guest | H |
| **cmusic** (Spotify) | VIN header, browse/search/queue, **4 s audio fingerprint** for song recognition | `service-oe…cd-emea.bmw:7570 /oes/service/v2/spotify/*` via DUMM | User actions | Login + Spotify session; no privacy check found | M-H |
| **mlaptimer** | Nothing leaves (local GPS lap trace, speed, g-forces, pedal, steering) | — (SDK analytics only) | Active session | Login | M-H |
| **oap-license-app** | Page-view state only | SDK analytics | View change | Analytics gate | H |

**Headline points**
1. **Location leaves the car in at least six paths**:
   - data-collection: start/end of every drive, full precision
   - x_call: precise position + breadcrumb trail, but only on a call
   - weather: full precision, periodic background wakes
   - CDC job request: ~5 km
   - newsnext: ~11 km
   - service_partner: on a nearby-dealer search
   - ts_rsu_report: only on a failed update
2. **The VIN is attached to almost every backend message**, in clear (`realVIN`, with `anomVIN:"0000000000"`), plus the gcid when a user is logged in.
3. **Defaults matter more than switches.** Non-sensitive settings default ON:
   - `HISTORY`: per-drive records with GPS
   - `AUTOMATIC_SERVICE_CALL`, `BATTERY_GUARD`, `TELESERVICE_REPORT(_MS)`, `ACCIDENT_INFO`
   - `CDC_SERVICE_QUALITY`, `REMOTE_SOFTWARE_UPDATE`, `CONNECTED_LEARNING`, `MAP_UPDATE`, `XCC_CONTRACT_INFO`
4. **Some flows have no user-facing switch at all**: x_call (by design), ts_diagnostic_service (backend-initiated remote diagnosis), ts_rsu_report, weather position, newsnext registration/position, message receipts, and the privacy-settings upload itself.
5. **The real gate is the backend.** Every flow also requires the app to be provisioned, and most hosts and URLs come from provisioning. Without a ConnectedDrive account most of it is dormant. On the examined car the four autostart apps (x_call, ts_diagnostic_service, oap-cdc-2018, trigger_service) remain installed without a login. Their sending still depends on per-service provisioning, which could not be read from the dumps.

---
## 2. Cross-cutting: the OAP platform (MainApp + SDK)

### 2.1 No backend hostnames are hard-coded
The MainApp (`oap-mainapp/`) has no BMW backend URL in its code or config. The only `https://` hosts are licence/GitHub links and a placeholder `https://example.bmw.com`. Every backend endpoint (analytics URL, app download URL, joynr backend domains) comes from **provisioning**: an XML/JSON document the BMW backend pushes to the car through the telematics unit (`de.bmw.infotainment.telematic.provisioning.Provisioning`, `provisioningDataJSON` broadcast). *Confidence: high.*

```
oap-mainapp/src/main.js (AnalyticsServiceImpl):
 "A '<app_analytics><active>true</active><url>https://example.bmw.com</url></app_analytics>' section is needed!"
```

### 2.2 Transports
- **joynr over MQTT** (BMW's middleware). Apps build proxies with `discoveryScope: GLOBAL_ONLY` to backend domains such as `rcc.lscfsu`, `rcc.vhcjoynrreceiver` and `sec.dpp`. The traffic goes out over the TCB (the telematics/modem ECU). *High.*
- **HTTP via DUMM** (`de.bmw.infotainment.telematic.dumm.DUMM`, methods `sendHTTPRequest` and `startHTTPTransfer`). DUMM is the telematics unit's HTTP transfer manager. Apps hand it a URL plus a request-body file, and DUMM performs the request. *High.*
- **App-to-app** (SOME/IP `de.bmw.infotainment.telematic.oap.AppToApp`, instance `cdc` = "3"). This carries platform analytics to the oap-cdc-2018 app (see 2.3). *High.*

### 2.3 Platform analytics ("AnalyticsService"): the pipeline behind the `APP_MEMORY discarded` log line
Every OAP app embeds the SDK's `AnalyticsServiceImpl`. MainApp has its own copy (SDK 26.27.2). Source: `oap-mainapp/src/main.js` modules 833–840.

**Two separate channels:**

| Channel | Publisher | Where it goes | Permission check |
|---|---|---|---|
| Platform analytics: `sendPlatformEvent()` | `AnalyticsCdcPublisher` | App-to-app `cdcApiClient.sendEvent()` to the **oap-cdc-2018** app, which then decides on forwarding (see §5 cdc) | `isPlatformAnalyticsPermitted()` |
| App analytics: `sendEvent()` | `AnalyticsCountlyPublisher` (**Countly** `countly-sdk-nodejs`) | HTTP POST through DUMM to a provisioned URL (`isBmwBackend:false`) | `isAppAnalyticsPermitted()` |

**Gate (both channels):** three conditions must all be true. *High.*
```
isPlatformAnalyticsPermitted(){ return this.oapPlatformAnalyticsFlag===TRUE &&
  (this.appPlatformAnalyticsFlag===TRUE || ...NOT_PRESENT) && !0===this.privacySettingsFlag }
isAppAnalyticsPermitted(){ return this.oapAppAnalyticsFlag===TRUE && void 0!==this.oapAppAnalyticsUrl && ... && !0===this.privacySettingsFlag }
```
1. **Provisioning, global**: the `oap` section must contain `<analytics><active>true</active>` (platform channel), or `<app_analytics><active>true</active><url>…</url>` (Countly channel).
2. **Provisioning, per app**: the app's own section must not set `active` to false (absent counts as allowed).
3. **Privacy setting**: `CDC_PRODUCT_QUALITY` must be in state `UserEnabled` for the current user (`PRODUCT_QUALITY_SETTING="CDC_PRODUCT_QUALITY"`, `PRIVACY_SETTING_ENABLED="UserEnabled"`). In the privacy_manager this setting sits in the group `ProductImprovement_ProductQuality`, which is **sensitive** and therefore **off by default** (see §4).

**What the car log line means.** `sendPlatformEvent` waits up to `analytics.isPermissionDefinedPromiseTimeout` = 10 000 ms for both the provisioning and the privacy answers. If either answer never arrives, the event is dropped. The SDK itself labels this "Works as designed. Analytics is most likely disabled." Two things explain it on this car: it is not signed in to ConnectedDrive, and the provisioning holds no `analytics` section. Nothing is queued for later, because the timeout path discards the event. *High.*
```
promiseWithTimeout(this.isPermissionDefinedPromise, config.get("analytics.isPermissionDefinedPromiseTimeout"),
 `... analytics internal timeout. Works as designed. Analytics is most likely disabled.`)
 ... logger.warn(`${logPrefix} timeout while waiting for provisioning/privacy status. Event ${event.eventType} discarded.`)
```

**What would be sent if enabled.** The event types are defined in `analyticsservice` (main.js line ~3261):
`APP_START, APP_STOP, APP_CRASH, APP_INSTALL, APP_UPDATE, APP_DOWNLOAD, APP_SIGNATURE_CHECK, APP_USAGE, APP_ACTIVE_BACKGROUND, APP_CPU, APP_MEMORY, PLATFORM_BOOT, PLATFORM_SHUTDOWN, PLATFORM_UPDATE, PLATFORM_CPU, PLATFORM_MEMORY, PLATFORM_MEMORY_STATES, RELOGIN`.

Payloads found in the code. *High.*

| Event | Payload fields | Emitted by / when |
|---|---|---|
| `APP_MEMORY` | `avgMemConsuKb`, `peakMemConsuKb` | SDK in each app: 3 start-up samples 30 s apart, then one sample every 100 s, aggregated 6 per event (`memoryTimerMs:100000`, `memoryMeasuresAggregatedPerEvent:6`), plus a final event at stop |
| `APP_CPU` | `avgCPUConsuPercent`, `peakCPUConsuPercent` | same timing scheme (`cpuTimerMs:100000`) |
| `APP_USAGE` | `usageDurationMs` (time the app was in the foreground) | SDK, when the app leaves the foreground |
| `APP_ACTIVE_BACKGROUND` | `activeDurationMs` / `inactiveDurationMs` | SDK |
| `APP_START` | `startReason`, `startUpTimeMs` | SDK at app start |
| `APP_STOP` | `stopReason` | SDK at shutdown (sent synchronously) |
| `APP_CRASH` | `stopReason` (UNCAUGHT_EXCEPTION / UNHANDLED_REJECTION), or `crashCount`, `appName`, `appVersion` | SDK, and MainApp recovery logic |
| `APP_INSTALL` / `APP_UPDATE` | `appName`, `appVersion`, `result`, `errorCode`, `errorMessage` | MainApp install flow |
| `PLATFORM_CPU` / `PLATFORM_MEMORY` / `PLATFORM_MEMORY_STATES` | CPU %, memory KB, time spent in a memory zone | MainApp, from cgroup files `/sys/fs/cgroup/.../oap.slice/...` |

Every event is extended with envelope fields (`extendEvent`): `senderId` (app name), `timestamp`, `versionApp`, `versionSDK`, `pu` (I-step/software level), `hwVersion` ("MGU18"/…), `swVersion`, and `sessionId` (a random UUID v1 per app run). **The platform channel itself attaches no VIN, location or user ID.** It carries app-usage telemetry: which apps run, for how long in the foreground, plus resource use and crashes. The CDC app may add vehicle identity when it forwards. *High for the payload, unknown for what CDC adds.*

**Countly channel extras** (only when `app_analytics` is provisioned):
```
device_id: EncryptionUtils_1.encryptSha1(vin), metrics:{_os:this.pu, _os_version:..., _device:`mgu${hw}`},
storage_path:this.storagePath, ... queue_size:500, max_events:500, interval:3e5
```
- The device ID is the **SHA-1 of the VIN**. That is a stable pseudonym, and anyone who already has the VIN can recompute it, so it is not anonymous. *High.*
- Every event gets a `driveId` from DUMM's `driveId` attribute. This links events to individual drives. *High.*
- Events are batched and flushed every 300 s, at most 500 queued. They are stored in `<app>/countly_data/` (`__cly_event.json`, `__cly_queue.json`). Uploads go through DUMM using files in a shared folder (`countlyFiles`, group `dumm_oap`); bodies over 2 MB are dropped. *High.*
- The Countly app key comes from the app's package/provisioning. I did not inspect it, by design.
- The data-collection CHANGELOG says "remove all countly events/oapAnalytics", and its `sendAnalyticsEvent()` now only writes to the log. Several other apps still bundle the Countly code; whether they call `sendEvent` was not checked app by app. *Medium.*

### 2.4 SDK identity helpers
- `getVin()` reads the VIN from the `VIN` environment variable that oapcontroller gives every app (`oap-sdk/source/src/utils/getVin.js`). **Every OAP app can read the VIN.** *High.*
- `UserAccount` / `USSO` expose the user's `gcid` (BMW Global Customer ID), name fields and an auth token to apps that request them in `manifest.json`. data-collection requests `firstName`, `gcid`, `name` and the USSO `token`. *High (manifest).*
- `JoynrLoggingAppender` only routes the joynr library's log lines into the app logger (DLT). It does not upload anything. *High.*

---

## 3. data-collection (uid 12213, v3.13.3, "RideHistory")

> package.json: "handles the data gathering for the Car Genius Facts and Figures functionality, by collecting vehicle information after each ride. For example fuel consumption, ride duration, efficiency."

Source: `apps-from-car/data-collection/` (bundle `javascript/app.js`; app modules 716–748). Background app, `visibility: BACKGROUND`, `userLoginRequired:false` in package.json, `loggingId OA31`.

### 3.1 Data read (manifest.json + code)
From the manifest proxies:
- **Location**: `Positioning.currentLocation` (sampled every 10 s, `config/base.json getIntervalsMs.Positioning.currentLocation:10000`), `GPSData.GPSPositionCAN`/`GPSPositionExtendedCAN`, `PositioningCAN.statusGpsPosition`, and the names of the current parking level, district and building.
- **Driving dynamics**: `Vehicle2.statusCarSpeed2` (every 2 s), `XView.statusSteeringAngleDriver`, `CDS.statusEngineSpeed2`, `CDS2.statusLongitudinalAccelerationMassCenter`, `Efficiencytainment2.statusOperatingModeHybrid`.
- **Vehicle state**: odometer, `KombiIF.statusRangeTankStatus`, `KombiInterface_2.cbsDataServiceList` (service due list, CBS) and `ccList` (Check-Control messages, CCM), `TPMS.statusTargetTyrePressure`, `VehicleCondition`, `VehicleInformation.Range`, exterior temperature, light status, trailer, `BeltContactSeatOccupancy`.
- **Trip computer**: `journeyhistory.BcPersonal` (full read, plus `startNewSegment`). This supplies `driveSegment`, `driveSegmentStatus` and `driveSegmentExtension`.
- **Identity**: VIN (`getVin`), `UserAccount.gcid/firstName/name`, `USSO.token/gcid/loggedIn`, `Telephone.signalQuality`.
- **eZones**: `ConnectedForesight` (low-emission and zero-emission zones crossed during the drive).

*High (manifest). Code use was confirmed for location, BcPersonal, CBS/CCM/TPMS, odometer, gcid and VIN. It was not confirmed for steering angle or acceleration, which may be unused leftovers.*

### 3.2 Destination
joynr to the BMW backend. Domain `rcc.lscfsu`, interface `de/bmw/infotainment/telematic/lsc/CSU`, method `updateRequest_V2` with `{vin, data}`. `permissions.json` additionally allows `rcc.vhcjoynrreceiver` / `JourneyHistoryBackend`. *High.*
```
BackendController: const domain=config.get("joynr:backend:domain:lsc") ... discoveryScope:DiscoveryScope.GLOBAL_ONLY
 await proxy.callMethod("updateRequest_V2",{vin:vin,data:data})
config/base.json: "domain": { "lsc": "rcc.lscfsu" }
```
The **VIN is sent in clear inside the payload**. Each record also carries infrastructure attributes: `oapDatasetType` (`CTC` or `FSU`), app version, `oapAppMguSwVersion` and `oapAppMguSop`.

### 3.3 Two data sets, with their triggers

**A. CTC: per-drive records (use cases PMH = "History", TRIP_STATISTICS, FLEET_DATA_ENERGY, FLEETDATA_ELECTRIFICATIONANALYSIS)**
- Trigger: a drive-segment status change from `BcPersonal`. The segment start is stored, and at segment **end** (end of drive / driver change) one record per allowed use case is built and submitted. Up to 3 retries 30 s apart. Records that fail to send are kept on disk. *High.*
- Content is defined in `data/mappingCTC.json` (107 attributes). PROD attributes include:
  - **identity**: `lastDriveVIN` (PMH), `lastDriveDriverID` = gcid (PMH and TRIP_STATISTICS)
  - **location**: `lastDriveStartGpsLat/Lon` and `lastDriveEndGpsLat/Lon`, the **start and end coordinates of every drive**, in PMH, TRIP_STATISTICS and FLEETDATA_ELECTRIFICATIONANALYSIS. These are raw latitude/longitude; the code does no rounding.
  - **time**: start and end time in UTC and local time, duration, moving time
  - **distance and odometer**: trip km, mileage at start and end
  - **energy**: fuel and electric consumption, tank level and HV state of charge at start and end, recuperation, electric km
  - **driving style**: share of distance in ECO/COMFORT/SPORT/ECO PRO+/electric modes, coasting km
  - **driving behaviour scores** (`analysis.*`): acceleration and braking "stars" won or lost, average values, `brakeTime5`, `acclTime5` (PMH)
  - **efficiency trainer**: bonus range won for acceleration, speed and foresight
  - **eZones**: count, IDs and distance driven inside low-emission zones
  - **outside temperature** at start and end, average speed
  ```
  createDriveSegmentOap: {bcBeDriverId:segmentStart.gcid, bcBeVin:this.vin, ...,
   bcBeStartGpsLat:segmentStart.gpsPosition.latitude, bcBeStartGpsLon:..., bcBeEndGpsLat:endPosition.latitude, bcBeEndGpsLon:...}
  ```

**B. LSC / "FSU" (Last State Call)**
- Content is defined in `data/mappingFSU.json` and filtered further by the provisioned whitelist: CBS service list (with service counter and days), Check-Control messages, target tyre pressures, pressure unit, and the **parking level, district and building names** from navigation. Odometer and units are added. *High.*
- Trigger: change-driven. The app subscribes to each attribute with 1 s sampling, debounces changes, and also sends the other attributes of the same "sendgroup". There is an initial submit 6 s after head-unit resume, and the current CCMs are sent 2 s after the vehicle enters driving state (`FAHREN`). Nothing is sent while the car is in workshop/diagnosis state (`PRUEFEN_ANALYSE_DIAGNOSE`) or shutting down. Up to 5 retries 10 s apart. *High.*

### 3.4 Gating
1. **Provisioning** (backend-controlled): `<data-collection enabled allowed>`, with sub-flags `<pmh>`, `<fleetdataenergy>`, `<tripstatistics>`, `<lsc>` plus an LSC signal whitelist, and `<pmh_development>` for DEV-only attributes. The README gives an example provisioning. Without the flags, no use case is active. *High.*
2. **Privacy settings** (checked per user, against the gcid of the driver who started the segment):
   - PMH needs `HISTORY` = UserEnabled
   - FLEET_DATA_ENERGY and FLEETDATA_ELECTRIFICATIONANALYSIS need `FLEET_DATA_ENERGY`
   - TRIP_STATISTICS needs `TRIP_STATISTICS` **and** the "confirmed" flag **and** a logged-in user
   - LSC needs `LAST_STATE_CALL`
   ```
   allowedUseCases = useCaseEnabledFlags.HISTORY && privacySettings.HISTORY ? ...concat("PMH") ...
   isUserLoggedIn && useCaseEnabledFlags.TRIP_STATISTICS && privacySettings.TRIP_STATISTICS ? ...
   ```
   The app's own default when it cannot read the settings is all **false**: `DEFAULT_PRIVACY_SETTINGS_PER_USER={HISTORY:!1,…,LAST_STATE_CALL:!1,GLOBAL_LOCATION_ACCESS:!0}`.
3. **GPS is gated separately by `GLOBAL_LOCATION_ACCESS` (GLA).** The app treats GLA as allowed **unless it is explicitly `UserDisabled`**: `isSettingEnabled="UserDisabled"!==privacySettingState`. Its default is `true`. When GLA is off, the coordinates are sent as 0/0 while the rest of the record is still sent. *High.*
4. **Login**: PMH and FLEET_DATA_ENERGY do **not** require a logged-in user; only TRIP_STATISTICS does. If nobody is logged in and nothing is allowed, the app logs `CTC_SUBMIT_NOT_ALLOWED` locally and counts the missed drive in `dpmCounter`. That counter is then sent with the next record that is allowed, as `lastDriveNotSentDPMCounter`. *High.*
5. **What is on by default.** In privacy_manager (§4), `HISTORY` is in the **non-sensitive** group `BMWConnectedDrive_Mobility` at level 2, so it is **enabled by default** (`initialEnabled = sensitive ? false : level<3`). `FLEET_DATA_ENERGY`, `TRIP_STATISTICS` and `LAST_STATE_CALL` are sensitive, so they are off by default. GLA is forced on outside China (§4). **Inference (medium confidence):** on a provisioned, ConnectedDrive-active car outside China, PMH records with VIN, gcid (if a user is logged in), start/end GPS, times, consumption and driving-style scores are sent after every drive unless the user switches off the "Mobility" (HISTORY) setting. Whether the backend actually provisions `<pmh enabled="true">` for a given market could not be verified from the dumps.

### 3.5 Local storage / retention
Files are written via `FileStorageController` in the app's data folder:
- `ctcSegmentStartData`: includes the start GPS fix and gcid
- `previousSegmentData`, `ctcDebugInfo`
- `ctcUnsentSegments`: **up to 300 unsent drive records**, kept up to **28 days** (`HISTORY_TIME_LIMIT_IN_SECONDS=2419200`, `MAX_NUM_SAVED_HISTORIES=300`)
- `lscPreviousCcm`, `lscCurrentMileage`, `bmwpointsEZoneEvents`, `bmwpointsBcState`

Quota is 17 MB (`maxDiskUsage`). *High.*

---

## 4. privacy_manager (uid 12208, v4.68.1, "Data Privacy Menu for ID7 vehicles")

This app is the **car's data-privacy menu**. It owns the `PrivacySettings` SOME/IP service that every other app queries, and it decides the defaults.

### 4.1 Settings per app (`config/App-Mapping.json`, bundle module 1049)
| App | Privacy setting keys |
|---|---|
| ts_battery_guard | BATTERY_GUARD |
| ts_servicecall | AUTOMATIC_SERVICE_CALL |
| ts_report (not on this car; ts_rsu_report and ts_diagnostic_service have **no** entry of their own) | TELESERVICE_REPORT_MS, TELESERVICE_REPORT |
| x_call | ACCIDENT_INFO |
| message_handling | XCC_CONTRACT_INFO, XCC_PRODUCT_INFO, XCC_SERVICE_INFO |
| smartinterior | LEARN_DRIVE_BEHAVIOR, LEARN_VEHICLE_POSITION |
| connected-onboard | CONNECTED_LEARNING |
| data-collection | TRIP_STATISTICS, FLEET_DATA_ENERGY, BMW_POINTS, HISTORY |
| oap-cdc-2018 | CDC_PARKING, CDC_MAP_QUALITY, CDC_ONLINE_TRAFFIC, CDC_PRODUCT_QUALITY, CDC_SERVICE_QUALITY, PREDICTIVE_MAINTENANCE |
| cmusic | ONLINE_ENTERTAINMENT_STATISTIC |
| oap-bon-newsnext | MY_PERSONAL_NEWS |
| (rsu) | REMOTE_SOFTWARE_UPDATE |

### 4.2 Defaults (`config/selected/groups`, module 1052; rule in `Setting.initialEnabled`)
```
get initialEnabled(){const level=this.level;return this.sensitive&&!...TC114...?(...,!1):level<3}
get level(){return this.defaultGroup.level(this.provisioning.homeCountry,this.override)}
```
- **A sensitive group always starts OFF.** A non-sensitive group starts ON when its level is below 3, which in practice means level 2. Levels can differ per home country. **The backend can override the level and scope through provisioning** (`ProvisioningSettingOverrideGroup`). *High.*

**Enabled by default (non-sensitive, level 2):**
- `BMWConnectedDrive_SecureMobility`: BATTERY_GUARD, AUTOMATIC_SERVICE_CALL, TELESERVICE_REPORT_MS, ACCIDENT_INFO
- `ProductImprovement_ServiceQuality`: TELESERVICE_REPORT, CDC_SERVICE_QUALITY
- `BMWConnectedDrive_Mobility`: **HISTORY**
- `Navigation_MapUpdate`: MAP_UPDATE
- `ProductImprovement_RSU`: REMOTE_SOFTWARE_UPDATE
- `CustomerCommunication_Contractinfo`: XCC_CONTRACT_INFO
- `BMWConnectedDrive_BMWConnectedLearning`: CONNECTED_LEARNING
- `BMWConnectedDrive_SIRIUSXM`

**Disabled by default (sensitive, or level ≥ 3):**
- CDC_PRODUCT_QUALITY and ONLINE_ENTERTAINMENT_STATISTIC (level 4)
- CDC_MAP_QUALITY/LEARNING_MAP, CDC_ONLINE_TRAFFIC, CDC_PARKING, ONLINE_ROUTES, ONLINE_DESTINATIONS, WEATHER_ON_MAP, LAST_STATE_CALL, FLEET_DATA_ENERGY, EDRIVE_ZONE, NCAP_SPEED_LIMIT_INFO, DRIVER_CAMERA_SYSTEM, GLOBAL_MICROPHONE_ACCESS (all sensitive, level 2)
- TRIP_STATISTICS, PREDICTIVE_MAINTENANCE, LEARN_DRIVE_BEHAVIOR, LEARN_VEHICLE_POSITION, WAKEUP_WORD, SPEECH, MY_PERSONAL_NEWS, REMOTE_360, ALEXA_IN_CAR, INTELLIGENT_SPEED_ASSISTANT (sensitive, level 3)
- ALWAYS_LISTENING, CDC_FUTURE_MOBILITY (sensitive, level 4)
- ONLINE_LOG (TOL), XCC_SERVICE_INFO, XCC_PRODUCT_INFO, BMW_POINTS, OAP_AUTOMATIC_APP_UPDATE, AFFILIATE_MARKETING, AFFILIATE_ENRICHED (non-sensitive, level 3–4)

*High.* A sensitive setting that is off can still be switched on through the "unconfirmed settings" pop-up (`UnconfirmedPopup`, `needsConfirmation`), and other apps can ask the privacy_manager to show a consent pop-up on their behalf (`openPrivacySettingsPopup`, app-to-app). *High (code present).*

### 4.3 Global Location Access (GLA) is forced on outside China
```
const glaSetting=this.oldList.__setting("MainMenuSetting_GLOBAL_LOCATION_ACCESS","GLOBAL_LOCATION_ACCESS");glaSetting.available=!0,
!this.provisioningRepository.china||... &&!this.codingController.tc114Enabled ?(glaSetting.confirmed=!0,glaSetting.enabled=!0, ...
```
This code is in `PrivacySettingsChangedUseCase.run()` (module 1037), which runs on every `PrivacySettings.allSettings` change. Each time, when the home country is not CN (or TC114 coding is off, which is hard-wired on MGU18: `CodingController on MGU18 - nothing to do here`, `tc114Enabled=!1`), the GLA entry in the merged settings list is set to `enabled=true, confirmed=true`. GLA has its own on/off button in the menu (`setGlaButton`). *High that the code exists.* **Unknown (low confidence):** whether the forced value is written back to the `PrivacySettings` service, i.e. whether a user's GLA "off" survives. This needs on-car verification. data-collection independently treats GLA as on unless it reads `UserDisabled` (§3.4). The CHANGELOG mentions "Correct handling of GLA sensitive setting state" (4.68.0).

### 4.4 The privacy settings are themselves uploaded to BMW
- joynr domain `sec.dpp`, interface `de/bmw/infotainment/dataprivacy/v3/PrivacySettingsBackend*`, method `updateSettings`. *High.*
- Payload: every available setting (`name`, `enabled`, `versionCounter`, label SID), `globalCustomerId` (gcid), `isGuestAccount`, `lastUserChange`, and a `requestId` containing the **VIN** plus a debug ref of `<app>-<timestamp>-<VIN>`.
- When: on any change (30 s delay on first sync), and again whenever the last upload is **older than 15 days** (`created.plus({days:15})<now`). The backend can also push settings into the car: `updateSettings` provider, sync types `FUPO_SYNC` and `VEHICLE_SYNC`, `requestTargetSetting`, `requestSyncedSetting`, `getPrivacyUsersWithGroupsForVin`. That means settings changed in the BMW account or phone app can flip switches in the car. *High.*
- The registry's `participantIds` for this app embed the VIN.

### 4.5 Other
- Triggers (`triggers.json`): settings changed, user changed, provisioning changed (sections listed for 18 apps, incl. `ts_logbook`, `parknow`, `edrive-zone`, `oap-snapshot`, `cradio`), language change, resume.
- Requests location/speed interfaces (Positioning, GPSData, Vehicle2 speed). By inference these serve the speed-lock overlay (`SpeedlockRepository`/`SpeedlockOverlay`): the menu is restricted while driving. No upload of these values was found. *Medium.*
- Local storage: `PersonalStorage` / `PublicStorage` (per-user settings, last upload, sync state).

---

## 5. oap-cdc-2018 (uid 12220, Crowd Data Collector), autostart, no login

**Firmware-preinstalled** (`preinstalled_apps/oap-cdc-2018@3.31.43.tgz`). Readable modules: `apps-firmware-modules/oap-cdc-2018/app-modules/`. The registry has `-appStartType:autostart`, `-userLoginRequired:false`.

**What it is.** A general-purpose in-car runtime for **data-collection campaigns**. The app does not have a fixed data set. It fetches signed "jobs" (scripts) from a BMW campaign backend and runs them. What gets collected is decided on the server. *H.*

**1. Data read.**
- Job scripts get these APIs (`job/ScriptApiFactory.js`): `someip` proxies, `diagnosis`, `dlt` (system logs), `crash_logs_mgu`, `persistency`, `resource_usage`, `getPrivacySettings`, `getVin`, `getVehicleCapability`.
- The manifest grants 169 interfaces. They include driver-model and face-tracking data, camera-based occupancy, `UserAccount` (name fields, gcid, ConnectedDrive user name), `USSO` token, licence plate, positioning, `BcPersonal` journey history, trip recorder, `VoiceCall` (contact ID and duration), crash severity, surround-view recorder and parking-sensor upload.
- *Grant: H. Actual use: unknown (depends on the campaigns deployed).*
- **Every job request** carries a fixed set of fields (`CampaignRequestGeneratorHttp.js`):
  ```
  jobRequest={position:position.pos_http,vehicleCapabilities,dataPrivacySettings,homeMarket,vehicleExtras,eCodes,ids,components,...}
  vin_long&&(jobRequest.vin=vin_long)
  ```
  The position is rounded to 0.05° (about 5 km). It is replaced by an invalid value when the home market is CN, KR or empty. *H.*
- Event identifiers: each job picks one of `VIN`, `DRIVE_ID` (per lifecycle), hashed VIN, `GCID`, `DEBUG_VIN` (`event/EventFactory.js`). *H.*

**2. Destination.**
- Jobs are fetched over HTTPS via DUMM from `https://cmcs.{prod,e2e}.cd-{emea,us,cn}.bmw.cloud:6920/cmvs/v1/jobs`. Provisioning `cdc_jobmanager` can override the URL; `cam_http_enabled` selects HTTP. The alternative is joynr `vsd.cmcs` (types `de.bmw.cc.vsd.cmrouter.*`).
- Job output goes to the **native** `CDCCoreService.sendEvent`, with targets such as `BACKEND_MGU`, `BACKEND_BULK`, `BACKEND_ATM2`. The upload endpoint lives in native code outside OAP. *Path: H. Endpoint: unknown.*
- **Platform analytics hub.** CDC's app-to-app `sendEvent` delivers each app's analytics event only to campaign jobs subscribed to it. With no subscriber the result is `"NoConsumer"`, and after 2 retries 5 s apart the event is dropped.
  ```
  for(...subscriptionsCache...) entry.callback(arg_o)
  const result_str=sub_count>0?"Consumed":"NoConsumer"
  ```
  So OAP platform analytics leaves the car only if a backend campaign asks for it. *H.*

**3. Triggers.**
- Job fetch happens after init/provisioning, on **every privacy-setting change** (debounced 30 s), and on diagnostic request. Up to 10 retries.
- Job conditions: `ConditionGeoPolygon`, `ConditionMileageInterval`, `ConditionTiming`, `ConditionDate`, `ConditionPWF` (power state), `ConditionNewCCMsg`, `ConditionVehDataBase(Modulus)`.
- A status event is sent about 30 s after start. *H.*

**4. Gating.**
- Jobs must be signature-valid and bound to the long VIN.
- CDC **creates its own privacy-menu entries** with `enabled:true`:
  ```
  PrivacyMenuKeys=["CDC_ONLINE_TRAFFIC","CDC_PARKING","CDC_PRODUCT_QUALITY","CDC_SERVICE_QUALITY","CDC_MAP_QUALITY"]
  addOrUpdateSetting({setting:{name:key,enabled:!0,...,type:"DYNAMIC",scope:"USER",versionCounter:"0",confirmed:!1}})
  ```
  `PREDICTIVE_MAINTENANCE` is only made available in 16 markets (DE, GB, FR, …; not US).
- This **conflicts** with privacy_manager, which treats these groups as sensitive and therefore off by default. How the two interact (privacy_manager reset vs. CDC insert, plus the "unconfirmed" pop-up) is open question Q3.
- **Update (stored settings read from one car):** all five CDC entries were stored as `enabled:true, confirmed:false`. The settings bridge maps `available && enabled` to `UserEnabled` and ignores `confirmed` (`someipPrivacySettingToTsPrivacySettingState`), so apps see these switches as user-enabled. On that car, BMW's provisioning had `<analytics><active>true</active>` and `<app_analytics><active>true</active>`.
- No in-app code was found that blocks a job's events on privacy state. The states are sent to the backend with the job request and are readable by job scripts. *(Inference, M:)* filtering happens in backend job selection and/or native CDCCore.
- No login is needed.

**5. Storage.** `job.registry.json`, `campaign.registry.json`, a per-job key/value store, crash-log `status.json`, `countly_data/`. A certificate module is bundled at `apps-firmware-modules/oap-cdc-2018/app-modules/certs/BackupCertificate.js` (not read).

---

## 6. x_call (uid 12206, v4.84.26 on car; firmware has 4.25.3), autostart, no login

The backend updated the app. The findings come from `apps-from-car/x_call/javascript/app.js`.

**1. Data read and sent in every `notifyXCall`.** *H.*
- VIN
- current position at full precision: lat, lon, altitude, heading
- `recentPositions` (the GNSS "pearl chain" breadcrumb trail)
- navigation destination, distance and travel time
- vehicle status: tyre pressures, odometer, tank, oil, motor and air temperature, battery SoC, range
- Check-Control list
- number of occupants (belt/seat sensors)
- network conditions, HMI language, trigger reason

```
const[{requestId,sequenceId},currentPosition,recentPositions,navigationDestinationInfo,environmentConditions,vehicleStatus,numberOfPassengers,ccmList,hmiLanguage,poiCapacityRemaining]=yield Promise.all([...
new VehicleStatus_1.default({tirePressure,odometer,tankLevel,oilLevel,motorTemperature,airTemperature,mainBatterySoc,remainingRange})
```
A breakdown call also starts remote-diagnostic PDM collection (`collectPdmResult("BDA00B","BDA00C")`) via ts_diagnostic_service.

**2. Destination.**
- joynr `vs.xcs` / `XCallBackend.notifyXCall`, also `ts.bcallservice`.
- The backend can push `requestXCall` / `requestVoiceCall`.
- The voice leg goes through the telematics unit (ACM `setupCall`).
- The only HTTP request is a GET for third-party call-provider names, which carries no vehicle data. *H.*

**3. Triggers.** *M-H.*
- SOS button, speech, accident or HV-battery-guard triggers, backend request.
- Accident trigger (`triggers.json`):
  ```
  if (res === 'SIGNAL_UNBEFUELLT' || res === 'KEINE_BESCHAEDIGUNG' || res === 'BESCHAEDIGUNGSSTUFE_1') { return false; }
  ```
  The accident flow persists the event and shows a CCM. No automatic send without a user reaction was found.
- No periodic upload.

**4. Gating.**
- Per-service provisioning flags, all defaulting to `DISABLED`: `a_call`, `b_call`, `i_call`, `h_call`, `auto_send_damage_data`, `third_party_call`, …
- There is **no privacy-setting check** in the call path, even though privacy_manager lists `ACCIDENT_INFO` for x_call (default ON).
- No login is needed.
- *(Inference:)* the legal EU 112 eCall is handled by the telematics unit, separately from this app.

**5. Storage.**
- `acall.persist` (damage data), `lastProvisioning.json`.
- Logs contain lat/lon of current and recent positions (PositionInfoRepository). *H.*

---

## 7. Teleservice family

### 7.1 trigger_service (uid 12203), autostart, core app
- **What it does.** It evaluates every app's `triggers.json` query scripts against about 157 allowed interfaces. Position, speed and odometer are polled every 1 s (`config/base.json getIntervalsMs`).
- **No network access from the scripts.** They run in a sandbox: `blackAndWhiteLists.js` blocks `http`, `https`, `net`, `fs`, `require`, `process`, `dgram`. So the trigger engine itself cannot exfiltrate data; it only wakes apps. *H.*
- **What it sends itself:** SDK analytics only. `PLATFORM_BOOT` (`bootType`), `PLATFORM_SHUTDOWN` (`mguLifeTimeMs`), and `TRS_HEALTH_REPORT` (per-app CPU/memory, first after 120 s, then hourly). These are subject to the analytics gate in §2.3. *M.*
- **Gating of apps:** an app's triggers fire only if its provisioning has `-enabled` and `-allowed`. Each app's trigger `localStorage` is capped at 10 KB.

### 7.2 ts_diagnostic_service (uid 12205, v4.31.11), autostart, no login

**Data.**
- VIN, ECU key data, PDM diagnostic-job results (UDS reads, DTC controllers via TASU), I-steps, service pack.
- Heartbeat: speed only as a bucket (`"0-6"`/`">6"`), locked state, parking brake, gear, signal strength, app versions. *H.*

**Destination.**
- joynr `ts.tsrd` (heartbeat), `ts.rtcservice` (key data), `ts.diagservice`/`ts.pdmdata` (results), `ts.pdmupdater`/`ts.wlupdater` (job-list updates).
- PDM result file goes by HTTP PUT via DUMM to an `uploadUrl` supplied by the backend:
  ```
  uploadPdmResult(section,uploadUrl){ yield this.httpClient.uploadFile(section.generatePdmResult(this.vin),uploadUrl)}
  ```

**Triggers.** Mainly backend-initiated wake-up-on-demand: `requestDiagResult`, `requestPdmResult`, `requestKeyData`, `initiateHeartbeat`. It also runs on behalf of x_call, ts_servicecall, ts_battery_guard and ts_rsu_report. The local `triggers.json` entries are all `enabled:false`.

**Gating.**
- **No privacy setting** (privacy_manager has no key for it).
- Limited by a signed ODF whitelist of allowed diagnostic jobs. Temporary sessions last at most 48 h, abort on speed or power-state change, and check the VIN. *M-H.*

**Storage.** `odf.xml`, `pdm.xml` (+ex-factory), `isteps.json`, `servicepack.json`, upload logs, persistent PDM results.

### 7.3 ts_servicecall (uid 12211, "Automatic Service Call")

**Data** (`collectData`): VIN, SW/HW version, model, I-steps, battery charge condition, fuel tank level, odometer, exterior temperature, CBS list, CCM list, key data.
- Note: a setter bug copies values into the wrong fields, so `motorTemperature` actually carries the exterior temperature.

**Destination:** joynr `ts.scallservice` `notifyMaintenanceStatus`, with `debugRefId` = `ts_service_call-<ts>-<VIN>`.

**Triggers:**
- CBS due after ≥60 s of driving, then on reaching a predicted odometer value.
- One of about 60 listed CCM IDs appears or resolves.
- Backend `requestMaintenanceStatus`.

**Gating:** privacy `AUTOMATIC_SERVICE_CALL` = UserEnabled (**default ON**, SecureMobility group) and provisioning `asc`.
```
if(!this.enabledProvisioning) return resolveAscCheck("PROVISIONING_DISABLED"); ... if(!privacySetting) ... "PRIVACY_DISABLED"
```
*H.* **Storage:** `ts_servicecall.json` (CBS/CCM state).

### 7.4 ts_battery_guard (uid 12204, v4.31.3)
- **Data:** VIN, `lowVoltageBatteryLimited`, `deepSleepModeActive`, model, I-steps, SW version, trigger reason. No SoC or position in the current version. The older firmware copy did send SoC and headlight state. *M-H.*
- **Destination:** joynr `ts.tsbgservice` `notifyBatterySleepStatus`. The backend can request status through a provider on domain `VIN-<VIN>`.
- **Triggers:** battery-guard wake-up `OSFG_ERREICHT`, a one-shot `INIT_DATA_CALL` when the privacy setting becomes enabled, and backend request.
- **Gating:** `PRIVACY_FLAG="BATTERY_GUARD"` must be `UserEnabled` (**default ON**). *H.*
- **Storage:** `ts_battery_guard.json`, a ring buffer of the last 5 events.

### 7.5 ts_rsu_report (uid 12207)
- **Data:** VIN, update trigger point (BEFORE_UPDATE / AFTER_UPDATE_SUCCESS / AFTER_UPDATE_ERROR), key data and PDM result from ts_diagnostic_service, SW version.
- **Position only on error:**
  ```
  if("AFTER_UPDATE_ERROR"===triggerPoint){… const coordinates=yield this.vehicleDataImpl.position.get(); …
  ```
- **Destination:** joynr `ts.rsurservice` `notifyRSUStatus`, plus analytics `PLATFORM_UPDATE`.
- **Trigger:** SOME/IP `TeleserviceTrigger.triggerTeleserviceReport` from the OTA gateway.
- **Gating:** **no privacy check found.** `REMOTE_SOFTWARE_UPDATE` exists (default ON) but is not read by this app. Login is required. *M-H.*

### 7.6 ts_service_partner (uid 12209)
- **Data:** VIN (header `BMW-VIN`), language, **current lat/lon on "search nearby"**, chosen dealer key, user bearer token (not inspected).
- **Destination:** HTTPS via DUMM to provisioned `service_url`. GET `/v1` returns the current partner; GET `/v1/search?lat&lon&language`; POST/DELETE `/v1`. No joynr.
  ```
  e={lat:t.latitude.toString(),lon:t.longitude.toString()}
  ```
- **Triggers:** user action or speech intent. Cold boot does a GET `/v1` without position *(inference, M)*.
- **Gating:** user-initiated, login required. Select and delete are refused for guest or secondary users. No privacy setting.
- **Storage:** `current_partner_information.json`.

---

## 8. Connected-service apps

### 8.1 weather (uid 12212, v4.10.49)
- **Data:** vehicle position (subscribed with a 10 s minimum interval), navigation destination, search text, units, language, market, favourites.
- **Destination:** HTTPS via DUMM to provisioned `service_url` (fallback: CDP host `…/vehicle/id7/rest/weather`), endpoints `weather/v1`, `reverseGeocoder/v1`, `geocoder/v1`. **Coordinates are sent unrounded.** *H (verified):*
  ```
  const lat=location.getLatitude(),lon=location.getLongitude(),params={lat:lat+"",lon:lon+"",market:this._market,language:language,...
  ```
- **Triggers:** wakes in the background via the trigger service:
  - a time trigger re-armed at **now + 20 min**
  - a **10 km exit geofence** around the last weather location
  - guidance and connectivity changes

  *(Inference, M:)* each wake fetches with the current position and the destination. The result is a coarse location track every 20 min or 10 km whenever the app is provisioned.
  ```
  const triggerDate=Date.parse(addMinutes(new Date,20)) … TEN_KM_RADIUS=1e4 … transitions:[EXIT_TRANSITION]
  ```
- **Gating:** login and connectivity. **No privacy setting is checked.**
- **Storage:** `locationCache` (coordinates + address, 24 h TTL), `weatherFavourites`. Logs contain coordinates.

### 8.2 oap-bon-newsnext (uid 12217, v4.10.23)
- **Data:**
  - position rounded to 0.1° (~11 km): `parseFloat(location.getLatitude().toFixed(1))` *(verified)*
  - remaining guidance time, country, language
  - user ID = gcid, **or the VIN if nobody is logged in** (`this.userId=gcid||this.VIN`)
  - listening/like/category events
- **Destination:** `ccis-ise.prod.cd-emea.bmw.cloud:5970` `/news-next/api/v1/users` (registration), `/users/<hash>/episodes?lat&lon&driveDuration`, `/users/<hash>/events`.
- **Triggers:** app start/resume, connectivity/language/power changes; event batches about every 15 min (first after ~4 min).
- **Gating:** behaviour events need `MY_PERSONAL_NEWS` (sensitive, **default off**, chosen on a splash screen). **Registration and the coarse-position fetch are not gated.** *H.*
- **Storage:** news cache, interaction DB, event queue, consent flag.

### 8.3 message_handling (uid 12210, v4.54.40)
- **Receives** BMW messages: recalls, product/service/contract info, RSU notices.
- **Sends** read receipts via joynr `rcc.msgsvc` `notifyMessageStatus`.
  - Payload: VIN, gcid, app/platform version, message ID, campaign ID, status (`DELIVERED`, `MESSAGE_OPENED`, phone number dialled, `DEEPLINK_CLICKED`, `MESSAGE_DELETED`, `CONFIRMATION_RESPONSE`).
  - Only for XCC messages and confirmations. *H.*
- **Position** is read locally for the UI only.
- **Gating:** login. No privacy check before receipts. The `XCC_*` settings govern which messages the car receives. Countly is off (`"enableAnalytics": false`).
- **Storage:** up to 100 messages.

### 8.4 connected-onboard (uid 12214, v3.3.26; "Send to car" + Alexa)
- **Data and destinations:**
  - gcid, VIN, model, language.
  - Trip-service GET/PUT/DELETE on `/api/gateway/connected/trip-service/v3/motorist/<gcid>/…`: destinations sent from the phone, plus their activation status.
  - Alexa vehicle-user mapping: `/api/gateway/avsclient/v1/vehicleusermapping` with header `bmw-gcid`, refreshed every hour (`setInterval(...,36e5)`).
  - joynr `vcs.omg` `registerNotification({appId,appVersion,vin})`.
- **Last-mile parking location:** gated by `LAST_STATE_CALL`, and the upload function is a stub that sends nothing: `sendLastMile(lastMileTrip){return this.logger.info(...),!1}`. *H.*
- **`client-analytics`:** a REST client exists (`user_id: gcid`, OS, locale), but no caller was found. *M.*
- **Gating:** login/token. Alexa needs an Amazon login.
- **Coverage:** the Alexa audio path was not fully traced.

### 8.5 smartinterior (uid 12218; Intelligent Personal Assistant, "Caring Car", scenes, smart window opener)
- **Data:** seat heating/ventilation stages in scenes, window opening, geofence enter/exit for user-saved places (POWI IDs and names), scene definitions, VIN + token.
- **Destinations:**
  - `CDCCoreService.sendEvent` (campaign 5, jobs 4/5)
  - joynr `vcs.vehicletask` `pushSceneUD` / `requestScenesML` (*inference:* server-side learned scenes)
  - Countly events (`SmartWindowOpener*`, program activation, with guest flag; no coordinates seen)
  - content downloads from `ices-ise.*.bmw.cloud`
- **Gating:** CDC events need `LEARN_DRIVE_BEHAVIOR`; smart window also needs `LEARN_VEHICLE_POSITION`. Both are sensitive, so **default off**. Guests are refused; login is required. *H.*
- **Storage:** POWI and scene descriptors are marked `"sync": true` *(inference: cloud-synced profile, M)*.

### 8.6 cmusic (uid 12215; Connected Music / Spotify)
- **Data:** VIN header (`BMW-Vin`), Spotify browse/search/queue requests, and a **4-second audio fingerprint** for song recognition (`getFingerprint({fingerprintLength:4e3})` → POST `fingerprint/track`).
- **Destination:** via DUMM to the provisioned URL. The default is an integration host `service-oe.int.cd-emea.bmw:7570`; the code also defines `/oe/service/{statistics,uploadlog}`, but no caller was found. *L.*
- **Gating:** login + Spotify session. No privacy check found, even though `ONLINE_ENTERTAINMENT_STATISTIC` exists in the privacy menu. *M.*

### 8.7 mlaptimer (uid 12219, "M Laptimer OAP CN")
Reads position, speed, RPM, longitudinal/lateral acceleration, pedal, steering, drift data. **No app-level network code** was found. The best-lap GPS trace is stored per user in `sessionsDirectory/last_session.json` and deleted on deactivate. Only SDK analytics could leave, and it has no Countly key. *M-H.*

### 8.8 oap-license-app (uid 12216)
Shows open-source licences. The only data emitted is an analytics `ID7_view` event (`viewedState` = page / hidden / speedlock), subject to the analytics gate. *H.*

---

## 9. Open questions

1. **Provisioning content (the decisive unknown).** The live provisioning document could not be read from the dumps. It decides:
   - the `data-collection` sub-flags (`pmh`, `lsc`, `tripstatistics`)
   - x_call's per-service flags
   - `asc` for ts_servicecall
   - `analytics`/`app_analytics` for the platform analytics
   - all service URLs

   Candidate sources on the car: x_call `lastProvisioning.json`, the provisioning service cache.
2. **Current privacy-switch states.** Reading the `PrivacySettings.allSettings` values (privacy_manager `PersonalStorage`) would turn "default ON" into "is ON".
3. **CDC vs. privacy_manager defaults** (partly answered: on one car the CDC entries stayed enabled and unconfirmed, and apps read them as `UserEnabled`; see §5). CDC inserts `CDC_*` entries with `enabled:true, confirmed:false`, while privacy_manager treats those groups as sensitive and defaults them off. Which value wins after start-up, and does the "unconfirmed settings" pop-up appear?
4. **GLA persistence.** `PrivacySettingsChangedUseCase` forces `GLOBAL_LOCATION_ACCESS` to enabled/confirmed outside China on every settings change. Does a user's "off" survive, i.e. is the forced value written back to the service? data-collection only drops GPS if it reads exactly `UserDisabled`.
5. **Native CDCCoreService.** Where does it upload campaign events (`BACKEND_MGU`/`BULK`)? Does it enforce `CDC_*` privacy states? Which campaigns/jobs are installed (`job.registry.json`, `campaign.registry.json` in the CDC data dir)?
6. **joynr broker and DUMM.** Which MQTT broker hostname is used (cluster-controller config, not in the app bundles)? Which identifying headers or client certificate does DUMM add to "b2v" HTTP requests from weather and newsnext?
7. **Backend-initiated diagnostics.** How often, if at all, does BMW call `requestDiagResult` / `initiateHeartbeat` on this VIN? Is any of it tied to a ConnectedDrive/Teleservices contract? Not determinable statically.
8. **pdm.xml contents.** What exactly is in the "key data" (`KEY015`/`KEY018`) and breakdown-call PDM sections, i.e. which ECU values and DTCs? These ship as `ts_diagnostic_service/data/pdm_exfactory.xml` and could be analysed next.
9. **Weather background fetches.** Is a backend request really made on every 20-min/10-km wake when the HMI is closed? This is inferred from the trigger design and needs a DLT capture to confirm.
10. **Countly users.** The data-collection CHANGELOG says Countly was removed. For the other apps that bundle Countly keys (connected-onboard prod keys; license-app, smartinterior, cmusic), does the backend actually provision `app_analytics`?
11. **Local logs.** x_call and weather log raw coordinates, and many `debugRefId`s embed the VIN. How long are DLT/journal logs retained, and are they ever pulled by CDC jobs (`dlt` API) or diagnostics?

---

## Appendix: note on "allowed" interfaces

The per-app `someipInterfaces/` directories (`someipInterfaces/oap_<uid>/`) list 39–169 SOME/IP services per app. About 40 of them appear for every app: GPSData, Telephone, UserAccount, USSO, DUMM, PrivacySettings, Provisioning and others. They are the shared SDK baseline. **An interface being allowed is not evidence that an app reads it.** This report counts a data item as collected only where the app code reads it and puts it in an outgoing payload.

The broadest grants:
- oap-cdc-2018: 169, used by remote campaign scripts
- trigger_service: 154, used by the sandboxed trigger evaluator
- smartinterior: 78

A per-app list can be regenerated from the directory listing.
