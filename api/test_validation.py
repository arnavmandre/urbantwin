import unittest

from api.validation import validate_run_request, validate_view_command


class ValidationTests(unittest.TestCase):
    def test_accepts_extreme_heat_rain_preset(self):
        body = {
            "temperature": 40,
            "humidity": 80,
            "rainfall": 80,
            "population": 100000,
            "apply_recommended_interventions": True,
            "animation_frames": 3,
            "animation_duration_seconds": 6,
        }
        request, error = validate_run_request(body)
        self.assertIsNone(error)
        self.assertEqual(request["population"], 100000)
        self.assertEqual(request["animation_frames"], 3)

    def test_city_defaults_to_london_accepts_pune_rejects_unknown(self):
        base = {"temperature": 30, "humidity": 50, "rainfall": 0, "population": 50000,
                "apply_recommended_interventions": False}
        self.assertEqual(validate_run_request(base)[0]["city"], "london")
        self.assertEqual(validate_run_request({**base, "city": "pune"})[0]["city"], "pune")
        for bad in ("paris", [], {"key": "pune"}, 3):
            request, error = validate_run_request({**base, "city": bad})
            self.assertIsNone(request)
            self.assertIn("city", error["error"]["fields"])

    def test_rejects_out_of_range_temperature(self):
        body = {
            "temperature": 99,
            "humidity": 80,
            "rainfall": 80,
            "population": 100000,
            "apply_recommended_interventions": True,
        }
        request, error = validate_run_request(body)
        self.assertIsNone(request)
        self.assertEqual(error["error"]["code"], "validation_failed")

    def test_accepts_allow_listed_user_selection(self):
        body = {
            "temperature": 40,
            "humidity": 80,
            "rainfall": 80,
            "population": 100000,
            "apply_recommended_interventions": True,
            "selected_recommendation_ids": ["increase_shade", "improve_drainage"],
        }
        request, error = validate_run_request(body)
        self.assertIsNone(error)
        self.assertEqual(request["selected_recommendation_ids"], body["selected_recommendation_ids"])

    def test_rejects_unknown_user_selected_action(self):
        body = {
            "temperature": 40,
            "humidity": 80,
            "rainfall": 80,
            "population": 100000,
            "apply_recommended_interventions": True,
            "selected_recommendation_ids": ["build_metro_station"],
        }
        request, error = validate_run_request(body)
        self.assertIsNone(request)
        self.assertIn("selected_recommendation_ids", error["error"]["fields"])

    def test_view_command_allow_list(self):
        ok, err = validate_view_command(
            {"state": "before", "camera": "ProblemZone", "overlay": "behavior"}
        )
        self.assertIsNone(err)
        self.assertEqual(ok["playback"], "play")
        paused, pause_err = validate_view_command(
            {
                "state": "after",
                "camera": "Overview",
                "overlay": "behavior",
                "playback": "pause",
            }
        )
        self.assertIsNone(pause_err)
        self.assertEqual(paused["playback"], "pause")
        bad, err2 = validate_view_command(
            {"state": "before", "camera": "/World/Hack", "overlay": "behavior"}
        )
        self.assertIsNone(bad)
        self.assertEqual(err2["error"]["code"], "validation_failed")


if __name__ == "__main__":
    unittest.main()
