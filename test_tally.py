"""Tests for the tally CLI. Run: python3 -m unittest -v test_tally.py

Network and Keychain are replaced with fakes, so nothing leaves the machine.
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
loader = importlib.machinery.SourceFileLoader("tally_cli", os.path.join(HERE, "tally"))
spec = importlib.util.spec_from_loader("tally_cli", loader)
tally = importlib.util.module_from_spec(spec)
loader.exec_module(tally)


class FakeServers:
    """Records requests and answers like Supabase and Jira do."""

    def __init__(self):
        self.calls = []
        self.fail_jira = False

    def __call__(self, method, url, headers=None, body=None):
        self.calls.append((method, url, headers or {}, body))
        if "/auth/v1/token" in url:
            return 200, {"access_token": "access", "refresh_token": "refresh-2",
                         "user": {"id": "user-1", "email": "me@example.com"}}
        if url.endswith("/rest/v1/sessions"):
            return 201, [{"id": "session-1"}]
        if "/worklog" in url:
            return (500, {"errorMessages": ["down"]}) if self.fail_jira else (201, {"id": "worklog-1"})
        if "/search/jql" in url:
            return 200, {"issues": [{"key": "ACME-7", "fields": {"summary": "Fix login", "status": {"name": "To Do"},
                                                                  "project": {"key": "ACME"}}}]}
        if "/issue/" in url:
            return 200, {"key": "ACME-7", "fields": {"summary": "Fix login", "project": {"key": "ACME"}}}
        return 404, {"message": "unexpected " + url}

    def posted(self, fragment):
        return [b for m, u, h, b in self.calls if m == "POST" and fragment in u]


class TallyTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.server = FakeServers()
        self.keychain = {"supabase-refresh": "refresh-1", "jira-token": "secret-token"}
        patches = [
            mock.patch.dict(os.environ, {"TALLY_HOME": self.home.name}),
            mock.patch.object(tally, "http", self.server),
            mock.patch.object(tally, "keychain_get", lambda a: self.keychain.get(a)),
            mock.patch.object(tally, "keychain_set", lambda a, s: self.keychain.__setitem__(a, s)),
            mock.patch.object(tally, "keychain_delete", lambda a: self.keychain.pop(a, None)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.home.cleanup)

    def run_cli(self, *argv, inputs=()):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch("builtins.input", side_effect=list(inputs)):
            code = tally.main(list(argv))
        return code, out.getvalue()

    def signed_in(self, jira=True, titles=False):
        config = {"goal": 10, "tally": {"user_id": "user-1", "email": "me@example.com"}}
        if jira:
            config["jira"] = {"site": "team.atlassian.net", "email": "me@example.com", "cloud_id": "cloud-1",
                              "store_titles": titles, "links": {"ACME": "Acme Corp"}}
        tally.save_config(config)

    def start_ago(self, minutes, **extra):
        stamp = (tally.now() - timedelta(minutes=minutes)).isoformat()
        active = {"client": "Acme Corp", "start": stamp, "started_at": stamp, "paused": False, "note": ""}
        active.update(extra)
        tally.save_data({"sessions": [], "active": active})

    # ----- timing -----

    def test_session_crossing_midnight_keeps_its_start_date(self):
        start = (datetime.now().astimezone() - timedelta(days=1)).replace(hour=23, minute=30, second=0, microsecond=0)
        tally.save_data({"sessions": [], "active": {"client": "Acme Corp", "start": start.isoformat(),
                                                    "started_at": start.isoformat(), "paused": False}})
        self.run_cli("stop")
        self.assertEqual(tally.load_data()["sessions"][0]["date"], start.date().isoformat())

    def test_pause_and_resume_keep_the_original_start(self):
        self.start_ago(30)
        original = tally.load_data()["active"]["started_at"]
        self.run_cli("pause")
        self.run_cli("resume")
        self.assertEqual(tally.load_data()["active"]["started_at"], original)
        self.assertAlmostEqual(tally.load_data()["active"]["accumulated"], 0.5, places=2)

    def test_fmt_hours_never_shows_sixty_minutes(self):
        self.assertEqual(tally.fmt_hours(1.9999), "2h")
        self.assertEqual(tally.fmt_hours(0.5), "30m")
        self.assertEqual(tally.fmt_hours(2.25), "2h 15m")

    def test_old_sessions_without_offset_still_parse(self):
        self.assertIsNotNone(tally.parse_dt("2026-10-14T09:00:00").tzinfo)

    # ----- Jira -----

    def test_worklog_seconds_round_to_minutes_with_one_minute_floor(self):
        self.assertEqual(tally.worklog_seconds(0.001), 60)
        self.assertEqual(tally.worklog_seconds(1.5), 5400)
        self.assertEqual(tally.worklog_seconds(0.2584), 960)  # 15.5 min → 16 min

    def test_jira_started_format(self):
        self.assertRegex(tally.jira_started("2026-10-15T09:05:07-04:00"), r"^2026-10-15T09:05:07\.000-0400$")

    def test_ticket_pattern(self):
        self.assertEqual(tally.TICKET_RE.search("FEATURE/ACME-123-LOGIN-FIX").group(1), "ACME-123")
        self.assertIsNone(tally.TICKET_RE.search("MAIN"))

    def test_normalize_site(self):
        self.assertEqual(tally.normalize_site("https://team.atlassian.net/jira/your-work"), "team.atlassian.net")
        self.assertEqual(tally.normalize_site("team"), "team.atlassian.net")

    def test_start_ticket_uses_linked_client(self):
        self.signed_in()
        self.run_cli("start", "acme-7")
        active = tally.load_data()["active"]
        self.assertEqual((active["client"], active["jira_key"], active["jira_summary"]), ("Acme Corp", "ACME-7", "Fix login"))

    def test_tasks_picker_starts_the_chosen_ticket(self):
        self.signed_in()
        code, out = self.run_cli("tasks", inputs=["1"])
        self.assertEqual(code, 0)
        self.assertIn("ACME-7", out)
        self.assertEqual(tally.load_data()["active"]["jira_key"], "ACME-7")

    def test_scoped_token_uses_atlassian_gateway_with_basic_auth(self):
        self.signed_in()
        self.run_cli("start", "ACME-7")
        method, url, headers, _ = self.server.calls[-1]
        self.assertTrue(url.startswith("https://api.atlassian.com/ex/jira/cloud-1/rest/api/3/issue/ACME-7"))
        self.assertTrue(headers["Authorization"].startswith("Basic "))

    # ----- stop + sync -----

    def test_stop_syncs_to_tally_and_logs_worklog(self):
        self.signed_in()
        self.start_ago(45, jira_key="ACME-7", jira_summary="Fix login", note="pairing")
        code, out = self.run_cli("stop")
        self.assertEqual(code, 0)
        session = self.server.posted("/rest/v1/sessions")[0]
        self.assertEqual(session["client"], "Acme Corp")
        self.assertEqual(session["platform"], "cli")
        self.assertEqual(session["task_note"], "ACME-7 · pairing")  # titles off by default
        worklog = self.server.posted("/worklog")[0]
        self.assertEqual(worklog["timeSpentSeconds"], 2700)
        saved = tally.load_data()["sessions"][0]["sync"]
        self.assertEqual(saved, {"tally": "session-1", "jira": "worklog-1"})
        self.assertEqual(self.keychain["supabase-refresh"], "refresh-2")  # rotated token was stored

    def test_session_carries_ticket_link(self):
        self.signed_in()
        self.start_ago(10, jira_key="ACME-7", jira_summary="Fix login")
        self.run_cli("stop")
        session = self.server.posted("/rest/v1/sessions")[0]
        self.assertEqual(session["external_key"], "ACME-7")
        self.assertEqual(session["external_url"], "https://team.atlassian.net/browse/ACME-7")

    def test_database_without_ticket_columns_still_syncs(self):
        self.signed_in()
        original = self.server.__call__

        def no_columns(method, url, headers=None, body=None):
            if url.endswith("/rest/v1/sessions") and body and "external_key" in body:
                self.server.calls.append((method, url, headers or {}, body))
                return 400, {"message": "Could not find the 'external_key' column of 'sessions' in the schema cache"}
            return original(method, url, headers, body)

        with mock.patch.object(tally, "http", no_columns):
            self.start_ago(10, jira_key="ACME-7", jira_summary="Fix login")
            self.run_cli("stop")
        posts = self.server.posted("/rest/v1/sessions")
        self.assertEqual(len(posts), 2)
        self.assertNotIn("external_key", posts[1])
        self.assertEqual(tally.load_data()["sessions"][0]["sync"]["tally"], "session-1")

    def test_titles_on_adds_ticket_title_to_task_note(self):
        self.signed_in(titles=True)
        self.start_ago(10, jira_key="ACME-7", jira_summary="Fix login")
        self.run_cli("stop")
        self.assertEqual(self.server.posted("/rest/v1/sessions")[0]["task_note"], "ACME-7 Fix login")

    def test_failed_worklog_is_retried_without_duplicating_the_tally_session(self):
        self.signed_in()
        self.server.fail_jira = True
        self.start_ago(20, jira_key="ACME-7", jira_summary="Fix login")
        _, out = self.run_cli("stop")
        self.assertIn("tally sync", out)
        self.assertEqual(tally.load_data()["sessions"][0]["sync"]["jira"], "pending")
        self.server.fail_jira = False
        self.run_cli("sync")
        self.assertEqual(len(self.server.posted("/rest/v1/sessions")), 1)
        self.assertEqual(len(self.server.posted("/worklog")), 2)
        self.assertEqual(tally.load_data()["sessions"][0]["sync"]["jira"], "worklog-1")

    def test_accidental_start_stop_skips_the_worklog(self):
        self.signed_in()
        stamp = tally.now().isoformat()
        tally.save_data({"sessions": [], "active": {"client": "Acme Corp", "start": stamp, "started_at": stamp,
                                                    "paused": False, "jira_key": "ACME-7"}})
        self.run_cli("stop")
        self.assertEqual(self.server.posted("/worklog"), [])

    def test_not_signed_in_keeps_the_session_local(self):
        self.start_ago(15)
        _, out = self.run_cli("stop")
        self.assertIn("tally login", out)
        self.assertEqual(self.server.calls, [])
        self.assertEqual(tally.load_data()["sessions"][0]["sync"]["tally"], "pending")

    def test_data_files_are_private(self):
        self.start_ago(1)
        self.assertEqual(os.stat(tally.data_path()).st_mode & 0o777, 0o600)


class AccuracyTest(unittest.TestCase):
    """Idle detection, commit review and proof of work."""

    def t(self, hh, mm):
        return datetime(2026, 10, 15, hh, mm).astimezone()

    def test_no_gap_when_activity_is_steady(self):
        events = [self.t(9, m) for m in range(5, 60, 10)]
        self.assertEqual(tally.idle_gaps([(self.t(9, 0), self.t(10, 0))], events, timedelta(minutes=20)), [])

    def test_lunch_in_the_middle_is_found_with_grace_on_both_sides(self):
        events = [self.t(9, 30), self.t(12, 0), self.t(13, 0), self.t(13, 15)]
        gaps = tally.idle_gaps([(self.t(9, 0), self.t(13, 30))], events, timedelta(minutes=20))
        self.assertEqual(gaps, [(self.t(9, 35), self.t(11, 55)), (self.t(12, 5), self.t(12, 55))])

    def test_reading_before_the_first_save_is_not_idle(self):
        events = [self.t(9, 35), self.t(9, 50)]
        self.assertEqual(tally.idle_gaps([(self.t(9, 0), self.t(10, 0))], events, timedelta(minutes=20)), [])

    def test_forgot_to_stop_trims_the_tail(self):
        gaps = tally.idle_gaps([(self.t(9, 0), self.t(17, 0))], [self.t(9, 50)], timedelta(minutes=20))
        self.assertEqual(gaps[-1], (self.t(9, 55), self.t(17, 0)))

    def test_paused_time_is_never_counted_as_idle(self):
        segments = [(self.t(9, 0), self.t(9, 30)), (self.t(13, 0), self.t(13, 30))]
        events = [self.t(9, 25), self.t(13, 20)]
        self.assertEqual(tally.idle_gaps(segments, events, timedelta(minutes=20)), [])

    def test_commits_group_into_blocks(self):
        blocks = tally.work_blocks([self.t(14, 0), self.t(14, 40), self.t(15, 50), self.t(19, 0)])
        self.assertEqual(blocks, [(self.t(13, 30), self.t(15, 50)), (self.t(18, 30), self.t(19, 0))])

    def test_uncovered_skips_tracked_time_and_short_leftovers(self):
        parts = tally.uncovered((self.t(13, 30), self.t(16, 0)), [(self.t(14, 0), self.t(15, 50))])
        self.assertEqual(parts, [(self.t(13, 30), self.t(14, 0))])  # the 10 minutes after 15:50 is too short

    def test_worklog_comment_lists_commits(self):
        doc = tally.worklog_comment({"note": "pairing", "proof": ["abc1234 Fix login"]})
        self.assertEqual(doc["content"][0]["content"][0]["text"], "pairing")
        self.assertEqual(doc["content"][2]["type"], "bulletList")
        self.assertIsNone(tally.worklog_comment({"proof": ["abc"]}, include_proof=False))


class GitActivityTest(unittest.TestCase):
    """Reads a real throwaway git repo."""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo)
        for args in (["init", "-q", "-b", "SCRUM-97-nav-graph"], ["config", "user.email", "me@example.com"],
                     ["config", "user.name", "Me"], ["config", "commit.gpgsign", "false"]):
            subprocess.run(["git", "-C", self.repo, *args], check=True)
        self.base = (datetime.now().astimezone() - timedelta(hours=3)).replace(microsecond=0)
        for i, minutes in enumerate((0, 20, 45)):
            when = (self.base + timedelta(minutes=minutes)).isoformat()
            with open(os.path.join(self.repo, f"f{i}.txt"), "w") as fh:
                fh.write(str(i))
            subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
            env = dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
            subprocess.run(["git", "-C", self.repo, "commit", "-q", "-m", f"Step {i}"], check=True, env=env)

    def test_my_commits_finds_times_and_branch_ticket(self):
        commits = tally.my_commits(self.repo, self.base - timedelta(minutes=1), self.base + timedelta(hours=1))
        self.assertEqual([c[2] for c in commits], ["Step 0", "Step 1", "Step 2"])
        self.assertEqual({c[3] for c in commits}, {"SCRUM-97"})
        self.assertEqual(commits[1][0], self.base + timedelta(minutes=20))

    def test_other_authors_are_ignored(self):
        subprocess.run(["git", "-C", self.repo, "config", "user.email", "someone@else.com"], check=True)
        self.assertEqual(tally.my_commits(self.repo, self.base - timedelta(hours=1), datetime.now().astimezone()), [])


class WeekAndExpiryTest(unittest.TestCase):
    def test_week_follows_account_week_start(self):
        from datetime import date
        thursday = date(2026, 10, 15)
        self.assertEqual(tally.week_bounds(thursday, 1), (date(2026, 10, 12), date(2026, 10, 18)))  # Monday
        self.assertEqual(tally.week_bounds(thursday, 0), (date(2026, 10, 11), date(2026, 10, 17)))  # Sunday
        self.assertEqual(tally.week_bounds(thursday, 3), (date(2026, 10, 14), date(2026, 10, 20)))  # Wednesday
        self.assertEqual(tally.week_bounds(thursday, 4), (thursday, date(2026, 10, 21)))  # starts today

    def test_expiry_date_input(self):
        from datetime import date
        today = date(2026, 10, 15)
        self.assertIsNone(tally.parse_expiry("", today))
        self.assertEqual(tally.parse_expiry(" 2026-12-30 ", today), "2026-12-30")
        for bad in ("12/30/2026", "2026-10-01", "2028-01-01"):
            with self.assertRaises(tally.TallyError):
                tally.parse_expiry(bad, today)

    def test_expiry_warning_only_in_the_last_week(self):
        from datetime import date
        config = {"jira": {"token_expires_on": "2026-12-30"}}
        self.assertIsNone(tally.jira_token_warning(config, date(2026, 12, 22)))
        self.assertIn("in 7 days", tally.jira_token_warning(config, date(2026, 12, 23)))
        self.assertIn("tomorrow", tally.jira_token_warning(config, date(2026, 12, 29)))
        self.assertIn("expired", tally.jira_token_warning(config, date(2027, 1, 2)))
        self.assertIsNone(tally.jira_token_warning({"jira": {}}, date(2026, 12, 29)))


if __name__ == "__main__":
    unittest.main()
