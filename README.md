# BEJÚ reply notifier

Posts every real Instantly lead reply (including later replies in ongoing threads) to Slack
`#instantly-notifcations`. Runs on GitHub Actions every 5 minutes, so it works with every
computer off. No secrets in this repo: `INSTANTLY_API_KEY` and `SLACK_BOT_TOKEN` are
GitHub Actions secrets. A Mac backup (`~/beju-jobs/notify_run.sh`, launchd
`com.beju.replynotify`) runs the same script; both dedupe on the `ref:` marker in Slack.
