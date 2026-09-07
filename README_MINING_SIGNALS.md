# Mining Signals — direct launch

Branch: `mining-signals-direct` on `swill008/SC-Toolbox`.

Full Mining Signals UI is unchanged (chart, scanner, ledger, refinery).
Other toolbox tools are still in the repo and are not launched by this file.

## Run

1. In GitHub Desktop, switch this clone to branch **mining-signals-direct** and pull.
2. If Python deps were never installed, run `INSTALL_AND_LAUNCH.bat` once.
3. Double-click `LAUNCH_MINING_SIGNALS.bat`.

Or from the repo root:

```bat
python tools\Mining_Signals\mining_signals_app.py
```

That script already bootstraps `shared/` so it does not need the 11-tool launcher.

## Later

Strip unused tools only after this path works on your machine.
