---
name: Training pipeline is manual hand-labelling, not YouTube harvest
description: The OCR models in this project were trained on manually-captured, hand-labelled glyphs via dual_capture + the label/review/prune workflow. Do not describe YouTube VOD harvesting as the actual training pipeline.
type: project
---

The dataset that trained the digit CNN, inverted-polarity CNN, CRNN, and Furore-tuned variants was built by **manual capture and hand-labelling**, NOT by the YouTube VOD harvester. The pipeline is:

1. `scripts/dual_capture.py` — overlays placed over SCAN RESULTS / signature panels while playing, SPACE/B captures to `training_data_panels/`.
2. `scripts/label_pending.py` / `scripts/label_crops_gui.py` — GUI labellers where the user types the values they can see.
3. `scripts/extract_labeled_glyphs.py` — splits each labelled value into per-character PNGs landing in `training_data_pending_review/<digit>/`.
4. `scripts/stage_for_review.py` / `scripts/review_glyphs.py` / `scripts/promote_reviewed.py` — review GUI accepts/rejects each glyph; accepted ones promote to `training_data_clean/<digit>/`.
5. `scripts/quarantine_contaminated_glyphs.py` / `scripts/blacklist_manager.py` — bad glyphs get pulled into `training_data_blacklist/` (also repurposed as anchor templates).
6. `scripts/filter_training_data.py` — cleans / dedupes datasets.

**Why:** The user explicitly corrected an earlier writeup that named YouTube harvesting as the training source. The `scripts/harvest_from_youtube.py` script and `harvest_plan_cycle*.tsv` files exist in the tree but were not the dataset the shipped models were trained on.

**How to apply:** When describing the project's training pipeline (writeups, descriptions, summaries), name the manual capture-label-prune workflow. Treat the YouTube harvester as an exploratory tool that wasn't adopted, not as the canonical pipeline.
