"""Accounting, timestamp and episode tests; synthetic data only."""
import unittest
import numpy as np
import pandas as pd
import backtest as b


class BacktestTests(unittest.TestCase):
    def test_roundtrip_cost_and_monotonic_stress(self):
        self.assertLess(b.etf_return(100, 100), 0)
        self.assertLess(b.etf_return(100, 101, .01), b.etf_return(100, 101))
        expected = ((101 * .9999) * (1 - .0000051) - .000119) / (100 * 1.0001) - 1
        self.assertAlmostEqual(b.etf_return(100, 101), expected)

    def test_drawdown_includes_initial_capital(self):
        m = b.metrics(pd.Series([-.1, 0]))
        self.assertAlmostEqual(m['ending_cash'], 90)
        self.assertAlmostEqual(m['max_daily_drawdown'], -.1)

    def test_episode_recovery_at_same_price(self):
        t = np.array([0, 1, 2, 3], dtype=np.int64) * 1_000_000_000
        e = b.episode_features(t, np.ones(4)*100, np.ones(4)*101, np.array([100,40,60,100]), np.ones(4)*100, 0, 4_000_000_000)
        self.assertEqual(len(e[0]), 1)
        self.assertTrue(e[0][0][1])

    def test_price_move_is_failure_not_recovery(self):
        t = np.array([0, 1, 2], dtype=np.int64) * 1_000_000_000
        e = b.episode_features(t, np.array([100,100,99]), np.ones(3)*101, np.array([100,40,200]), np.ones(3)*100, 0, 3_000_000_000)
        self.assertEqual(e[0][0][1:], (False, True))

    def test_future_recovery_does_not_repair_timeout(self):
        t = np.array([0, 1, 7], dtype=np.int64) * 1_000_000_000
        e = b.episode_features(t, np.ones(3)*100, np.ones(3)*101, np.array([100,40,100]), np.ones(3)*100, 0, 3_000_000_000)
        self.assertFalse(e[0][0][1])

    def test_signal_requires_both_blocks(self):
        left = [[(i, True, False) for i in range(20)], [(i, False, False) for i in range(20)]]
        right = [left[1], left[0]]
        self.assertEqual(b.episode_direction([left, right])[0], 0)
        self.assertEqual(b.episode_direction([left, left])[0], 1)

    def test_dst_and_short_day(self):
        self.assertEqual(b.stamp('2023-03-10','09:30').tz_convert('UTC').hour, 14)
        self.assertEqual(b.stamp('2023-03-13','09:30').tz_convert('UTC').hour, 13)
        self.assertFalse(b.regular(pd.Timestamp('2023-11-24')))

    def test_overnight_trade_rejected(self):
        day = pd.Timestamp('2023-01-03')
        row = {'day':day,'direction':1,'entry':b.stamp(day,'15:30'), 'exit':b.stamp(day+pd.Timedelta(days=1),'09:30'), 'return':.01}
        with self.assertRaises(AssertionError):
            b.summarize([row], pd.DatetimeIndex([day]))


if __name__ == '__main__':
    unittest.main()
