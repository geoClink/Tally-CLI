# tally

A lightweight CLI time tracker for freelancers. Track billable hours by client, set weekly goals, and get warned before you hit your limit — all from terminal.

## Install

```bash
sudo nano /usr/local/bin/tally
# paste the tally script, save with Ctrl+O, exit with Ctrl+X
sudo chmod +x /usr/local/bin/tally
```

## Usage

```bash
tally start tripsetta-android   # start tracking
tally pause                     # pause session
tally resume                    # resume session
tally stop                      # stop and save
tally status                    # progress bar + breakdown
tally report                    # all-time totals
tally add lctway 2              # manually log 2 hours today
tally add lctway 2 2026-05-25   # log hours for a past date
tally goal 10                   # set weekly hour goal
```

## Data

All data is stored locally at `/Users/Shared/tally/` as JSON. Nothing leaves your machine.
