import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class HomeAbsenceIdentityTests(unittest.TestCase):
    def test_home_calendar_absence_matches_by_user_id_not_display_name(self):
        src = (ROOT / "frontend" / "js" / "home.js").read_text(encoding="utf-8")
        self.assertIn("function absenceFor(workerId, dateStr)", src)
        self.assertIn("String(e.user_id) === String(workerId)", src)
        self.assertNotIn("absenceFor(w.name", src)
        self.assertNotIn("e.name === workerName", src)


if __name__ == "__main__":
    unittest.main()
