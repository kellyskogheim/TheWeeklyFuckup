import unittest
from datetime import date

from ce_agent.calendar_sync import parse_tags
from ce_agent.rules import calculate_progress, risk_level


class RulesTests(unittest.TestCase):
    def test_50_minute_hours_and_business_cap(self):
        rows = [
            {
                "completed_on": "2026-01-01",
                "minutes": 200,
                "activity_kind": "Organized",
                "ce_type": "General Business",
                "bias_topic": 0,
                "specific_education": 0,
                "status": "completed",
            },
            {
                "completed_on": "2026-02-01",
                "minutes": 150,
                "activity_kind": "Organized",
                "ce_type": "Professionalism",
                "bias_topic": 1,
                "specific_education": 1,
                "status": "completed",
            },
        ]
        progress = calculate_progress(rows, 2026)
        self.assertEqual(progress.general_business, 4.0)
        self.assertEqual(progress.total, 6.0)
        self.assertEqual(progress.organized, 7.0)
        self.assertEqual(progress.professionalism, 3.0)
        self.assertEqual(progress.bias, 3.0)

    def test_planned_and_unclassified_do_not_count(self):
        rows = [
            {
                "completed_on": "2026-01-01",
                "minutes": 500,
                "activity_kind": "Organized",
                "ce_type": "Other Relevant",
                "bias_topic": 0,
                "specific_education": 0,
                "status": "planned",
            }
        ]
        progress = calculate_progress(rows, 2026)
        self.assertEqual(progress.total, 0)

    def test_calendar_tags(self):
        tags = parse_tags("CE-Type: Professionalism\nCE-Bias: Yes\nCE-Minutes: 75")
        self.assertEqual(tags["type"], "Professionalism")
        self.assertEqual(tags["bias"], "Yes")
        self.assertEqual(tags["minutes"], "75")

    def test_year_end_gap_is_urgent(self):
        progress = calculate_progress([], 2026)
        self.assertEqual(risk_level(progress, date(2026, 12, 1)), "urgent")


if __name__ == "__main__":
    unittest.main()
