import unittest

from app.forgery.fixed_category import explanation_prompt


class FixedCategoryTests(unittest.TestCase):
    def test_fixed_category_prompt_keeps_category_and_visible_evidence(self):
        prompt = explanation_prompt("currency_analysis", "Currency Forgery")
        self.assertIn("Use exactly currency_analysis", prompt)
        self.assertIn("Begin explanation with Currency Forgery", prompt)
        self.assertIn("Do not substitute a new verdict", prompt)
        self.assertIn("Do not invent evidence", prompt)

    def test_genuine_category_can_still_be_selected(self):
        prompt = explanation_prompt("no_forgery_detected", "No Forgery Detected")
        self.assertIn("Use exactly no_forgery_detected", prompt)
        self.assertIn("itself the fixed classification", prompt)
