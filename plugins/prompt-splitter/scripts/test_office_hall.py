"""Tests for the hall of doors, the warehouse, the navigation and the idle characters' plans."""
import unittest

from office import data, sprites
from office.demo import DemoSource
from office.hall import BACK, WAREHOUSE, doors_of
from office.model import Worker
from office.office import Office


def worker(wid, parent, state="done", in_cwd=True, index=1, group="g"):
    return Worker(id=wid, session_id="s", name="n", title=wid, item_label="1", group=group, index=index, cwd="/x",
                  started_ms=1.0, state=state, parent=parent, in_cwd=in_cwd, room_title=f"Sessao {parent}")


class CwdTests(unittest.TestCase):
    def test_record_counts_by_its_cwd_or_its_parent_cwd(self):
        self.assertTrue(data.record_in_cwd({"cwd": "/a/b/c"}, "/a/b"))
        self.assertTrue(data.record_in_cwd({"cwd": "/z", "parent_cwd": "/a/b"}, "/a/b"))
        self.assertFalse(data.record_in_cwd({"cwd": "/a/bc", "parent_cwd": "/z"}, "/a/b"))
        self.assertTrue(data.record_in_cwd({"cwd": "/z"}, None))


class DoorTests(unittest.TestCase):
    def test_one_door_per_parent_session_across_groups(self):
        doors = doors_of([worker("a", "p1", group="g1"), worker("b", "p1", group="g2"), worker("c", "p2")])
        self.assertEqual([(d.key, len(d.workers)) for d in doors], [("p1", 2), ("p2", 1)])

    def test_hall_shows_only_the_cwd_and_the_warehouse_shows_everything(self):
        office = Office(200, 60)
        office.set_workers([worker("a", "here"), worker("b", "there", in_cwd=False)])
        self.assertEqual(office.hall.entry_keys(), ["here", WAREHOUSE])
        self.assertEqual(office.warehouse.entry_keys(), ["here", "there", BACK])

    def test_selection_starts_on_the_newest_door_even_when_the_list_starts_empty(self):
        office = Office(200, 60)
        office.set_workers([worker("a", "here")])
        self.assertEqual(office.hall.selected_key, "here")


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.office = Office(200, 60)
        self.office.set_workers([worker("a", "here"), worker("b", "there", in_cwd=False)])

    def test_door_room_and_back(self):
        self.assertIsNone(self.office.press())
        self.assertEqual(self.office.mode, "room")
        self.assertEqual(self.office.press().id, "a")
        self.office.back()
        self.assertEqual(self.office.mode, "hall")

    def test_warehouse_and_back_returns_to_where_the_door_was_opened(self):
        self.office.toggle_warehouse()
        self.office.select(1)
        self.office.press()
        self.assertEqual(self.office.scene.selected().id, "b")
        self.office.back()
        self.assertEqual(self.office.mode, "warehouse")
        self.office.back()
        self.assertEqual(self.office.mode, "hall")

    def test_click_on_a_door_enters_it(self):
        x, y = self.office.hall.cell_xy(0)
        self.office.click(x + 5, (y + 10) // 2)
        self.assertEqual(self.office.mode, "room")

    def test_room_is_left_when_its_session_disappears(self):
        self.office.press()
        self.office.set_workers([worker("b", "there", in_cwd=False)])
        self.assertEqual(self.office.mode, "hall")


class LifeTests(unittest.TestCase):
    def test_hands_up_poses_are_gone(self):
        self.assertNotIn("raise", sprites.POSES)
        self.assertNotIn("stretch", sprites.POSES)

    def test_idle_characters_leave_and_come_back_while_busy_ones_stay(self):
        office = Office(200, 60)
        office.set_workers([worker("idle", "p"), worker("busy", "p", state="working", index=2)])
        idle, busy = office.scene.actors["idle"], office.scene.actors["busy"]
        kinds, seen_out, seen_back = set(), False, False
        for _ in range(3000):
            office.step()
            kinds.add(idle.life.kind)
            seen_out = seen_out or idle.away
            seen_back = seen_back or (seen_out and not idle.away)
            self.assertEqual(busy.life.kind, "work")
            self.assertFalse(busy.away)
        self.assertIn("out", kinds)
        self.assertTrue(seen_out and seen_back)

    def test_a_character_that_returns_to_work_comes_back_at_once(self):
        office = Office(200, 60)
        item = worker("idle", "p")
        office.set_workers([item])
        actor = office.scene.actors["idle"]
        while not actor.away:
            office.step()
        item.state = "working"
        office.set_workers([item])
        office.mode = "warehouse"
        office.step()
        self.assertFalse(actor.away)

    def test_every_view_survives_a_long_run_with_navigation(self):
        for size in ((200, 60), (120, 40), (80, 30), (30, 10)):
            office = Office(*size)
            office.set_workers(DemoSource().snapshot())
            for tick in range(2500):
                if tick % 400 == 0:
                    office.press()
                if tick % 400 == 200:
                    office.back()
                if tick % 700 == 650:
                    office.toggle_warehouse()
                office.step()
                office.render()


if __name__ == "__main__":
    unittest.main()
