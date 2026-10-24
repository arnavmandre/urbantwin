import csv
import io
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from phase10 import generate_citizens as g


class NewSurveyTests(unittest.TestCase):
    def test_mapping_directions_and_missing(self):
        answers = {q: [next(iter(options))] for q, options in g.FORM_OPTIONS.items()}
        answers[4] = ["Not at all"]
        answers[5] = answers[6] = ["Very comfortable"]
        answers[7] = ["No extra time"]
        answers[8] = ["Very comfortable"]
        answers[9] = ["No extra time"]
        answers[14] = ["I would avoid walking"]
        answers[15] = [""]
        values, used = g.map_form(answers)
        self.assertAlmostEqual(values[0, 0], .98)
        self.assertAlmostEqual(values[0, 2], .98)
        self.assertTrue(np.isnan(values[0, 3]))
        self.assertEqual(used[0, 3], 0)
        answers[7] = ["More than 10 minutes"]
        self.assertLess(g.map_form(answers)[0][0, 0], values[0, 0])

    def test_copula_uses_only_training_marginals_and_is_repeatable(self):
        x = np.column_stack([np.arange(12.) / 12] * 7)
        x[:, 6] = np.arange(12) % 4
        model = g.fit_normal_copula(x)
        a = g.draw_normal_copula(model, 1000, np.random.default_rng(7))
        b = g.draw_normal_copula(model, 1000, np.random.default_rng(7))
        np.testing.assert_array_equal(a, b)
        self.assertTrue(np.all(a >= np.min(x, axis=0)))
        self.assertTrue(np.all(a <= np.max(x, axis=0)))
        self.assertTrue(set(a[:, 6]) <= set(x[:, 6]))
        self.assertGreater(np.linalg.eigvalsh(model['correlation']).min(), 0)
        self.assertGreater(np.corrcoef(a[:, 0], a[:, 1])[0, 1], .95)

    def test_missing_imputation_uses_training_only(self):
        x = np.array([[1., 2.], [3., np.nan], [5., 6.]])
        model = g.fit_normal_copula(x)
        self.assertEqual(model['medians'][1], 4.)
        with self.assertRaises(ValueError):
            g.fit_normal_copula(np.full((5, 2), np.nan))

    def test_respondent_holdouts_are_disjoint_and_repeatable(self):
        x = np.random.default_rng(3).uniform(size=(30, 7))
        x[:, 6] = np.arange(30) % 4
        metrics, splits = g.validate_form(x, 7, 100)
        again, same = g.validate_form(x, 7, 100)
        self.assertEqual(splits, same)
        self.assertEqual(metrics, again)
        self.assertEqual(len(splits), 20)
        for split in splits:
            train, test = set(split['training_rows']), set(split['holdout_rows'])
            self.assertFalse(train & test)
            self.assertEqual(train | test, set(range(1, 31)))
            self.assertEqual(len(test), 6)

    def test_bad_answer_reports_only_row_and_question(self):
        f = io.StringIO()
        w = csv.writer(f)
        w.writerow(['Name', *[f'{q}. question' for q in range(1, 17)]])
        w.writerow(['PRIVATE NAME', *['bad'] * 16])
        f.seek(0)
        with patch.object(Path, 'open', return_value=f):
            with self.assertRaises(ValueError) as e:
                g.read_form(Path('responses.csv'))
            self.assertNotIn('PRIVATE NAME', str(e.exception))
            self.assertIn('Q1', str(e.exception))


if __name__ == '__main__':
    unittest.main()
