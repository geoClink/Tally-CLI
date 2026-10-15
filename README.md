# tally

A terminal time tracker for freelancers. Track billable hours by client, set weekly goals, sync
sessions to your [Tally](https://tallytimetracker.com) account, and log time to Jira tickets
automatically.

## Install

Needs Python 3.9+ (already on macOS). No other dependencies.

```bash
git clone https://github.com/geoClink/Tally-CLI.git ~/Documents/GithubProjects/Tally-CLI
ln -sf ~/Documents/GithubProjects/Tally-CLI/tally /opt/homebrew/bin/tally   # or /usr/local/bin on Intel Macs
```

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

## Data

- Sessions and settings: `~/Library/Application Support/tally/` (readable only by your account)
- Tally sign-in and Jira token: macOS Keychain, service `tally-cli`

Older versions stored data in `/Users/Shared/tally/`; it's copied over on first run.

## Tests

```bash
python3 -m unittest -v test_tally.py
```
