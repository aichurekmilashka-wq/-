import concurrent.futures
import tempfile
import unittest
from pathlib import Path

try:
    from worktime.store import Store, Problem
except ModuleNotFoundError:
    Store = None


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Store, "Хранилище ещё не реализовано")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "test.sqlite3"
        self.now = 1793966400.0  # 2026-11-06 12:00 UTC
        self.store = Store(self.path, clock=lambda: self.now)
        self.person = self.store.add_employee("Анна Примерова")

    def start(self, description="Подготовка отчёта"):
        return self.store.start(self.person["id"], description)

    def report(self, start="2026-11-06", end="2026-11-06"):
        return self.store.report(start, end)

    def event(self, session, begin, end, **extra):
        return self.store.record_activity(self.person["tracking_key"], {
            "event_id": "event-one", "session_id": session["id"],
            "started_at": begin, "ended_at": end,
            "kind": "page", "url": "https://example.org/research?q=private#part",
            "title": "Вымышленное исследование", **extra,
        })

    def test_employee_survives_reopen(self):
        reopened = Store(self.path, clock=lambda: self.now)
        self.assertEqual(reopened.employees()[0]["name"], "Анна Примерова")

    def test_blank_employee_is_rejected(self):
        with self.assertRaises(Problem):
            self.store.add_employee("  ")

    def test_blank_description_is_rejected(self):
        with self.assertRaises(Problem):
            self.start("\n ")

    def test_stop_calculates_server_time(self):
        session = self.start()
        self.now += 1500
        self.store.stop(session["id"])
        self.assertEqual(self.report()["employees"][0]["total_seconds"], 1500)

    def test_second_start_does_not_create_another_timer(self):
        session = self.start()
        with self.assertRaises(Problem) as caught:
            self.start("Другая задача")
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.store.active(self.person["id"])["id"], session["id"])

    def test_simultaneous_start_only_creates_one_timer(self):
        def run(_):
            try:
                self.start()
                return 201
            except Problem as error:
                return error.status
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(run, range(2))), [201, 409])

    def test_restart_after_stop_creates_new_session(self):
        first = self.start()
        self.now += 60
        self.store.stop(first["id"])
        second = self.start("Следующая задача")
        self.assertNotEqual(first["id"], second["id"])

    def test_repeated_stop_preserves_original_end(self):
        session = self.start()
        self.now += 60
        first = self.store.stop(session["id"])
        self.now += 90
        second = self.store.stop(session["id"])
        self.assertEqual(first["ended_at"], second["ended_at"])

    def test_active_timer_survives_application_restart(self):
        session = self.start()
        self.now += 120
        reopened = Store(self.path, clock=lambda: self.now)
        self.assertEqual(reopened.active(self.person["id"])["id"], session["id"])
        self.assertEqual(reopened.report("2026-11-06", "2026-11-06")["total_seconds"], 120)

    def test_empty_report_keeps_employees_with_zero(self):
        result = self.report()
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["total_seconds"], 0)
        self.assertEqual(result["employees"][0]["total_seconds"], 0)

    def test_report_clips_session_at_midnight(self):
        self.now = 1794009000.0  # 2026-11-06 23:50 UTC
        session = self.start()
        self.now += 1200
        self.store.stop(session["id"])
        self.assertEqual(self.report()["total_seconds"], 600)
        self.assertEqual(self.report("2026-11-07", "2026-11-07")["total_seconds"], 600)

    def test_reversed_period_is_rejected(self):
        with self.assertRaises(Problem):
            self.report("2026-11-07", "2026-11-06")

    def test_invalid_date_is_rejected(self):
        with self.assertRaises(Problem):
            self.report("2026-02-30", "2026-11-06")

    def test_activity_removes_query_and_fragment(self):
        session = self.start()
        self.now += 30
        self.event(session, self.now - 30, self.now)
        page = self.report()["pages"][0]
        self.assertEqual(page["url"], "https://example.org/research")
        self.assertEqual(page["seconds"], 30)

    def test_retry_of_same_event_does_not_double_time(self):
        session = self.start()
        self.now += 30
        self.event(session, self.now - 30, self.now)
        self.event(session, self.now - 30, self.now)
        self.assertEqual(self.report()["page_seconds"], 30)

    def test_overlapping_events_are_clipped(self):
        session = self.start()
        self.now += 45
        self.event(session, self.now - 45, self.now - 15)
        self.event(session, self.now - 30, self.now, event_id="event-two")
        self.assertEqual(self.report()["page_seconds"], 45)

    def test_sleep_gap_is_not_counted_as_a_page(self):
        session = self.start()
        self.now += 600
        with self.assertRaises(Problem):
            self.event(session, self.now - 600, self.now)
        self.assertEqual(self.report()["unobserved_seconds"], 600)

    def test_activity_after_stop_is_clipped(self):
        session = self.start()
        self.now += 20
        self.store.stop(session["id"])
        self.now += 10
        self.event(session, self.now - 30, self.now)
        self.assertEqual(self.report()["page_seconds"], 20)

    def test_invalid_tracking_key_is_rejected(self):
        with self.assertRaises(Problem) as caught:
            self.store.tracker_state("not-a-real-key")
        self.assertEqual(caught.exception.status, 401)

    def test_other_employee_cannot_write_activity(self):
        session = self.start()
        other = self.store.add_employee("Олег Вымышленный")
        self.now += 30
        with self.assertRaises(Problem):
            self.store.record_activity(other["tracking_key"], {
                "event_id": "wrong-owner", "session_id": session["id"],
                "started_at": self.now - 30, "ended_at": self.now,
                "kind": "idle",
            })

    def test_report_distinguishes_idle_away_and_unobserved(self):
        session = self.start()
        self.now += 90
        self.event(session, self.now - 90, self.now - 60, kind="idle")
        self.event(session, self.now - 60, self.now - 30, kind="away", event_id="away")
        result = self.report()
        self.assertEqual((result["idle_seconds"], result["away_seconds"], result["unobserved_seconds"]), (30, 30, 30))

    def test_clock_rollback_does_not_make_activity_exceed_task(self):
        session = self.start()
        self.now += 60
        self.event(session, self.now - 60, self.now)
        self.now -= 40
        self.store.stop(session["id"])
        self.now += 120
        report = self.report()
        self.assertEqual(report["total_seconds"], 20)
        self.assertEqual(report["page_seconds"], 20)

    def test_unknown_employee_does_not_start_a_timer(self):
        with self.assertRaises(Problem) as caught:
            self.store.start(999, "Несуществующий сотрудник")
        self.assertEqual(caught.exception.status, 404)

    def test_future_activity_is_rejected(self):
        session = self.start()
        with self.assertRaises(Problem):
            self.event(session, self.now, self.now + 30)

    def test_non_finite_time_is_rejected(self):
        session = self.start()
        with self.assertRaises(Problem):
            self.event(session, self.now, float("nan"))

    def test_page_outside_shortened_task_is_not_listed_with_zero_time(self):
        session = self.start()
        self.now += 60
        self.event(session, self.now - 30, self.now)
        self.now -= 40
        self.store.stop(session["id"])
        self.now += 120
        self.assertEqual(self.report()["pages"], [])

    def test_completely_empty_database_has_zero_report(self):
        empty = Store(Path(self.tmp.name) / "empty.sqlite3", clock=lambda: self.now)
        report = empty.report("2026-11-06", "2026-11-06")
        self.assertEqual(report["employees"], [])
        self.assertEqual(report["entries"], [])
        self.assertEqual(report["total_seconds"], 0)

    def test_employee_filter_does_not_mix_team_totals(self):
        anna = self.start()
        other = self.store.add_employee("Олег Вымышленный")
        oleg = self.store.start(other["id"], "Другая задача")
        self.now += 60
        self.store.stop(anna["id"])
        self.now += 30
        self.store.stop(oleg["id"])
        report = self.store.report("2026-11-06", "2026-11-06", self.person["id"])
        self.assertEqual(report["total_seconds"], 60)
        self.assertEqual([entry["employee_id"] for entry in report["entries"]], [self.person["id"]])
        self.assertEqual(self.report()["total_seconds"], 150)


if __name__ == "__main__":
    unittest.main()
