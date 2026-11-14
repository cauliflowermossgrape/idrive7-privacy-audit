# 02 — Stock native system services: what is collected, where it goes, what gates it

Scope: native daemons and configs on the **stock root filesystem** (partition 8, sector 5269504) of a stock MGU eMMC image. The JavaScript OAP apps are covered in another report. Method: read-only `debugfs` (`cat`/`dump`/`rdump`) plus `strings`/`grep`. No binaries were run. Partition 10 (`/var/opt`) was checked for **directory names only**.

Labels used:
- **code present**: the logic exists in the binary or library.
- **configured/enabled**: a unit/config turns it on in this image.
- **gated by X**: it only works if X allows it.
- **unknown**.
- Confidence is **H**, **M** or **L**. Anything marked *Inference* is not shown directly by the evidence.


---

## 1. Summary table

| Service (binary / unit) | Purpose | Data it handles / sends | Destination | Gating | Status / confidence |
|---|---|---|---|---|---|
| **Telematics** (`/usr/bin/Telematics`, `telematics-platform.service`, uid `tm_12000`) | The head unit's internet gateway. Its modules: DUMM (data upload manager), Http (libcurl), USSO/OAuth device-code login, Provisioning/OTA config, joynr backend handler, ACM, eCall proxy, cookie manager, "ttclient" TCP proxy | Everything that other daemons upload: VIN (subject to "VIN protection"), tokens, HTTP payloads | BMW backend URLs taken from the **signed provisioning XML**. Traffic goes out on vlan77 → TCU/ATM gateway `160.48.199.226` | Provisioning ("Enabled by provisioning"), connectivity through the TCU, HU VIN protection, firewall uid allow-list | enabled (late.target); H |
| **cdc-native** (`cdc-native.service`, uid `tm_12007`) | **Crowd Data Collector** client. Runs campaign-driven event collection and FAST/BULK upload | `CdcEvent` with eventId, campaignIds, jobId, TTL, priority, use-case data. Identifier types include `VIN`, `HASHED_VIN`, `TRIP_ID`, `PERSONALIZATION_ID`. Also DTC status updates | joynr `com.bmw.cc.vsd.erdcdc2fcd` (SensorDataIngestion, BulkUploadManager) and the DUMM bulk upload | Unit condition `/run/variant/cdc/active`, which comes from vehicle **coding `SYSTEM_CONFIGURATION.CDC_ENABLE`**; campaigns come from the backend/provisioning; DIAG can trigger a campaign. **No reference to dataprivacyd** | code present, enabled when coded; H for code, unknown whether active on this car |
| **healthtelemetryd** (`healthtelemetryd.service`) | "Health statistics gathering and preparation for sending them through CDC" | Hashed VIN (`vehicleId`, `hashEncodeVin`), SW version/variant, crash records (process, thread, signal, module offsets), wakeup/reset reasons, lifecycle counters, eMMC wear/CID/serial, free memory | JSON files in `/var/opt/public/sin/health_telemetry` (group `tm_oap_app`). *Inference:* an OAP/CDC component then sends them | No privacy setting referenced | enabled; H for collection, M for the upload path |
| **rsu-agent** (+ `rsu-delta-daemon`, `rsu-disk-manager`, `rsu-lighttpd`) | Remote Software Upgrade (OTA) | VIN, VCM address, **mileage**, vehicle configuration (SVT), update reports, and **logs on backend trigger** (`doSendSpecificDetailedLogs`) | joynr `com.bmw.rsa.v6.RsuBackendService` and `RsuVehicleTriggerService` | **Privacy setting `REMOTE_SOFTWARE_UPDATE`** (VEHICLE scope): "RSU is disabled for privacy reasons". Also needs provisioning and an upload URL | enabled; H |
| **speechd** + **natp** (Nuance/Cerence VoCon/Dragon Drive, uid `spe_9000`) | Voice assistant, hybrid on-board/off-board | Off-board ASR audio/TTS, **phonebook upload**, **favourite-POI upload**, VCM data upload, VIN, third-party session (Alexa threshold string present) | Off-board speech backend from provisioning (joynr `com.bmw.cc.inf.speech.hvd.v03`, curl). Firewall lets uid 9000 reach vlan77 TCP 5540/5650/…/8080 | Privacy `SPEECH`, `WAKEUP_WORD`, `ALWAYS_LISTENING`; HMI "Offboard flag"; provisioning ("No provisioning to send HTTP request for Phonebook upload") | enabled on high/highf/mid HW; H |
| **NavController** (+ NavigationFully/Basic, mapdataservice, navlocation) | Navigation online services | Online traffic, online routes, dynamic POI, **parking: ultrasonic (USS) parking-space measurements upload**, parking situations, Learning Navigation (estimated destinations), geofencing | BMW online services. Test/E2E defaults are compiled in (see hostnames); production values come from provisioning (*Inference*) | Privacy `ONLINE_TRAFFIC`, `ONLINE_ROUTES`, `ONLINE_DESTINATIONS_AND_DYNAMIC_POI`, `PARKING`, `LEARNING_NAVIGATION`; NavController has its own `traffic/privacy/PrivacyManager.cpp` | code present; enabled on nav variants; H for code, M for what is uploaded |
| **mapupdaterd** (`mapupdaterd.service`) | Over-the-air map updates (MUPI) | Current car position (needed for the update-region check), DB regions, reports; `DebugUploadUrl` | joynr `com.bmw.cc.nav.mupi.control.MUPI_v23` | Privacy `MAP_UPDATE`, provisioning | enabled on nav variants; H/M |
| **persod** (personalisation) | User accounts (BMW ID / GCID), profiles | Profile data upload ("Sending upload request to backend"), GCID↔VIN binding | Backend via DUMM | Privacy `USER_PROFILE_SYNC` (*Inference*: persod does not reference the privacy API directly); login state | enabled; M |
| **dataprivacyd** | Holds the privacy switches (25 categories, USER or VEHICLE scope) | Settings only | Local SOME/IP service `de.bmw.infotainment.dataprivacy.privacysettings` | — | enabled; H |
| **cluster-controller** (joynr, uid `tm_12002`) | MQTT messaging bus to the BMW backend | All joynr traffic (CDC, RSU, MUPI, SFA, speech) | Brokers from provisioning. Compiled-in `tcp://mqtt.bmwgroup.net:1883` and `tcp://mqtt.e2e.cd-emea.bmw:8883`. Firewall: uid 12002 → vlan77 TCP 1883/8883 | Provisioning | enabled; H |
| **sfa-master** | Secure Feature Activation (paid features/FSC tokens over the air) | VIN, feature states, token packages | joynr `de.bmw.infotainment.telematic.sfaota` | Provisioning, backend | enabled; H |
| **necemad** + `stunnelconfiggenerator` + `/etc/stunnel/stunnel.conf` | Vehicle certificate management (BMW PKI "OnlineCertificationService"); TLS tunnel for the China mini-program platform | Certificate requests (CSR, VIN-bound — *Inference*) | `pki.bmwgroup.com` schema strings; `tai-mpp.int.cd-cn.bmw:7680`; `vcis-mp*.e2e.cd-cn.bmw` | China variant only (*Inference*) | code present; M |
| **tencentdaemon** (TAI, uid `cns_12704`) | Tencent mini-program platform launcher (China) | — | Via the OAP TAI interface | Market (*Inference*: China only); firewall allows only cns_12701/12703 egress | enabled unit, does nothing outside CN (*Inference*); M |
| **crashhandler** / **dlt-cdh** / **systemdcoredump** / **recmgr** | Crash dumps and restart statistics | Core dumps (process memory!), GPU hangs, crash reports, restart statistics DB | Local eMMC. Exported over **DLT file transfer** or **HTTP :8081** to a connected tester (not internet) | Firewall closes 8081 by default; HTTP server stopped after the "burn flag" (mileage > 254 km) | enabled; H |
| **dlt-daemon / dlt-system / dlt-recv / dlt-alt-recv / log-trace-manager** | Diagnostic Log & Trace | Journald, /proc stats, screenshots, internal trace (verbose, all apps). Logstorage of up to 1800 × 1 MB, **encrypted** to `trace.cert` | Local. DLT TCP 3490 and HTTP 8082, both dropped by the firewall by default. USB copy; RSU log upload on backend trigger | FSC (Freischaltcode) for internal/external tracing, burn flag, debug mode | enabled; trace off on this unit (`ecu_trace_mode_off` flag); H |
| **mgusecdiagd** + **nodestartupcontroller** → `debug.target` | Debug-mode gate | — | Enables **sshd on :22** and **root autologin on serial ttyS2** | Signed, device-bound **debug token**, or SecureBoot off | not active by default; H |
| **EthernetDiagnostics / eth-diag** | BMW HSFZ diagnostics over Ethernet (port 6801), flashing (8888) | UDS diagnostics, including DTC/env data | Workshop tester via OBD → BDC gateway (vlan73/socnet0) | Physical access, BMW diagnostic security | enabled; H |
| **CarPlay / aapd (Android Auto) / CarLife / Miracast / mdnsd** | Phone projection | Projection streams; vehicle data exposed to the phone | Phone over the Wi-Fi hotspot `wlan_bridge` / USB | User pairing | enabled; M (not analysed in depth) |
| **mediaspotify** (container) | Spotify | Account/streaming | Internet through SOCKS (`libpreloadedsocks.so`, `10.1.1.1:1080`) | Provisioning, user login | code present; M |
| **SXMApp / SXMTrusted** | SiriusXM 360L (US) | Streaming API | `streamingapi-*.mountain.siriusxm.com` | Privacy `SIRIUSXM`, US market | code present; M |
| **mediaapp Gracenote** | Music recognition/metadata | Audio fingerprints | `ConfigServiceURL http://160.46.254.249/gn/service/rest/2/fingerprint` (`UseConfig=false` → the URL comes from provisioning) | Provisioning | code present; M |
| **nv_uplink_info / nv_dsrc / nv_vics** (Asia nav) | Japan DSRC/ETC2.0 "uplink" | **Driving history**: positions, forward/side acceleration peaks, yaw angle, behaviour info | Roadside DSRC units (Japan ITS spots) | Variant `/run/variant/navigation/asia` | code present; *Inference*: inactive on EU cars; M |
| **icam2proxy** | Camera arbiter; Drive Recorder / Remote Theft Recorder export | Camera video | USB or Wi-Fi export. *Inference:* the remote upload runs elsewhere | Coding `SYSTEM_CONFIGURATION.DRIVE_RECORDER`; privacy `REMOTE_THEFT_RECORDER`, `REMOTE_360` | code present; M |
| **pim** | Contacts, SMS, e-mail, calendar from the phone (BT MAP/PBAP) | Contacts, SMS, e-mail bodies, calendar | Local SQLite (other report). Speech can upload the phonebook (see speechd) | BT pairing | enabled; H |
| **Monitor**, **EnhancedTestabilityService** | CPU/RAM/IO monitoring to DLT; SOME/IP test events | System metrics | DLT, local only | — | enabled; H |

---

## 2. Backend hostnames / URLs found

Real backend endpoints are mostly **not hard-coded**. They arrive in the signed provisioning XML (`bmwprovsigned` / `bmwprov`, sections `prov`, `dumm`, `joynr`, `routing_table`). The names below are what is compiled in or configured. Many are test/E2E/integration defaults or documentation links.

| Hostname / URL | File | Notes |
|---|---|---|
| `tcp://mqtt.bmwgroup.net:1883` | `/usr/bin/cluster-controller` | joynr MQTT default broker |
| `tcp://mqtt.e2e.cd-emea.bmw:8883` | `/usr/bin/cluster-controller` (next to `/data/joynr_additional_brokers`) | E2E (test) ConnectedDrive EMEA broker |
| `tai-mpp.int.cd-cn.bmw:7680` | `/etc/stunnel/stunnel.conf` (`[Netscaler CN]`) | China TAI mini-program platform, integration env |
| `vcis-mpw.e2e.cd-cn.bmw`, `vcis-mpm.e2e.cd-cn.bmw` | `/usr/bin/stunnelconfiggenerator` | China, E2E |
| `https://los.e2e.cd-emea.bmw:6740/localsearch-service/v2/POIs` | `/usr/bin/NavController` | online POI search (E2E default) |
| `https://paf.e2e.cd-emea.bmw:6760/paf/v1/` | `/usr/bin/NavController` | E2E default |
| `https://vlbs.e2e.cd-emea.bmw:6760/ggps/emea-int/ggps/v1/parkingsituations` | `/usr/bin/NavController` | parking situations (E2E) |
| `https://int-b2v.bmwgroup.de/acs/cfas-int/platform/services/traffic-quality/park-eu` | `/usr/bin/NavController` | integration B2V backend, parking |
| `https://int-cngw.bmwgroup.de/cngw/park-eu` | `/usr/bin/NavController` | integration |
| `https://demo-gateway-1232419531.eu-central-1.elb.amazonaws.com/v1.3` | `/usr/bin/NavigationBasic` | AWS demo gateway (test leftover) |
| `streamingapi-bmw1-prod-360.mountain.siriusxm.com` (+ `-emma1-stage`, `-emma1-beta`) | `/etc/mediaconfig/sxmapp_config_hu.xml` | SiriusXM 360L |
| `http://160.46.254.249/gn/service/rest/2/fingerprint` | `/etc/mediaconfig/mediaapp_config_hu*.xml`, `_midbase.xml` | Gracenote fingerprint service. *Inference:* the IP is in BMW's 160.46/16 block. Overridden by provisioning |
| `pki.bmwgroup.com` (XSD namespace only) | `/usr/bin/necemad` | BMW PKI online certification service schema |
| `maps.google.com`, `earth.google.com`, `labs.google.com` | `/usr/bin/NavigationBasic` | KML/GPX namespace and icon strings, not live calls (*Inference*) |
| `wss://localhost:4243`, `ws://localhost:4242`, `mqtt://localhost:1883` | `/etc/joynr/*.settings`, `/etc/sfa-master/config.toml` | local joynr only |
| `asc.bmwgroup.net`, `asc-repoa.bmwgroup.net`, `asc.bmw.com`, `confluence.harman.com`, `naviwiki.harmanbecker.com`, `elvis.harman.com` | mediaconfig XML comments, HmiMain3D, NavigationCoding, `.hbtc` files | developer documentation / ticket links only |
| `http://proxy.tld:3128` | `/etc/opkg/opkg.conf` | placeholder sample |

Internal (in-vehicle) addressing: the MGU is `160.48.199.99` (vlan73 = vehicle backbone with BDC/ATM2/Kombi/WAVE…). vlan77 `160.48.199.225/29`, gateway `.226` = **internet path via the telematics unit**. The phone hotspot is `wlan_bridge 172.16.222.97/27`. vlan144 = RSE. Source: `/etc/systemd/network/*`, `/usr/bin/firewall-tools.sh`.

No hard-coded `*.nuance.*`, `*.cerence.*`, `*.here.com`, `*.amazon.*` (except the demo ELB), `*.apple.com`, `*.spotify.com`, crashlytics/sentry or other analytics-SDK hosts were found in `/usr/bin/*` or `/etc`. `/usr/lib` (about 3000 libraries) was only partly scanned (the rsu libs).

---

## 3. How the head unit reaches the internet

1. **Only through vlan77 to the telematics unit (TCU/ATM)**. Telematics pushes the routes and DNS servers:
   - `/usr/bin/setup_vlan77.sh`: `# Reads a list of CIDR networks from Telematics binary via stdin to be configured on vlan77` … `ip r add "$r" via 160.48.199.226 dev vlan77`
   - `/usr/bin/updateResolvConf.sh`: `# Reads a list of addresses from Telematics binary via stdin to be configured as nameservers`
   - `/etc/dnsmasq.conf`: `resolv-file=/etc/resolv.dnsmasq` (→ `/var/volatile/resolv.conf`), `interface=vlan77`.
   - configured; H.
2. **Firewall egress allow-list by Unix uid** (`/etc/nftables/firewall-mgu-hw-appl-release.nft`):
   ```
   oifname vlan77 skuid { 12000, 12201-12700 } ip protocol tcp accept
   oifname vlan77 skuid 12703 ip protocol tcp accept   /  skuid 12701 …
   chain outputChain12002 { oifname vlan77 tcp dport { 1883, 8883 } accept }
   ```
   - Allowed: uid 12000 = `tm_12000` (Telematics); 12201–12700 = dynamic OAP app uids (`/etc/uidrun.conf`); 12002 = joynr; 9000 = speech (`outputChain9000`); `ent_mtrusted` (SXM); 12701/12703 = China services.
   - `defaultpolicy.nft` appends `jump logblocked` (`log … "Blocking unknown connection: " drop`). *Inference:* the two files merge into the same chains, so any other uid is dropped and logged. M-H.
   - Consequence: cdc-native (uid 12007), healthtelemetryd, crashhandler, rsu-agent, persod and others **cannot open internet sockets themselves**. They hand data to Telematics/DUMM, to joynr/MQTT, or to an OAP app.
3. **No SIM/contract.** *Inference:* without a working TCU data connection and valid provisioning, nothing leaves the car. Telematics refuses work without provisioning:
   - `Cannot request keep alive: no provisioning data`
   - `Incomplete vehicle data. Will not send provisioning request.`
   - `Dumm provisioning data is not complete!`
   - Speech: `No provisioning to send HTTP request for Phonebook upload`.
   - M-H. Whether the TCU still has an active eSIM/APN without a ConnectedDrive contract cannot be told from the MGU image (EsimProxy interface present). Unknown.
4. **Phone Wi-Fi does not give the head unit internet.** *Inference* from the firewall: the `wlan_bridge` rules only accept projection/mDNS ports, and only CarPlay's uid 13002 may send arbitrary traffic to `wlan_bridge`. M.
5. **IPsec (strongSwan)** is used to in-car ECUs only: `firewall-ipsec-{atm2,kombi,wave,bcp,rse,mgu}-open.sh` with `ATM2_IP=160.48.199.97` etc. Not a VPN to the backend. H.

---

## 4. Per-topic findings

### 4.1 Crowd Data Collector (CDC) — campaign-based fleet data collection
- `/lib/systemd/system/cdc-native.service`: `ConditionPathExists=/run/variant/cdc/active` … `User=tm_12007`. It is in `late.target.wants`.
- `/usr/bin/runtimevariantprovider`: `RuntimeVariantMGUCodingProvider::isCrowdDataCollectorValid(CodingSYSTEM_CONFIGURATION::eCDC_ENABLE)`, string `SYSTEM_CONFIGURATION.CDC_ENABLE`.
  - This is **gated by vehicle coding**. H.
- `/usr/bin/cdc-native` (embedded Avro schema, namespace `com.bmw.cc.vsd.cdc`):
  - `"doc" : "At least one element. Links to the campaign which caused the data collection. Campaign must exist in campaign management."`
  - `"symbols" : [ "NO_IDENTIFIER", "VIN", "RESERVED_1", "HASHED_VIN", "TRIP_ID", "PERSONALIZATION_ID", "DEBUG_VIN", "RTM_Realtime", "RTM_Supplemental", "ECU_UID", …]`
  - `"doc" : "Time to live in milliseconds… also for the final analytics node."`
- Transport: `JoynrEventSender` → `SensorDataIngenstionService.processMessages` (joynr `com.bmw.cc.vsd.erdcdc2fcd`). `DummEventSender` → `BulkUploadManagerService.getBulkUploadResource` / Telematics DUMM.
  - FAST and BULK paths with flush intervals, min/max sizes and TTLs that come from provisioning (`ProvisioningParser`).
- Other inputs:
  - DTC updates (`cdc::diag::DtcDispatcher::handleDtcUpdate … ErrorMemoryTypes … EnvCondStruct`).
  - Diagnostic jobs `SteuernCdcTriggerCampaignRequest`, `SteuernCdcClearEventbuffer`, `StatusCdcCurrentJobs`.
  - `CrowdDataCollector` / `CrowdDataCollector21` interfaces. Clients include `sdip-ar` and other ECUs (*Inference*).
- **No privacy-setting reference**: `grep -la privacysettings /usr/bin/*` matches only HmiMain3D, SXMApp, NavController, dataprivacyd, speechd. cdc-native is not among them. *Inference:* CDC is gated only by coding, campaigns, provisioning and possibly the backend, not by the user's privacy menu. M.
- What the campaigns actually collect is defined server-side ("Use-case-specific data. Its format depends on the schema specified by the data collection job"). Unknown.

### 4.2 Health telemetry
- `healthtelemetryd.service`: `Description=Health statistics gathering and preparation for sending them through CDC.`
- Strings in `/usr/bin/healthtelemetryd`:
  - `std::__cxx11::string VinTools::hashEncodeVin(const string&)`, `vehicleId`, `softwareVersion`, `softwareVariant`
  - `lastCrash totalCrashes crashId processName threadName signalId ipModuleName raModuleName`
  - `WAKEUP_REASON_WATCHDOG_RESET … WAKEUP_REASON_REMOTE_UPDATE`, `lifecycleCounter`, `lifeTimeWriteKbytes badBlockRuntimeInfo eraseCounters productSerialNumber`, `systemMemFree`, `heartbeat`
  - `/var/opt/public/sin/health_telemetry`, `event_%%%%%%%%%%.json`, `health_sessions.db`, state `AvailableForSending`
- `/etc/tmpfiles.d/*`: `d /var/opt/public/sin/health_telemetry 2750 sin_healthtelemetry tm_oap_app`. The **OAP app group can read the JSONs**. *Inference:* an OAP app is the sender; see the OAP report.
- Status: H (collection); M (upload).

### 4.3 Remote Software Upgrade (RSU / OTA)
- `/usr/lib/rsu/librsu-agent-main.so.0.42.0`:
  - `Add VIN, VCM address and mileage to session for usage with Cobra and/or new application image`
  - `Uploading vehicle configuration to` / `Uploading UpdateReport to` / `Logs uploaded to backend`
  - `Received sendSpecificDetailedLogs trigger from backend, initiating send logs`
- Gating:
  - `RSU disabled in privacy settings`, `Unable to initiate sending logs because RSU is disabled for privacy reasons`. The privacy key is `REMOTE_SOFTWARE_UPDATE`, scope `VEHICLE` (it applies to every user).
  - `librsu-agent-vehicle.so` contains `PrivacySettingsProvider`.
  - Exception: `Ongoing FSC-only update, ignoring privacy settings change`.
  - Status: H.
- The RSU agent can start a full internal trace for the duration of an update (`librsu-agent-logandtrace.so`: `Full internal trace already running.`). M.
- `/etc/rsu/rsu-config.json`: local RSU protocol server at `160.48.199.99:8888` (in-vehicle). `testerOptions` are all `false` except `bypassMobileCodes: true`.

### 4.4 Privacy settings (dataprivacyd)
- `/etc/dataprivacyd/dataprivacyd-default-settings.json` (defaults: which scope owns each switch):
  - `"REMOTE_SOFTWARE_UPDATE": "VEHICLE"`, `"REMOTE_INCAR": "VEHICLE"`, `"REMOTE_INCAR_DWA": "VEHICLE"`
  - `"ONLINE_TRAFFIC": "USER"`, `"SPEECH": "USER"`, `"ALWAYS_LISTENING": "USER"`, `"LEARNING_NAVIGATION": "USER"`, `"REMOTE_360": "USER"`, `"REMOTE_THEFT_RECORDER": "USER"`, `"DRIVER_CAMERA_SYSTEM": "USER"`, `"LAST_STATE_CALL": "USER"`, `"VEHICLE_FINDER": "USER"`, `"USER_PROFILE_SYNC": "USER"`
  - Other keys: `CHARGE_NOW`, `LEARNING_MAP`, `MAP_UPDATE`, `ONLINE_DESTINATIONS_AND_DYNAMIC_POI`, `ONLINE_ROUTES`, `PARKING`, `WEATHER_ON_MAP`, `WAKEUP_WORD`, `AUTOMATIC_TIME`, `SIRIUSXM`, `NCAP_SPEED_LIMIT_INFO`.
- The values are USER/VEHICLE **scope**, not on/off. The on/off state is persisted per user and for the guest:
  - `Loaded guest persistency settings:`, `Error: found VEHICLE setting in the user persistency!`
- Remote-service availability is read from the ATM:
  - `ATM Remote Servi…de.bmw.infotainment.remoteservices.RemoteServiceSetting`, `LSC_CUSTOMER_ENABLED LSC_NOT_ENABLED LSC_OTD_ENABLED`, `REMOTE360_AVAILABLE`.
- Consumers found: speechd (`offboardFlagChangedByDataPrivacy`), NavController (`Online Dynamic POI is disabled (Privacy Manager)`, `Parking switch in Privacy Menu changed to:`), mapupdaterd (`Privacy settings:`), RSU (above), SXMApp, HmiMain3D.
- **Not covered by any switch:** CDC, health telemetry, crash/DTC data and DLT. No `PRIVACY_MODE` string was found in the dumped binaries. H.

### 4.5 Provisioning (backend-controlled configuration)
- In `/usr/bin/Telematics`:
  - `Failed to parsing OTA xml, 'bmwprovsigned' and 'bmwprov' are unavailable`
  - `DAS does not contain one or more of the sections: 'prov', 'dumm', 'joynr', 'routing_table'`
  - `DTC_PROVISIONING_WITHOUT_SIG_OTA set`
  - `AutoTime disabled from provisioning`, `Enabled by provisioning:`, `Cannot start time syncronization: component is not enabled by provisioning or HMI`
  - `Unsupported country alpha code`
- Telematics also handles `SECURITY_DEBUG_MODE` (`DiagSecurity proxy available. Subscribe to SECURITY_DEBUG_MODE`) and `HU VIN protection is activated`.
- *Inference:* the backend decides per car and market which services exist, with which URLs, and the CDC flush/size parameters. H for the mechanism; the content is unknown (persisted provisioning lives in encrypted `/var/opt` — see the stored-data report).

### 4.6 Voice assistant
- `/etc/natp/natp.cfg`: `# COMPANY : Nuance Communications Deutschland GmbH`, `…DragonDriveAsrService, ENLUService`. `/etc/natp/json/toplevel.json`: `"version": "VoConHigh 1.0"`.
- `/usr/bin/speechd` source paths: `speechd/offboard/phonebookuploader.cpp`, `favoritepoiuploader.cpp`, `vcmuploader.cpp`, `speechpreconnect.cpp`.
- Log strings: `Pending request to delete all phonebook from backend`, `Phonebook Sync settings has been changed by HMI.`, `Alexa Threshold is not ok`, `Offboard flag has been changed by HMI`.
- Temporary audio files: `/tmp/speech/offboard/client.crt` (a cert file exists; not read), `/tmp/speech/third_party.pcm`.
- Status: code present/enabled; gated by privacy `SPEECH`, the HMI off-board flag and provisioning. H.

### 4.7 Navigation online services, parking crowd data, position
- `/usr/bin/NavController`:
  - `components/parking/ussupload/src/parking/ParkingUssUploadAdapter.cpp`
  - `dataUltrasoundSensorParkingSpaceLength=`, `ussCollectionMode:`, `ussUploadMethod:`, `ParkUssEvent.json`, `Call ComControl startHttpUploadTransfer`
- *Inference:* parking spaces measured by the ultrasonic sensors are uploaded with location, an "on-street parking" crowd function. Gated by privacy `PARKING` and provisioning. M-H.
- Learning Navigation: `LearningNavigationController.cpp`, `LearningNavigationPersistenceClient` (local), `LearningNavigation was turned off`. No upload string was seen for it. M.
- **No `FCD` / "floating car data" / "swarm" / "Local Hazard" strings** were found in NavController. Hazard data is likely handled by other ECUs or OAP apps. Unknown.
- mapupdaterd: `Current car position not available! Aborting update check!`. *Inference:* the position or region goes to the MUPI backend. M.
- Positioning: `gnssd`, `NavigationPositioning`, `navlocation` (geofencing service `de.bmw.infotainment.navigation.geofencing.Geofencing:v2_0`). These are local services. Consumers (OAP/CDC) may export positions. Unknown.

### 4.8 eCall / bCall / remote services
- The MGU only holds proxies: Telematics `ECallProxyService`, `libde.bmw.infotainment.telematic.ecall*`, `remoteservices`. The eCall modem logic sits in the TCU/ATM. The MGU side is HMI and voice (*Inference*). M.
- `LAST_STATE_CALL`, `REMOTE_360`, `VEHICLE_FINDER`, `REMOTE_THEFT_RECORDER`, `REMOTE_INCAR(_DWA)` exist as privacy switches. Execution is mostly on the ATM/cameras. Unknown on the MGU.

### 4.9 Projection / media
- CarPlay (`/usr/bin/carplay -c /etc/cinemo/cinemo_options.xml`), Android Auto `aapd`, CarLife (Baidu), Miracast, `mdnsd`: local to the phone. Not analysed further.
- Spotify runs in a container with `LD_PRELOAD=/usr/lib/telematics-platform/libpreloadedsocks.so` (`/etc/mediaconfig/mediaspotifycontainer_config_hu.xml`) and a veth to `10.1.1.1`. The firewall accepts `vethhost0 … tcp dport 1080`.
  - *Inference:* Telematics acts as the SOCKS proxy to the internet. M.
- Gracenote online lookup: see hostnames; `<UseConfig>false</UseConfig> <!-- if true then config values are used instead of the provisioning values -->`.

### 4.10 China / Japan specific
- China:
  - `tencentdaemon` → `TaiDaemonOap`, `servicelauncher`.
  - stunnel `[Netscaler CN] … connect = tai-mpp.int.cd-cn.bmw:7680`, with cert path `…/mgu-tls/secureboot_off/TLS_enduserCert.pem` (path only).
  - CarLife.
- Japan:
  - `nv_uplink_info`: `DSRC Uplink DrivingInfo byteSize:%d`, `Send forwardAcc peak : %d current : %d`, `Send yawAngle peak…`, `CheckDistGap CurrentPosition : %d,%d`.
  - The NV* units carry `ConditionPathExists=/run/variant/navigation/asia`.
  - Driving-behaviour history sent to roadside DSRC. M.

---

## 5. Local logging and persistence

| What | Path | Retention / size | Evidence |
|---|---|---|---|
| journald | RAM | `Storage=volatile`, `RuntimeMaxUse=12M` | `/etc/systemd/journald.conf` |
| DLT daemon | ring buffer in RAM (`RingbufferMaxSize = 32500000`); `/tmp/dlt.log`; `PersistanceStoragePath = /var/opt/public/sin/dlt-daemon` (log-level persistence) | volatile, except the settings | `/etc/dlt.conf` |
| **Internal trace** (dlt-recv offline logstorage, verbose, all apps) | `/run/logntrace/internaltrace` → `/mnt/share/sin/internaltrace` (= `/var/opt/hdshare/sin/internaltrace`, eMMC p10) | `FileSize=1000000`, `NOFiles=1800` (about 1.8 GB). Encrypted (CMS) to `/etc/logntrace/certificates/trace.cert` (public cert; not read) | `/etc/dlt-recv.conf`, log-trace-manager strings `Did not create CMS Enveloped Data due to missing Certificate` |
| Alt trace on demand | `/run/logntrace/...` (`dlt-alt-recv.conf`, 1800 × 1 MB) | volatile | `/etc/dlt-alt-recv.conf` |
| Trace-mode flag | `/var/opt/target/logntrace/ecu_trace_mode_off` | **present on the examined unit** (0 bytes) | debugfs ls p10. The internaltrace dir and `tm/dumm` spool are **empty** |
| Unconditional tracing flag | `/var/opt/target/logntrace/enable_unconditional_external_tracing` | Created only while the lifecycle count is under a limit; deleted by script | `/usr/bin/unconditional-external-tracing-disable.sh` (Alpine Electronics) |
| Core dumps | `/var/opt/public/sin/crashhandler/coredumps`, `…/gpu_hangs`, `/var/opt/kerneldump/`, `/var/opt/public/sin/gcd/` | `MaxOldCoreDumps=10` (+ `MaxCoreDumpSpaceMb`); "reduced coredumps" mode. Encrypted to `/etc/logntrace/certificates/coredump.cert` for export | `/etc/crashhandler.ini`, crashhandler/log-trace-manager strings |
| Restart stats | `/var/opt/public/sin/recmgr/recmgr_stats.db`, `restartInfo.xml` | persistent | recmgr strings |
| Health telemetry | `/var/opt/public/sin/health_telemetry/event_*.json`, `health_sessions.db` | `cleanOldEvents` (limit unknown) | healthtelemetryd strings |
| CDC event buffer | persisted event storage + KVS (path not in strings) | TTL-based (`removeExpiredEvents`) | `Failed to persist the event storage to:` |
| DUMM upload spool | `/var/opt/hdshare/tm/dumm` (`/mnt/share/tm/dumm/`) | empty on this unit | tmpfiles, Telematics strings |
| Screenshots | `/run/logntrace/screenshots/` → DLT file transfer / USB | volatile, limit `Reached screenshot limit` | log-trace-manager, `/etc/dlt-system.conf` |

Note: `/var/opt/public` and `/var/opt/personal` are ecryptfs-encrypted on disk (`.public`, `.personal` lower dirs), so the contents of crash/health/recmgr dirs are not visible from the raw image. Covered by the stored-data report.

**"Burn flag" / field mode:** log-trace-manager has `Mileage over 254km: %d`, `Burn flag was set to On, Status of httpd is changed: Stop`, `Cannot switch developer FSC mode: ECU is Field mode`. Once the car has more than 254 km on it, the trace/coredump HTTP export is stopped and developer tracing modes are locked. H.

---

## 6. Debug and remote-access surfaces

- **sshd** (`sshd.socket`, `ListenStream=22`, `PartOf=debug.target`) and **root serial autologin** (`mgu-serial-getty.service`: `agetty --autologin root -8 -L ttyS2 115200`) are only in `debug.target.wants`. `default.target → early.target`.
  - `nodestartupcontroller` starts `debug.target` on `BMWDebugModeActive`.
  - `mgusecdiagd`: `Activating the BMW Debug Mode since SecureBoot is deactivated!`, `Device id of provided debug token does not match.`, `SecureBoot is activated, dont turn on debug mode by default`.
  - `/var/opt/target/security-debugtoken/` is empty on this unit.
  - Gated by a signed device-bound token or SecureBoot off. H.
- **debug-shell.service** (root sh on tty9, `ConditionPathExists=/dev/tty9`) is in sysinit.target.wants only via the systemd debug generator (kernel cmdline). Not enabled in this image. M.
- **lighttpd-log-trace** (8081 core dumps, 8082 internal trace, `dir-listing.activate = "enable"`, **no auth**): the unit is not in any `.wants`. Firewall: `tcp dport 8081 drop` / `8082 drop` by default; opened by `firewall-http-coredump-open.sh`. Stopped after the burn flag. Reachable only from the in-car network (vlan73/socnet0). H.
- **DLT TCP 3490**: dropped by default (`tcp dport 3490 drop`); opened by `firewall-dlt-tracing-inbound-open.sh`.
- **HSFZ diagnostics TCP 6801** (`iifname vlan73 tcp dport 6801 accept`, `iifname socnet0 tcp dport 6801 accept`) and **RSU HTTP 8888** (`lighttpd-rsu.conf server.bind = "160.48.199.99"`): always open toward the vehicle network. A workshop tester on the OBD port reaches them via the BDC gateway. UDS can read DTC/environment data, the CDC job state, and trigger CDC campaigns (`SteuernCdcTriggerCampaignRequest`). H.
- **NFS**: `nfs-export-hdd.service` exports HDD/hdshare dirs (incl. `/var/opt/hdshare/cia`, `ent`, `hmi`) to `160.48.199.162` (the RSE rear-seat unit) on vlan144, only if `rse_configured`. M.
- **Firewall debug/plant/provisioning chains** (`inputdebug`, `inputplant`, `inputprovisioning`) are empty in release and filled by firewalldZ on a debug-mode change (`Failed to remove debug mode rules, IPv4, InputDebug`). H.

---

## 7. Open questions
1. Is `CDC_ENABLE` coded on a given car, i.e. does `/run/variant/cdc/active` exist at runtime? This needs a runtime check or a read of coding data (CodingShm).
2. What do the provisioned CDC campaigns and jobs actually collect? The schema is server-defined, and the provisioning file is in encrypted `/var/opt`.
3. Which component (OAP app?) sends the health-telemetry JSONs? Who provides `de.bmw.infrastructure.CrowdDataCollector` (another ECU, or an OAP app via `tm_oap_app`)?
4. Does the TCU keep a data connection (eSIM) without an active ConnectedDrive contract? Does provisioning still arrive and keep CDC/RSU log upload working? This can't be told from the MGU image.
5. Does the user-facing "Data privacy" menu map 1:1 onto these keys, and does any key cover CDC? No CDC key is visible in dataprivacyd.
6. Production backend hostnames: they only arrive via provisioning. The E2E/int URLs in NavController/cluster-controller are probably fallbacks. Confirm by checking the persisted provisioning (stored-data report).
7. `/usr/lib` (about 3000 libraries) was only scanned for rsu. More hostnames or SDKs may live in libraries such as `libtelematicsPlatform-joynrmodel`, the nav and HMI libs.
8. Exact uid ↔ binary mapping for `cns_12701`/`12703` (allowed internet egress); no unit uses them in this image.
