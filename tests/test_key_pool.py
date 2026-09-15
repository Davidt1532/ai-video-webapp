"""Unit tests for the rotating NovAI API key pool and its integration with
video_generator. Run: python -m unittest tests.test_key_pool -v
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import key_pool as key_pool_mod
from key_pool import KeyPool
from config import FREE_DAILY_VIDEO_LIMIT, QUOTA_OFFSET_HOURS


import requests

class _FakeResp:
    def __init__(self, status_code, json_body):
        self.status_code = status_code
        self._json = json_body
    def json(self):
        return self._json
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)


class TestParseKeys(unittest.TestCase):
    def test_comma_separated_with_spaces(self):
        with patch.object(key_pool_mod, "VIDEO_API_KEYS", " k1 , k2 , k3 "), \
             patch.object(key_pool_mod, "VIDEO_API_KEY", "k0"):
            self.assertEqual(key_pool_mod._parse_keys(), ["k1", "k2", "k3"])

    def test_blanks_and_trailing_comma(self):
        with patch.object(key_pool_mod, "VIDEO_API_KEYS", "k1,,,k2,"), \
             patch.object(key_pool_mod, "VIDEO_API_KEY", "k0"):
            self.assertEqual(key_pool_mod._parse_keys(), ["k1", "k2"])

    def test_fallback_to_single_key(self):
        with patch.object(key_pool_mod, "VIDEO_API_KEYS", ""), \
             patch.object(key_pool_mod, "VIDEO_API_KEY", "only"):
            self.assertEqual(key_pool_mod._parse_keys(), ["only"])

    def test_no_keys(self):
        with patch.object(key_pool_mod, "VIDEO_API_KEYS", ""), \
             patch.object(key_pool_mod, "VIDEO_API_KEY", ""):
            self.assertEqual(key_pool_mod._parse_keys(), [])


class TestKeyPool(unittest.TestCase):
    def setUp(self):
        self.pool = KeyPool(["kA", "kB"], daily_limit=2)

    def test_round_robin_and_quota(self):
        got = []
        for _ in range(6):
            k = self.pool.get_video_key()
            if k:
                self.pool.mark_submitted(k)
                got.append(k)
        # 2 keys x 2 limit = 4 usable, then None
        self.assertEqual(got, ["kA", "kB", "kA", "kB"])
        self.assertIsNone(self.pool.get_video_key())

    def test_mark_exhausted(self):
        self.pool.mark_exhausted("kA")
        self.assertEqual([self.pool.get_video_key() for _ in range(3)], ["kB", "kB", "kB"])

    def test_any_key_ignores_video_quota(self):
        for _ in range(4):
            k = self.pool.get_video_key()
            self.pool.mark_submitted(k)
        self.assertEqual(self.pool.any_key(), "kA")

    def test_mark_submitted_unknown_key_is_noop(self):
        self.pool.mark_submitted("nope")
        self.assertEqual(self.pool.status()[0]["used"], 0)

    def test_day_reset(self):
        for _ in range(4):
            k = self.pool.get_video_key()
            self.pool.mark_submitted(k)
        self.assertIsNone(self.pool.get_video_key())
        # Simulate a new UTC+8 day beginning (yesterday's date in that zone).
        self.pool._day = (datetime.utcnow() + timedelta(hours=QUOTA_OFFSET_HOURS - 24)).date().isoformat()
        self.pool._exhausted["kA"] = True
        self.pool._reset_if_new_day()
        self.assertEqual(self.pool._used, {"kA": 0, "kB": 0})
        self.assertEqual(self.pool._exhausted, {"kA": False, "kB": False})
        self.assertEqual(self.pool.get_video_key(), "kA")

    def test_all_exhausted_message(self):
        msg = self.pool.all_exhausted_message()
        self.assertIn("2 NovAI API key(s)", msg)
        self.assertIn("2 video generations", msg)

    def test_free_limit_matches_config(self):
        self.assertEqual(KeyPool(["x"])._limit, FREE_DAILY_VIDEO_LIMIT)


class TestRotationInGenerateVideo(unittest.TestCase):
    """Simulated submit: key A returns 'daily limit' 429, key B succeeds.
    Asserts the generator switches keys and polls with the winning key."""

    def test_auto_switch_on_daily_limit(self):
        import video_generator
        pool = KeyPool(["kA", "kB"], daily_limit=2)
        video_generator.key_pool = pool

        post_headers = []
        calls = {"post": 0, "get": 0}

        def fake_post(url, headers=None, json=None, timeout=None, **kw):
            calls["post"] += 1
            post_headers.append(headers)
            key = headers["Authorization"].split()[-1]
            if key == "kA":
                return _FakeResp(429, {"detail": "You have reached the "
                    "daily limit of 5 free video generations (video generation is GPU-heavy "
                    "upstream). Limit resets at midnight (UTC+8)."})
            return _FakeResp(200, {"id": "task-1"})

        def fake_get(url, headers=None, params=None, timeout=None, **kw):
            calls["get"] += 1
            return _FakeResp(200, {"task_status": "succeeded",
                                    "video_result": [{"url": "http://cdn/x.mp4"}]})

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(video_generator.requests, "post", side_effect=fake_post), \
             patch.object(video_generator.requests, "get", side_effect=fake_get), \
             patch.object(video_generator, "download_video",
                          side_effect=lambda u, p: p):
            path = video_generator.generate_video("Test prompt", 1, output_dir=tmp)

        self.assertTrue(path.endswith(os.path.join("clips", "scene_01.mp4")))
        self.assertEqual(calls["post"], 2)
        self.assertEqual(calls["get"], 1)
        self.assertEqual(post_headers[0]["Authorization"], "Bearer kA")
        self.assertEqual(post_headers[1]["Authorization"], "Bearer kB")
        # Winning key must be used for polling and counted against quota.
        self.assertEqual(pool.status()[1]["used"], 1)
        self.assertTrue(pool.status()[0]["exhausted"])

    def test_all_exhausted_raises(self):
        import video_generator
        pool = KeyPool(["kA", "kB"], daily_limit=1)
        pool.mark_exhausted("kA")
        pool.mark_exhausted("kB")
        video_generator.key_pool = pool
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(video_generator.requests, "post") as mpost:
            with self.assertRaises(video_generator.DailyQuotaExceeded):
                video_generator.generate_video("Test", 1, output_dir=tmp)
        mpost.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)