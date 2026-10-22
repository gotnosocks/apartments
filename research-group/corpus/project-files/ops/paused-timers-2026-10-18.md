# Paused timers, 2026-10-18

All project timers on thelio were paused on 2026-10-18 (stopped and disabled, nothing deleted). All are systemd user units for ben. Times are New York time.

To turn any of them back on: `systemctl --user enable --now <name>`

## Paused today

| # | Name | What it does | Schedule | Next run it would have had |
|---|------|--------------|----------|----------------------------|
| 1 | apartments-dashboard-build.timer | Rebuilds the research site's data from run records; skips when nothing is new | Every 10 min | Sun 10-18 12:20 |
| 2 | apartments-modal-cleanup.timer | Deletes the Modal fit storage after 24 h with no fit | Hourly | Sun 10-18 13:00 |
| 3 | apartments-pipeline-build.timer | Builds the fit-ready rows from the StreetEasy export (daily fallback for #8) | Daily 07:15 | Mon 10-19 07:15 |
| 4 | apartments-streeteasy-backup.timer | Backs up the StreetEasy archive to /data2 | Daily 09:00 | Mon 10-19 09:00 |
| 5 | apartments-city-fetch.timer | Adds new city lot and building records to the dated archive | Fri 04:05 | Fri 10-23 04:05 |
| 6 | apartments-streeteasy-topup.timer | Reads current StreetEasy ads for each region (spends OxyLabs credits) | Fri 05:35 | Fri 10-23 05:35 |
| 7 | apartments-dashboard-build.path | Runs the dashboard build whenever a fit writes results | When files change | n/a |
| 8 | apartments-pipeline-build.path | Runs the pipeline build whenever the StreetEasy export changes | When files change | n/a |

Nothing was running when paused. The top-up job (#6) still shows a failed state from a manual run on Sat 10-17 13:43 that was stopped; left as is.

Units 4 and 6 are links into the repo copy; disabling removed the links, so they were recreated without enabling. The enable commands above still work.

## Already off before today (unchanged)

| Name | Schedule |
|------|----------|
| apartments-ev-monitor.timer | Every 2 h at :37 |
| apartments-fgp-monitor.timer | Every 2 h at :17 |
| apartments-gv-monitor.timer | Every 2 h at :47 |
| apartments-nomad-monitor.timer | Every 2 h at :27 |
| apartments-stuytown-monitor.timer | Every 2 h at :47 |
| apartments-modal-test-cleanup.timer | Hourly |
| apartments-rate-balance.timer | Every 15 min at :05 |

Scheduled tasks on Ben's Claude account: 4 exist (an old hourly thread wake check and three one-off retry wakes), all already off.

## Checked, nothing scheduled

- ben's crontab: none. Root's crontab couldn't be read (sudo needs a password); /etc/cron.* holds only OS entries.
- Modal: no apps deployed and no scheduled functions in the repo.
- No leftover one-off systemd-run timers.

## Left running on purpose

- apartments-site.service (the website). Not scheduled.
- claude-rc.service (lets Claude reach thelio). Not scheduled.

Verified after pausing: no apartments timer or path unit has a next run.
