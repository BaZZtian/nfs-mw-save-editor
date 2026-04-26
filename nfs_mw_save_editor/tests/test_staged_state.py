import unittest

from ui.staged_state import StagedMap, StagedScalar, StagedSnapshotInjections


class StagedScalarTests(unittest.TestCase):
    def test_current_set_clear_reset_and_pending(self) -> None:
        staged = StagedScalar[int]()

        self.assertEqual(staged.current(10), 10)
        self.assertFalse(staged.has_pending(10))

        staged.set(20)
        self.assertEqual(staged.current(10), 20)
        self.assertTrue(staged.has_pending(10))

        staged.clear()
        self.assertEqual(staged.current(10), 10)
        self.assertFalse(staged.has_pending(10))

        staged.reset_to(10)
        self.assertEqual(staged.current(99), 10)
        self.assertFalse(staged.has_pending(10))


class StagedMapTests(unittest.TestCase):
    def test_set_item_seeds_from_have(self) -> None:
        staged = StagedMap[str, int]()

        staged.set_item("b", 20, {"a": 1, "b": 2})

        self.assertEqual(staged.current({}), {"a": 1, "b": 20})

    def test_get_item_uses_staged_have_default_fallbacks(self) -> None:
        staged = StagedMap[str, int]()
        have = {"a": 1, "b": 2}

        self.assertEqual(staged.get_item("a", have, 0), 1)
        self.assertEqual(staged.get_item("missing", have, 0), 0)

        staged.set_item("a", 10, have)
        staged.set_item("c", 30, have)

        self.assertEqual(staged.get_item("a", have, 0), 10)
        self.assertEqual(staged.get_item("b", have, 0), 2)
        self.assertEqual(staged.get_item("c", have, 0), 30)
        self.assertEqual(staged.get_item("missing", have, 0), 0)

    def test_clear_reset_prune_and_pending(self) -> None:
        staged = StagedMap[str, int]()
        have = {"a": 1, "b": 2, "c": 3}

        staged.reset_to(have)
        self.assertEqual(staged.current({}), have)
        self.assertFalse(staged.has_pending(dict(have)))

        staged.set_item("b", 20, have)
        self.assertTrue(staged.has_pending(have))

        staged.prune_to_keys({"b", "c", "d"}, have)
        self.assertEqual(staged.current({}), {"b": 20, "c": 3})
        self.assertTrue(staged.has_pending(have))

        staged.clear()
        self.assertEqual(staged.current(have), have)
        self.assertFalse(staged.has_pending(have))

    def test_prune_without_staged_state_is_noop(self) -> None:
        staged = StagedMap[str, int]()
        have = {"a": 1, "b": 2}

        staged.prune_to_keys({"a"}, have)

        self.assertEqual(staged.current(have), have)
        self.assertFalse(staged.has_pending(have))


class StagedSnapshotInjectionsTests(unittest.TestCase):
    def test_stage_clear_clear_all_mode_and_pending(self) -> None:
        staged = StagedSnapshotInjections()

        self.assertIsNone(staged.mode_for("snap-a"))
        self.assertFalse(staged.has_pending())

        staged.stage("snap-a", "career")
        staged.stage("snap-b", "my_cars")

        self.assertEqual(staged.mode_for("snap-a"), "career")
        self.assertTrue(staged.has_pending())

        staged.clear("snap-a")
        self.assertIsNone(staged.mode_for("snap-a"))
        self.assertEqual(staged.mode_for("snap-b"), "my_cars")

        staged.clear_all()
        self.assertFalse(staged.has_pending())

    def test_ordered_items_uses_library_order_and_appends_unknown_items(self) -> None:
        staged = StagedSnapshotInjections()
        staged.stage("snap-c", "career")
        staged.stage("snap-a", "my_cars")
        staged.stage("snap-x", "career")

        self.assertEqual(
            staged.ordered_items(["snap-a", "snap-b", "snap-c"]),
            [("snap-a", "my_cars"), ("snap-c", "career"), ("snap-x", "career")],
        )

    def test_ordered_items_extra_overrides_returned_preview_only(self) -> None:
        staged = StagedSnapshotInjections()
        staged.stage("snap-a", "career")

        self.assertEqual(
            staged.ordered_items(["snap-a"], extra_snapshot_id="snap-a", extra_target_mode="my_cars"),
            [("snap-a", "my_cars")],
        )
        self.assertEqual(staged.mode_for("snap-a"), "career")

    def test_ordered_items_requires_complete_extra_pair(self) -> None:
        staged = StagedSnapshotInjections()

        with self.assertRaises(ValueError):
            staged.ordered_items(["snap-a"], extra_snapshot_id="snap-a")


if __name__ == "__main__":
    unittest.main()
