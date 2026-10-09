"""Post every real Instantly lead reply to Slack #instantly-notifcations.

Instantly's own alerts fire only when a lead's status changes, so a 2nd/3rd reply in an
ongoing thread never pinged anyone. This reads recent received emails and posts each one
not yet in the channel, labelled "first reply" or "reply #N in ongoing thread".

Stateless: every post ends with a `ref:<instantly email id>` marker, and each run reads the
channel's recent history to skip ids already posted. So it can run anywhere (GitHub Actions,
or a Mac as backup) without a state file, and a late or doubled run never reposts.

Env: INSTANTLY_API_KEY, SLACK_BOT_TOKEN (bot needs chat:write + channels:history).
  python3 notify.py            # post what's missing
  python3 notify.py --dry-run  # print what would be posted, post nothing
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

CHANNEL = "C0C7TU7CJNN"  # #instantly-notifcations
# Plain channel posts don't push to phones under Slack's default settings; an @mention does.
MENTION = os.environ.get("SLACK_MENTION", "<@U0C528KBKKL>")  # Benas
# Replies before the notifier went live were handled by hand; never backfill them.
START_AFTER = "2026-10-08T17:48:06"
LOOKBACK = timedelta(hours=48)
TZ = ZoneInfo("Europe/Vilnius")
CAMPAIGNS = {
    "e53a84be-5c9a-4fe8-8f52-e244876c0e5c": "Podcasters",
    "60f5dbf8-1f07-4bbc-992b-36eb707c4fd4": "Online Coaches",
}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
AUTO_SUBJECT = re.compile(
    r"(automatic reply|auto.?reply|out of (the )?office|\booo\b|delayed response|"
    r"thank(s| you) for (reaching out|your (email|message)|getting in touch)|"
    r"received your (email|message)|abwesenheit|vielen dank)", re.I)
# "Thank you for reaching out" opens real replies too (Nivedita 10-08), so it is not a body signal.
AUTO_BODY = re.compile(
    r"(i('m| am) (currently )?(out of (the )?office|on (vacation|holiday|leave|maternity leave))|"
    r"your (message|email) has been received|we('ll| will) get back to you as soon as|"
    r"(will )?receive a response within|(will )?respond within \d+ (hours|business days)|"
    r"this is an automated|vielen dank f(ü|u)r deine nachricht)", re.I)
REF = re.compile(r"ref:([0-9a-f-]{8,})")


def http(url, token, data=None, method="GET"):
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "User-Agent": UA,
        "Content-Type": "application/json; charset=utf-8", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read() or b"{}")


def received(key):
    q = urllib.parse.urlencode({"limit": 100, "email_type": "received"})
    return http(f"https://api.instantly.ai/api/v2/emails?{q}", key).get("items", [])


def posted_refs(tok):
    refs, cursor = set(), None
    for _ in range(3):  # up to 600 recent messages
        q = {"channel": CHANNEL, "limit": 200}
        if cursor:
            q["cursor"] = cursor
        d = http("https://slack.com/api/conversations.history?" + urllib.parse.urlencode(q), tok)
        if not d.get("ok"):
            raise RuntimeError(f"slack history: {d.get('error')}")
        for m in d.get("messages", []):
            refs.update(REF.findall(m.get("text", "")))
        cursor = (d.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break
    return refs


def post(tok, text):
    d = http("https://slack.com/api/chat.postMessage", tok, method="POST",
             data=json.dumps({"channel": CHANNEL, "text": text, "unfurl_links": False}).encode())
    if not d.get("ok"):
        raise RuntimeError(f"slack post: {d.get('error')}")


def body_text(e):
    b = e.get("body") or {}
    t = b.get("text") or re.sub(r"<[^>]+>", " ", b.get("html") or "")
    t = re.split(r"\n\s*On .{5,80}wrote:|\n>|\nFrom: ", t)[0]
    return re.sub(r"\s+", " ", t).strip()


def is_auto(e, text):
    if e.get("i_status") == 1:  # Instantly rated it interested: always post
        return False
    return bool(AUTO_SUBJECT.search(e.get("subject") or "") or AUTO_BODY.search(text[:400]))


def main():
    dry = "--dry-run" in sys.argv
    key, tok = os.environ["INSTANTLY_API_KEY"], os.environ["SLACK_BOT_TOKEN"]
    floor = max(START_AFTER, (datetime.now(timezone.utc) - LOOKBACK).strftime("%Y-%m-%dT%H:%M:%S"))
    items = received(key)
    done = posted_refs(tok)
    todo = sorted((e for e in items if (e.get("timestamp_email") or "") > floor and e["id"] not in done),
                  key=lambda e: e["timestamp_email"])
    posted = skipped = 0
    for e in todo:
        text = body_text(e)
        if is_auto(e, text):
            skipped += 1
            continue
        n = sum(1 for x in items if x.get("thread_id") == e.get("thread_id")
                and (x.get("timestamp_email") or "") <= e["timestamp_email"])
        label = "first reply" if n == 1 else f"reply #{n} in ongoing thread"
        when = datetime.fromisoformat(e["timestamp_email"].replace("Z", "+00:00")).astimezone(TZ)
        msg = (f"{MENTION} :incoming_envelope: *{e.get('from_address_email')}* → {e.get('eaccount')} · "
               f"{CAMPAIGNS.get(e.get('campaign_id'), 'other')} · _{label}_ · {when:%H:%M}\n"
               f"*{e.get('subject') or '(no subject)'}*\n> {text[:300]}{'…' if len(text) > 300 else ''}\n"
               f"Reply in Unibox (inbox {e.get('eaccount')}) · ref:{e['id']}")
        if dry:
            print("WOULD POST:\n" + msg + "\n")
        else:
            post(tok, msg)
        posted += 1
    print(f"{datetime.now(TZ):%F %T} checked {len(items)}, new {len(todo)}, posted {posted}, skipped auto {skipped}")


if __name__ == "__main__":
    main()
