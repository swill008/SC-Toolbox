# Resolution testing results: SC Toolbox v3.0.1 (5120x2160 / 5K2K)

Test record for the SC Toolbox author. Everything from the 2026-10-15 test session is in
this folder: screenshots, logs, the full findings report and the test evidence.

- **Full findings report:** [REPORT.md](REPORT.md)
- **Tested build:** SC Toolbox v3.0.1 (Velopack installer, per-user install). Source
  compared against `ScPlaceholder/SC-Toolbox-Beta-V2` master @ `7895bab4`.
- **Display:** LG ULTRAGEAR+ 5120x2160 (21:9), primary monitor, Windows scaling 150%,
  in a 4-monitor mixed-DPI desktop. Star Citizen at 5120x2160 in Fullscreen mode.
- **Ship:** Argo MOLE (Arbor MH2 laser).

Usernames and paths in the text files are replaced with `<USER>`. Screenshots are
unedited and show in-game player handles.

## Folder layout

```
testing/resolution-3.0.1/
  README.md                  this index
  REPORT.md                  full findings report (system, install, pipelines, bugs, live test)
  screenshots_native/        in-game screenshots (Print Screen), full 5120x2160
  screenshots_downscaled/    2000x843 copies shared earlier (values approximate)
  logs/                      Mining Signals logs from the live test and the failed calibration
  evidence/
    manual_override/         proof of the manual-override coordinate bug (overlays, crops, runs)
    hud_pipeline/            HUD data-flow trace (per-stage JSON) and harness scripts
    signal_pipeline/         signal-scanner data-flow trace (per-run JSON/logs) and harness scripts
```

## screenshots_native/ (5120x2160, straight from `StarCitizen\LIVE\ScreenShots`)

Times are local time on 2026-10-15. "Upscaling off" means the game rendered natively (no
DLSS), as confirmed by the tester. Native rendering was confirmed for every shot from 13:03
on. Earlier shots were probably taken with DLSS Balanced (57%), per files 02/03.

| File | Time | What it shows | Correct values |
|---|---|---|---|
| `01_hud_taranite_14565.jpg` | 12:39:05 | Mining HUD, SCAN RESULTS panel, fracture mode. Probably DLSS Balanced. | TARANITE (RAW) · Mass 14565 · Resistance 64% · Instability 125.89 · IMPOSSIBLE · Composition 10.68 SCU · 8.23% Taranite 525 / 84.63% Taranite 310 / 7.12% Inert 0 |
| `02_settings_graphics_top.jpg` | 12:53:34 | Options > Graphics (top) | Vulkan · 5120x2160 · **Fullscreen** · VSync No · Upscaling Balanced (57%), DLSS/DLAA, Transformer · Custom (High) |
| `03_settings_graphics_bottom.jpg` | 12:54:21 | Options > Graphics (bottom) | Post FX Very High · FOV 118 · Gamma 61 · Brightness 50 · Contrast 50 · **Sharpening 100** · Motion blur off |
| `04_signal_42000_a.jpg` | 13:00:41 | Scan mode, radar signature readout | RS **42,000**. Badge at about x 2510-2615, y 768-800; digits ~13 px tall |
| `05_signal_42000_b.jpg` | 13:00:47 | Same, 6 s later | RS 42,000 |
| `06_hud_taranite_14565_noupscale.jpg` | 13:03:49 | Same rock as 01, **upscaling off**; left MFD on INFO tab | Same values as 01. Panel within a few px of 01 |
| `07_signal_42000_c_ping_noupscale.jpg` | 13:06:08 | Scan ping in progress (cyan terrain outline), **upscaling off** | RS 42,000 |
| `08_signal_42000_d_noupscale.jpg` | 13:06:10 | After the ping, **upscaling off** | RS 42,000 |
| `09_livetest_hud_taranite_14565.jpg` | 13:17:22 | **Live test**: HUD while Mining Signals was scanning | Taranite · 14565 · 64% · 125.89. Tool read: mass None / resistance 12.0 / instability 7.78 |
| `10_livetest_hud_taranite_768.jpg` | 13:17:38 | **Live test**: new rock, HUD | Taranite · Mass 768 · Resistance 55% · Instability 6.40 · EASY · Composition 737.67m SCU · 10.66% Taranite 718 / 57.75% Taranite 310 / 31.57% Inert 0. Tool read: None / 77.0 / 5.5 |
| `11_livetest_scan_no_signature.jpg` | 13:20:27 | **Live test**: scan mode, no RS readout on screen (signal WEAK). A useful negative case | No signature badge present |
| `12_livetest_signal_42000.jpg` | 13:20:31 | **Live test**: scan mode, RS readout | RS 42,000. Tool confirmed 4700 / 4900 ("No match") |

## screenshots_downscaled/ (2000x843, shared through chat, so lower quality)

| File | What it shows |
|---|---|
| `hud_taranite_2000x843.webp` | Earlier HUD capture (different rock state, narrower FOV). Values read from the downscaled image are approximate: Taranite, mass ~14555, resistance ~51%, instability ~193.68 |
| `signal_scanner_2000x843.webp` | Earlier scan-mode capture; RS readout looked like 11,055 (unconfirmed) |

## logs/

| File | What it is |
|---|---|
| `mining_signals_live_session_full.log` | Every line of `mining_signals.crash.log` (+ rotated `.1`) from 12:58:14 to 13:24:46: the live test with the manual-override calibration. HUD region 436x322 @ 3590,716; scan region 127x55 @ 2493,754 |
| `hud_results.log` | Excerpt: one `scan_hud_onnx` result line per HUD scan, plus manual-override and calibration lines |
| `signal_pipeline.log` | Excerpt: gate decisions, icon voter (`find_icon`, REJECTED/REJECTED-WEAK), `sc_ocr.signal` stages, segmenter, `_on_scan_result` |
| `mining_signals_video_calibration_attempt.log` | 11:55-12:03: an earlier calibration attempt made against a YouTube video, not the game. All samples rejected ("ratio outside (2.0, 7.5)") and nothing saved. Included for the silent-failure UX issue only |

## evidence/manual_override/ (main bug, see REPORT.md section 7)

The input is `06_hud_taranite_14565_noupscale.jpg` cropped to the user's HUD region
(3590,716,436,322). This is exactly what the app captures.

| File | What it shows |
|---|---|
| `calibration_user_saved.json` | The user's saved `calibration.json` (manual override mode; boxes in raw 436x322 px; `image_size` [907,670]) |
| `crop_raw_436x322.png` | Raw capture of the HUD region |
| `crop_resized_907x670.png` | Same capture after `scan_hud_onnx` resizes it to REF_H=670 |
| `overlay_boxes_on_raw_436x322.png` | Saved boxes on the raw capture. They land exactly on TARANITE (RAW), 14565, 64%, 125.89 |
| `overlay_boxes_on_resized_907x670.png` | **The same boxes as the reader applies them** on the 907x670 frame. They land on the panel title area |
| `overlay_boxes_scaled_on_resized_907x670.png` | Boxes scaled ×(907/436, 670/322). They land on the values again |
| `out_original/` | Unmodified pipeline with the user's boxes. EARLY-DIRECT pre-empts the override (mass None, res 0, inst None) |
| `out_original_forced/` | Override branch forced first with the user's boxes. Reproduces the live symptom; `valuecrop_02_*` shows the resistance crop is the text "ITE (RAW)" |
| `out_corrected_forced/` | Override forced first with scaled boxes. Taranite, 64, 125.89 correct. Mass crop `valuecrop_01_*` is a clean "14565", but it is read as 34565 |
| `out_corrected_unforced/` | Scaled boxes but unmodified pipeline. EARLY-DIRECT still pre-empts the override |
| `out_tight_forced/` | Variant with ≤48 px bands |
| `*/label_rows_as_applied_907x670.png` | Rows and value crops the engines actually received |
| `*/record.json`, `*/run.log` | Exact rows and crop rectangles, plus a full debug log per run |
| `harness.py`, `draw.py` | Offline harness (fake LOCALAPPDATA, stubbed capture, QT offscreen) and overlay script |

## evidence/hud_pipeline/ and evidence/signal_pipeline/ (data-flow traces, REPORT.md section 5)

These traces check that each stage is called, receives correctly shaped input and
passes its output on. They are not accuracy tests. Inputs were mostly downscaled
YouTube frames plus blank and noise images. The video images themselves are not
included; the trace output is.

| File | What it is |
|---|---|
| `hud_pipeline/trace/*.json` | Per-function call counts, input/output summaries, ONNX inputs vs expected, data-flow edges and swallowed exceptions. Cases: tight/loose panel crop, blank; fast and legacy modes |
| `hud_pipeline/trace_case.py`, `run_case.py` | Tracer and harness |
| `signal_pipeline/trace_out/*.json, *.log` | The same for the signal scanner. `blank_black_140x60__*` and `noise_140x60__*` reproduce the empty-frame path; `console.txt` is the run console |
| `signal_pipeline/x2.7_tick6.log`, `x2.7_tick7.log` | Live-loop replica ticks where a **blank frame** was reported as 21200 "Copper" (REPORT.md 6.1) |
| `signal_pipeline/trace_pipeline.py`, `live_seq.py` | Tracer and `_do_scan` loop replica |
