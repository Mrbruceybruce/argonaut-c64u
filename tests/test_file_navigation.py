import unittest
from c64u_browser.navigation import History

class HistoryTests(unittest.TestCase):
    def test_back_forward_and_new_branch(self):
        h = History('/a')
        h.visit('/b'); h.visit('/c')
        h.visit(h.target(-1), -1)
        self.assertEqual(h.target(1), '/c')
        h.visit('/d')
        self.assertIsNone(h.target(1))
        self.assertEqual(h.paths, ['/a', '/b', '/d'])

    def test_refresh_does_not_duplicate(self):
        h = History('/a'); h.visit('/a')
        self.assertIsNone(h.target(-1))
        self.assertIsNone(h.target(1))

    def test_failed_navigation_leaves_cursor(self):
        h = History('/a'); h.visit('/b')
        self.assertEqual(h.target(-1), '/a')
        self.assertEqual(h.index, 1) # looking up a target does not commit it
        with self.assertRaises(ValueError): h.visit('/other', -1)
        self.assertEqual(h.index, 1)
