# SC Toolbox v3.0.1: Resolution Testing Report (5120x2160)

- **Prepared for:** the SC Toolbox author
- **Date:** 2026-10-15
- **Build:** v3.0.1 (Velopack installer, per-user install)
- **Compared against:** `ScPlaceholder/SC-Toolbox-Beta-V2` master @ `7895bab4`
- **File index:** [README.md](README.md)

Offline tests ran headless from image files: no screen capture, no windows, no writes
to user data (isolated copies of the tool were used). The live test (section 8) ran
the installed app against the running game. Line numbers refer to the v3.0.1 source.

## 1. System

| Item | Value |
|---|---|
| OS | Windows 11 Pro 64-bit, 10.0.26200 (build 26200) |
| CPU | AMD Ryzen 7 9800X3D (8 cores) |
| RAM | 64 GB |
| GPU | NVIDIA GeForce RTX 4090 (driver 32.0.16.1656). AMD Radeon iGPU and a "Virtual Desktop Monitor" adapter are also present |
| VC++ runtime | 2015-2022 x64, 14.51.36247 |
| Security | Smart App Control off; no Mark-of-the-Web on installed files |

| Display | Physical | Logical | Scale | Position |
|---|---|---|---|---|
| DISPLAY1 (primary), LG ULTRAGEAR+ | 5120x2160 @165 Hz | 3413x1440 | 150% | 0,0 |
| DISPLAY2, LG TV | 3840x2160 @60 Hz | 1280x720 | 300% | left of primary |
| DISPLAY5, CF15T | 1920x1080 @59 Hz | 1536x864 | 125% | below right |
| DISPLAY6, CF15T | 1920x1080 @59 Hz | 1536x864 | 125% | below left |

The game and all Mining Signals regions are on DISPLAY1. Region coordinates are in
physical pixels; x=3924 is beyond the 3413 logical width, so the tool handles DPI
correctly.

Star Citizen settings (screenshots 02/03):
- Vulkan, 5120x2160, **Fullscreen** (not Borderless)
- DLSS Balanced (57%) by default, turned off for later tests
- Sharpening 100, FOV 118

## 2. Executive summary

1. **Install is complete and matches upstream.**
   - Code is identical apart from CRLF line endings and the username scrub.
   - All 20 OCR models have identical weights.
   - All bundled assets are present.
2. **Packaging gap.** `psutil`, `comtypes`, `pycaw`, `pygame`, `rapidfuzz` and `orjson`
   are imported but never bundled. Installed manually here; the warnings cleared with no
   regressions.
3. **Both Mining Signals pipelines are plumbed end to end.**
   - Every engine that runs gets non-empty, correctly shaped input.
   - Outputs reach the UI.
   - No exceptions escape.
4. **Several stages are disconnected or ineffective.** Some never vote, some output a
   constant, some use the wrong model, and the gates have holes. The result is
   confident wrong values, including a blank frame reported as "Copper".
5. **Manual override is broken at non-670 px region heights** (section 7):
   - boxes are saved in raw-capture pixels but applied to the 670-px resized frame
   - the auto-detect path can pre-empt the override
6. **Live test at native 5120x2160** (section 8):
   - HUD: mass never read; resistance and instability wrong on every scan
   - Signal: true value 42,000; the tool confirmed 4700/4900 ("No match")
7. **The calibration dialog fails silently.** It rejects samples without telling the user why.

## 3. Install / dependency findings

### 3.1 Delivery
- Velopack installer with a bundled embeddable Python 3.14.0. The `.bat` files are
  dev-only.
- No guidance is given for SmartScreen / unsigned-binary blocks (FORKING.md: "Nothing is
  code-signed").

### 3.2 Imported but missing from `build/build_installer.bat` (pip line ~162) and `requirements.txt`

| Package | Used at | Effect when missing |
|---|---|---|
| psutil | `tools/SuitMk2/core/sound_classifier.py:298`, `voice_fx.py:271`, `tools/Assistant/assistant/ipc_bus.py:99,191` | Assumes StarCitizen.exe is always running and respawns the tap every retry. Ducking can't match the game session. IPC falls back to PowerShell CIM scans |
| comtypes, pycaw | `voice_fx.py:278-280, 437` | Ducking silently never triggers. `game_level()` (:373) is unguarded |
| pygame | SuitMk2 / Assistant `input_devices` | No joystick push-to-talk. pygame has no cp314 wheel; **pygame-ce** works |
| rapidfuzz | `assistant/set_route/destination_engine.py:26` | difflib fallback |
| orjson | `skills/DPS_Calculator/data/cache.py:14` | Slower cache loads |

`voice_fx.py` says "pycaw+comtypes+psutil (all already in the toolbox Python)"; that is
not true for the shipped build.

Installed here: psutil 7.2.2, comtypes 1.4.17, pycaw 20260927, rapidfuzz 3.14.6,
orjson 3.13.0, pygame-ce 2.5.8. Verified that imports, functional calls and the app's
code paths all work and logs are clean. These are lost on every Velopack update.

### 3.3 Other notes
- **Tesseract version.** The bundled Tesseract is v5.2.0.20220712, but the build
  references the 5.4.0 installer (the build copies a system install first if one exists).
- **Paddle model download.** The Paddle sidecar (py313: paddle 3.0.0, paddleocr 3.7.0)
  downloads PP-OCRv6 models to `%USERPROFILE%\.paddlex` on first use. This is
  undocumented.
- **Stray folder.** `debug_segmenter\` ships in the package but is unused.
- **Unit tests.** Upstream tests against the installed code: 402/409 pass. The 7
  failures are stale:
  - `test_validate`: mass 0 is now accepted
  - `test_hud_panel_tracker`: the colon presence check is not mocked

## 4. Component checks
- **ONNX models:** all 24 (`ocr\models` + `ocr\models_glyph`) load in onnxruntime
  1.30.0 (CPU) and produce output.
- **Tesseract:** reads synthetic text correctly.
- **Online sources reachable:** Google signal sheet, scmdb.net, UEX API, GitHub,
  HuggingFace.
- **Lexicon:** 173 known signature values plus 33 user-verified.

## 5. Pipeline data-flow traces (instrumented, headless)

Method:
- Every stage function, every `onnxruntime` `run()` and every Tesseract call was wrapped
  to log: called?, input type/shape/dtype/range, output, swallowed exceptions, and
  downstream consumer.
- Fast and legacy modes, plus blank and noise inputs and a replica of the `_do_scan` loop.
- This checks that information reaches each stage, not accuracy.
- Evidence: `evidence/hud_pipeline/`, `evidence/signal_pipeline/`.

### 5.1 Signal scanner (`ocr/sc_ocr/api.py` unless noted)

| Stage | Called | Input OK | Output | Passed on |
|---|---|---|---|---|
| UI anchor gate `signal_anchor.find_icon` (ui/app.py:4319) | yes | yes | bbox after 3 hits | yes |
| capture → max_channel | yes | yes | yes | yes |
| world model + `_find_pill_for_signal` (12926) | yes | yes | sometimes | yes |
| `signal_solve` pill fallback (13041) | **never** | – | – | dormant |
| `localize_icon` (geometry + RGB NCC) | yes | yes | yes | yes |
| `find_digit_crop_box` (legacy NCC) | on miss | yes | yes | yes |
| Icon voter: geometry + contour | yes | yes | yes | yes |
| Icon voter: RGB CNN + gray CNN tiers (icon_voter.py:397-570) | **never** | – | – | – |
| Scanning-timeout gate (13149) | yes | – | – | yes |
| Comma crop extension (13213) | yes | yes | yes | yes |
| RGB CRNN `model_signal_crnn_rgb` (13560) | yes | (1,3,48,W) f32 0-1 ✓ | yes | yes |
| Segmenters (proportional / column) | yes | yes | yes | yes |
| Gray CNN signal / signal_inv | yes | 28x28 f32 | yes | N-way vote |
| RGB CNN `signal_rgb_cnn_v2` / `rgb_inv` | yes | (N,3,28,28) f32 | **constant class** | counted in vote |
| Gray CRNN `model_crnn` / `_v2` | yes | PIL L | yes (run twice) | yes |
| `_signal_cnn_per_digit` (15822) | yes | **wrong convention** | None 8/8 | ignored |
| Fast Tesseract `_tesseract_char_boxes` | yes | yes | yes | yes |
| `_signal_cnn_at_tess_boxes` (~15750) | yes | **wrong convention** | None 2/2 | ignored |
| Legacy Tesseract engines A/B | yes | yes | yes | yes |
| Legacy Paddle | not tested | | | |
| `SignalMatcher.match_all` | yes | int | yes | yes |

### 5.2 Mining HUD (`onnx_hud_reader.py` / `api.py`)

| Stage | Called | Input OK | Output | Passed on |
|---|---|---|---|---|
| Capture `hud_region` (api.py:16832). Pipeline resizes to H=670 (16860-16866); the gate uses the raw size | yes | RGB | yes | yes |
| SCAN RESULTS gate `find_scan_results_anchor` (ui/app.py:4349). **Also seeds the shared tracker, see 6.8** | yes | yes | yes | yes |
| Calibration lookup (onnx_hud_reader.py:2955) | yes | yes | None if no calibration | fallback |
| `find_hud_panel` (tuned to a cyan/green HUD, `hud_color_calibration.json`) | yes | yes | **always None** | lost hint |
| `find_mineral_name_row` | yes | yes | yes | yes |
| `label_match.find_label_positions`. UnboundLocalError is swallowed at label_match.py:1077, so the cache never caches | yes | yes | yes | yes |
| HudPanelTracker / Stabilizer / panel_solve | yes | **wrong scale** | yes | yes |
| `_find_value_crop` (724) | yes | yes | RGB crops | yes |
| Composition SCU + composition rows | **no code exists** | | | |
| HUD RGB CRNN, `model_hud_cnn`, `model_cnn_inv`, `model_hud_rgb_cnn`, mineral CRNNs | yes | shapes ✓ | yes | yes |
| `model_signal_rgb_cnn_v2` used in HUD consensus (7661) | yes | ✓ | consensus None every call | ignored |
| `model_cnn.onnx` | loaded, **never run** | | | required (5191) |
| Tesseract (fast; ~25-29 calls per scan), template fallback, legacy Tesseract | yes | yes | yes | yes |
| Paddle | never | | | |
| Validators / consensus / lock → UI (5 keys, ui/app.py:4481-4485) | yes | yes | yes | consumed |

## 6. Issues found (file:line), most impactful first

### Signal scanner

**6.1 Blank frame reported as "Copper".** In the live-loop replica, a blank tick read
21200 → "Copper 5R". The chain:
1. The anchor cache keeps the gate open (`_smooth_anchor_with_cache`, ui/app.py:4319-4334).
2. The anchor misses, so the heuristic-mask path (13278-13299) sets crop mode to "none".
3. The ink check and the 0.92 threshold apply only in "icon_only" mode (14626-14685).
4. The RGB CRNN reads an all-zero tensor as "21,200" (0.85), and the lexicon gate
   accepts at 0.40 (14672).

**6.2 Stale crop mode.** `last_crop_mode()` resets only in `find_digit_crop_box`
(signal_anchor.py:1369). On other ticks, the gate at 14623 reads the previous tick's mode.

**6.3 The cross-check CNNs never vote.**
- `_signal_cnn_per_digit` (~15838-15890) and `_signal_cnn_at_tess_boxes` (~15750) use the
  old convention: no polarity routing, and they call the HUD model `model_cnn_inv.onnx`
  instead of the signal inverse model.
- They return None 10/10. As a result, gray-CRNN "cnn=no-check" reads are accepted
  without a lexicon check (15375-15424); values 1500 and 1420 were accepted.
- Tesseract values are never cross-checked.

**6.4 Lexicon gate threshold.** The RGB-CRNN lexicon gate accepts at mean ≥ 0.40, so
noise snaps to wrong-but-known values (21200, 19200).

**6.5 RGB per-glyph CNNs output one class for every glyph** (14294-14366, 6032-6290), yet
count as 2 of 4 votes. Likely cause: white aspect-repad bars (13875) drive the
median-based polarity choice (5548-5624).

**6.6 Icon voter.**
- The RGB tier (icon_voter.py:419-460) gives p(@) ≈ 1.0 for icons, digits and empty
  background. It takes max(normal, inverse) on the raw crop; `model_signal_rgb_inv_cnn_v3`
  scored 85/100 plain digits above 0.7.
- `signal_anchor.py` ~273 treats gray_cnn "unavailable" (actually "not consulted") as
  missing and rejects: 23 REJECTED-WEAK in one offline session, 105 in the live test.
- The gray CNN reads real icons as '2'.
- The icon training class is 600 augmented copies of one image (`bad crop.png`).

**6.7 Crop geometry.**
- The comma extension (13213-13257) pulls icon pixels into the digit crop. The gray CRNN
  read "111520" / "142000", and the 6-digit read is discarded instead of stripped.
- The `localize_icon` crop is `max(80, 6.5*icon_w)` wide, running past the pill.
- The world-model crop can be only 12 px tall.
- The pill finder has fixed limits (area 600, close 30), false-fires on noise and
  expects cyan/green.
- The gray CRNN runs twice per input (15036, 15219).
- `scan_region` swallows recognizer exceptions at DEBUG level (screen_reader.py:836).
- Cold start measures "since last icon" from 0.0.

### Mining HUD

**6.8 Gate/pipeline scale mismatch.** The SCAN RESULTS tracker is seeded by the UI gate in
raw pixels (ui/app.py:4346-4349) and reused on the 670-high frame
(onnx_hud_reader.py:3290-3297; api.py:16860). scan_results_match.py ~323-340 then
rejects the correctly sized title as a "lookalike jump". This affects every uncalibrated
region that is not ~670 px tall.

**6.9 Label template font.** `ocr/sc_templates/labels.npz` and `scan_results.npz` use a
narrower font than the HUD. MASS matches land in the value column, then the "MASS top-1
DISAGREES" swap picks a wrong row and the stabilizer locks it.

**6.10 Value-column X is mis-placed,** so value crops include the label text.

**6.11 Shifted rows locked as confident wrong values.** Rows shifted by one get locked
"unanimous 3/3", e.g. instability 54.3494 taken from the "64.34%" composition row.

**6.12 Wiring.**
- The signal model `model_signal_rgb_cnn_v2` is used in HUD consensus, although
  `model_hud_rgb_cnn` exists.
- `model_cnn.onnx` is a hard dependency that never runs during scans.
- `find_hud_panel` returns None on an orange-label HUD.
- Legacy mode returns all None if `tesseract_status()` hasn't run.
- **The fast-path Tesseract char boxes use a hard-coded
  `C:\Program Files\Tesseract-OCR\tesseract.exe`**
  (scripts/extract_labeled_glyphs.py:39), not the bundled exe. This path is dead on PCs
  without a system Tesseract.

**6.13 Mineral name is not repeatable.** The mineral-name slow path has a 1500 ms budget
(api.py:16481).

**6.14 Composition SCU and the composition rows are not implemented.**

### Calibration / UX

**6.15 Silent sample rejection.** The calibration dialog rejects samples ("ratio outside
(2.0, 7.5)") without telling the user. It never completes.
See `logs/mining_signals_video_calibration_attempt.log`.

**6.16 Pending crops written into the install folder.** Every HUD scan writes value crops
to `<install>\tools\Mining_Signals\training_data_crnn\pending` (api.py:18028), so bad
captures can enter self-training.

**6.17 Scans overrun the timer.** A scan takes 3-5 s live (1.7 s offline) against a 1.5-3 s
timer, giving "previous scan still in flight - skipping".

### Cosmetic

**6.18 Stylesheet strings.** `ui/calibration_dialog.py:612-615, 1019-1020, 1024-1027,
1032-1033, 1351-1353` concatenate an f-string with a plain string ending in "}}". Qt gets
a literal "}}", producing hundreds of "Could not parse stylesheet" warnings per session.

**6.19 Misleading log line.** `ui/app.py:478` logs the legacy path as "loaded from" when
the AppData config is missing.

**6.20 Log levels.** `signal_anchor.py:177/661/895` log routine diagnostics at WARNING.

**6.21 Launcher IPC disabled.** The launcher was started with cmd file "nul", so
`_start_cmd_watcher` exits and no IPC launches are possible.

## 7. Manual override is broken (confirmed in code, reproduced offline)

Evidence: `evidence/manual_override/`. The input is screenshot 06 cropped to the user's
region (3590,716,436,322).

**7.1 Coordinate-space mismatch.**
- **Saved:** `manual_override_dialog.py:81, 141-147, 183-192` stores boxes in raw-capture
  pixels (436x322). The source image is the un-resized `screen_reader.capture_region`
  (calibration_dialog.py:3230-3236, 2098, 2220).
- **Applied:** `api.py:16860-16865` resizes the capture to REF_H=670 (907x670), then
  `_build_manual_override_label_rows` (onnx_hud_reader.py:2962-2999) uses the raw x/y/h
  unscaled. `image_size` [907,670] in calibration.json is never consulted.
- Docstrings say "no transformation needed" (manual_override_dialog.py:13-16;
  calibration.py:445-446, 554-556).
- **Effect:** the boxes land ~2.08x too close to the top-left. The resistance crop was the
  text "ITE (RAW)", giving resistance 70 live and 79 offline.

**7.2 The override does not bypass auto-detect.**
- PRE-ANCHOR/EARLY-DIRECT (onnx_hud_reader.py:3269-4108) can return at :4108, before the
  override check at :4117.
- The pose-hold wrapper (:3110-3117) returns held rows before either.

**7.3 Box width is ignored.** Only the y-band and left x of each box are used.
`_find_value_crop(x_min=x+6)` (:776-876) reads to the rightmost ink. Scaled bands taller
than 50 px trip the CRNN "value_crop too tall" gate.

**Offline results (screenshot 06, truth: Taranite 14565 / 64 / 125.89):**

| Run | Mineral | Mass | Resistance | Instability |
|---|---|---|---|---|
| Unmodified, user boxes | – | None | 0.0 | None |
| Override forced first, user boxes | – | None | 79.0 | None |
| Override forced first, boxes ×2.08 | Taranite | 34565 (first digit 1 read as 3, 0.54) | **64** | **125.89** |
| Unmodified, boxes ×2.08 | – | None | 0.0 | None |

Corrected boxes for this region (907x670 space):

| Field | x | y | w | h |
|---|---|---|---|---|
| mineral | 29 | 146 | 453 | 77 |
| mass | 458 | 243 | 169 | 65 |
| resistance | 445 | 335 | 137 | 71 |
| instability | 441 | 420 | 198 | 73 |

**Fix:**
1. Scale the boxes by (907/436, 670/322) at save or load time.
2. Run the override before EARLY-DIRECT and pose-hold.
3. Honour the box width, and keep bands ≤ 50 px.

## 8. Live test, 2026-10-15 12:58-13:24 (native 5120x2160, upscaling off)

Logs: `logs/`. Setup:
- Regions: `ocr_region` 127x55 @ 2493,754; `hud_region` 436x322 @ 3590,716
- Calibration: manual override (`evidence/manual_override/calibration_user_saved.json`)
- Engine mode: fast

**HUD:** ~117 scans, 0 errors, 3-5 s per scan. Mass was never read.

| Time | Truth (screenshot) | Read |
|---|---|---|
| 13:17:22 | 14565 / 64% / 125.89 (09) | None / 12.0 / 7.78 |
| 13:17:38 | 768 / 55% / 6.40 (10) | None / 77.0 / 5.5 |

**Signal (truth 42,000; screenshots 04-08, 12):**
- **Run 1 (13:15-13:18):** `find_icon` accepted 0 candidates on 46/46 ticks (105
  REJECTED-WEAK). `sig_present` was never true, so the digits were never read.
- **Run 2 (13:20-13:21):** the gate passed via `world_model_region2` (sig_score 0.80).
  - Candidate reads: 42001 (segmenter); 42006 (CRNN secondary, rejected as "not in
    known values"); 142000 (icon edge read as a leading 1); 47000 (N-way); RGB CRNN
    '2,520'; RGB-INV '0000'; SHADOW RGB '@707'.
  - The CRNN count oracle said 4 digits, forcing 4-box segmentation.
  - Confirmed values: **4700 / 4900 → "No match"**, with the flap logged as
    "oscillate(14000<->4000)".
  - Matches items 6.3-6.7.

## 9. Test conditions and caveats
- **The game ran in Fullscreen.** README asks for Borderless Windowed. Captures still
  worked (non-empty HUD crops).
- **Earlier shots used DLSS Balanced and Sharpening 100;** later shots and the live test
  were native.
- **An earlier calibration attempt used a YouTube video** (11:57-12:01). Its failure is
  expected; it is included only for 6.15. Video-derived accuracy figures are excluded from
  conclusions.
- **Faults are independent of image quality.** The faults in sections 6-7 were reproduced
  on native screenshots, clean crops and data-flow traces.

## 10. Suggested priorities
1. Manual override: scale the boxes to reader space, and check the override before
   EARLY-DIRECT and pose-hold (7.1, 7.2).
2. Bundle psutil / comtypes / pycaw (+ pygame-ce, rapidfuzz, orjson) in the build (3.2).
3. Signal empty-frame guard: apply the ink check in every crop mode, reset crop mode
   every tick, and tighten the 0.40 lexicon gate (6.1, 6.2, 6.4).
4. Fix the cross-check CNN conventions; require a lexicon match for "no-check" reads (6.3).
5. Icon voter: polarity correction and padding; retrain the icon class (6.5, 6.6).
6. Strip a leading icon-edge digit instead of discarding the read (6.7).
7. HUD auto-detect: one coordinate scale for gate and pipeline; current-font label
   templates; value-column X (6.8-6.10).
8. Use the bundled Tesseract path everywhere (6.12).
9. Tell the user why calibration samples are rejected (6.15).
10. Stylesheet "}}" fix and log-level clean-up (6.18-6.20).
