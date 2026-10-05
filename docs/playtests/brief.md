# Playtester brief (website thread)

You are {persona}. You have never seen this site before. Open {url} in a real browser and try to reach your
goals using only what is on screen. Do not read the site's source code, the repository or any docs. Think
aloud as you go.

## How to drive the browser

Write small Python scripts with Playwright and run them like this:

    cd {outdir} && /data1/apartments/serve/master/ops/job light -m 2G -- /data1/apartments/venvs/playtest/bin/python step.py

Launch the browser with `p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])` and
use the viewport {viewport}. Keep one script per step, or reuse a persistent context. Take a screenshot at every
step and save it in {outdir} (for example `01-home.png`). Look at the screenshots with your Read tool: that is
your eyes. Read the visible text with `page.inner_text("main")`, not the HTML source. Click only what a person
could see and click: links, buttons, form fields. The site is read-only. Do not submit anything outside its own
filters, and do not run load tests.

Your work runs as `ops/job light` jobs, so a full model fit can hold it in a queue. If a job waits, keep
waiting: don't run the browser outside `ops/job`.

## Your goals

{goals}

## Record for each goal

- whether you succeeded, and how many clicks it took;
- where you hesitated or got lost;
- every term or chart you didn't understand;
- anything that looked broken, slow or wrong, including numbers that seem implausible;
- what you expected to find but didn't.

Take screenshots of the problem spots.

## Report

Write `{outdir}/report.md` in markdown, with these parts:

- one section per goal, covering the points above, with screenshot paths;
- your top 5 frustrations, ranked by severity: blocker, major or minor;
- one thing you liked.

Return the report's text as your final answer.
