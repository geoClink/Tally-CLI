# tally

A terminal time tracker for freelancers. Track billable hours by client, set weekly goals, sync
sessions to your [Tally](https://tallytimetracker.com) account, and log time to Jira tickets
automatically.

## Install (Mac)

Needs Python 3.9+ (already on macOS). No other dependencies.

```bash
git clone https://github.com/geoClink/Tally-CLI.git ~/Tally-CLI && ln -sf ~/Tally-CLI/tally /opt/homebrew/bin/tally
```

No Homebrew, or an Intel Mac? Use `sudo ln -sf ~/Tally-CLI/tally /usr/local/bin/tally` for the second part.
Update later with `git -C ~/Tally-CLI pull`.

### New teammate checklist

1. Install (above).
2. `tally login` with your Tally email and password. Signed up with Apple or Google? Set a password first
   with "Forgot password?" on tallytimetracker.com.
3. Make **your own** Jira API token (see Jira below). Never share tokens: worklogs show under the token's owner.
4. `tally jira connect`, then `tally jira link <KEY> "<Client>"` with the same client name your team uses.
5. `tally tasks` to start; `tally stop` when done.

## Usage

```bash
tally start tripsetta-android   # start tracking
tally pause / tally resume
tally note "fixed the login"    # note for the running session
tally stop                      # stop and save (and sync, see below)
tally status                    # progress bar + breakdown
tally report                    # all-time totals
tally add lctway 2              # manually log 2 hours today
tally add lctway 2 2026-05-25   # log hours for a past date
tally goal 10                   # set weekly hour goal
```

## Sync to your Tally account

```bash
tally login                     # your Tally email + password
```

Every session you stop is sent to your account and shows up in the Tally iPhone, Mac, web and
Android apps. If you're offline it stays on this Mac until `tally sync`.

## Jira

Create a scoped API token at Atlassian → Account settings → Security → API tokens →
**Create API token with scopes**, app **Jira**, scopes `read:jira-work`, `write:jira-work` and
`read:jira-user`.

```bash
tally jira connect                    # site, email, token (stored in your macOS Keychain)
tally jira link ACME "Acme Corp"      # ACME-* tickets bill to Acme Corp
tally tasks                           # pick one of your open tickets and start it
tally start ACME-123                  # or start a ticket directly
tally stop                            # saves to Tally and logs a worklog on the ticket
```

Inside a git repo, a plain `tally start` uses the ticket in the branch name
(`feature/ACME-123-login-fix` → ACME-123).

By default only the ticket key goes to Tally, not its title. Turn titles on with
`tally jira titles on` if your client is fine with that.

## Troubleshooting

- **Which Jira site?** Open any ticket in your browser: in `https://acme.atlassian.net/browse/ABC-12`
  the site is `acme.atlassian.net` and the project key is `ABC`. home.atlassian.com lists all your sites.
- **`tally tasks` started nothing:** at "Start which?" type the ticket's number; Enter alone cancels.
- **Signed in to Tally with Google or Apple?** `tally login` needs a password for now. Set one with
  "Forgot password?" on tallytimetracker.com. Jira logging works without signing in.
- **Something didn't sync:** `tally status` shows how many sessions are waiting; `tally sync` retries.

## Accuracy

tally only knows what you tell it, so it double-checks against your actual work in git:

- **Idle check on stop.** If there were no file saves or commits for 20+ minutes while the timer ran
  (lunch, a meeting, forgot to stop), `tally stop` shows the gap and offers to remove it. The first
  stretch after starting gets twice the allowance, since reading the ticket and code comes first.
  `tally idle 30` changes the limit; `tally idle off` turns it off.
- **`tally review`** compares today's commits (in repos you've started timers in) with what you tracked
  and offers to add the work no session covers, ticket included. `tally review 2026-10-14` checks
  another day. Nothing is added without a yes.
- **Proof of work.** Each Jira worklog lists the commits made during that session.
  `tally jira proof off` leaves them out.

## Data

- Sessions and settings: `~/Library/Application Support/tally/` (readable only by your account)
- Tally sign-in and Jira token: macOS Keychain, service `tally-cli`

Older versions stored data in `/Users/Shared/tally/`; it's copied over on first run.

## Tests

```bash
python3 -m unittest -v test_tally.py
```
