"""Tests for the hall of doors, the warehouse, the navigation and the idle characters' plans."""
import unittest

from office import data, hallart, sprites
from office.demo import DemoSource
from office.hall import BACK, WAREHOUSE, doors_of
from office.model import Worker
from office.hallart import BAY_H, BAY_W, CAP, WINDOW, draw_side_walls, shade
from office.hallplan import SLOPE
from office.props import OUTLINE
from office.hallplan import BACK_Y, DROP, TABLE_TOP, Plan
from office.office import Office
from office.paths import Grid, desk_blocks
from office.scene import Scene


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


class RouteTests(unittest.TestCase):
    def test_route_goes_around_an_obstacle(self):
        grid = Grid(120, 60, lambda x, y: 40 <= x <= 60 and y <= 44)
        path = grid.route((20, 8), (100, 8))
        self.assertEqual(path[-1], (100, 8))
        self.assertTrue(any(y > 44 for _, y in path))

    def test_route_falls_back_to_the_goal_when_walled_off(self):
        grid = Grid(120, 60, lambda x, y: 40 <= x <= 60)
        self.assertEqual(grid.route((4, 8), (100, 8)), [(100, 8)])

    def test_nearest_free_leaves_an_obstacle(self):
        grid = Grid(120, 60, lambda x, y: x < 40)
        self.assertTrue(grid.is_free(grid.nearest_free((8, 8))))

    def test_waiter_never_crosses_a_desk_on_its_way(self):
        scene = Scene(200, 60)
        make = lambda i, state, after=(): Worker(id=f"w{i}", session_id="s", name="n", title="t", item_label=str(i), group="g",
                                                 index=i, cwd="", started_ms=i, state=state, after=list(after))
        scene.set_workers([make(1, "working"), make(2, "done"), make(3, "waiting", [1])])
        scene.step()
        walker = scene.actors["w3"]
        desks = [a.desk for a in scene.actors.values() if a is not walker]
        for _ in range(200):
            scene.step()
            for desk in desks:
                near_goal = max(abs(walker.foot[0] - walker.goal[0]), abs(walker.foot[1] - walker.goal[1])) <= 12
                near_start = max(abs(walker.foot[0] - walker.stand_point[0]), abs(walker.foot[1] - walker.stand_point[1])) <= 12
                self.assertFalse(desk_blocks(desk, *walker.foot) and not near_goal and not near_start, walker.foot)


class PlanTests(unittest.TestCase):
    def test_wide_screens_put_rooms_on_both_walls_and_small_ones_keep_the_list(self):
        wide = Plan(200, 60, True)
        self.assertTrue(wide.wide)
        self.assertEqual(len(wide.panels), 4)
        self.assertLess(wide.panels[0].x, wide.table[0])
        self.assertGreater(wide.panels[1].x, wide.table[0])
        self.assertFalse(Plan(150, 44, True).wide)
        self.assertIsNotNone(Plan(150, 44, True).table)

    def test_floor_edge_is_flat_under_the_table_and_falls_to_both_edges(self):
        plan = Plan(200, 60, True)
        cx = plan.cols // 2
        self.assertEqual(plan.floor_edge(cx), BACK_Y)
        self.assertEqual(plan.floor_edge(cx - 10), plan.floor_edge(cx + 9))
        self.assertGreater(plan.floor_edge(0), plan.floor_edge(cx - 40))
        for x in range(plan.cols):
            self.assertEqual(plan.floor_edge(x), plan.floor_edge(plan.cols - 1 - x))
        tx, ty = plan.table
        mid = tx + 30
        self.assertGreaterEqual(plan.floor_edge(mid), ty + 17)
        self.assertLessEqual(plan.floor_edge(mid), ty + 18)

    def test_wide_plans_keep_panels_in_view_and_doors_reachable(self):
        for cols, rows in [(188, 46), (200, 60), (230, 60), (276, 70)]:
            with self.subTest(cols=cols, rows=rows):
                plan = Plan(cols, rows, True)
                self.assertTrue(plan.wide)
                self.assertGreaterEqual(len(plan.panels), 2)
                for panel in plan.panels:
                    self.assertGreaterEqual(panel.x, 0)
                    self.assertLessEqual(panel.x + BAY_W, cols)
                    self.assertGreaterEqual(panel.y, 0)
                    self.assertLessEqual(panel.y + DROP + BAY_H, plan.height)
                grid = plan.grid()
                for panel in plan.panels:
                    route = grid.route(grid.nearest_free(panel.door), grid.nearest_free(plan.spots()[0]))
                    self.assertGreater(len(route), 1, panel.door)
        self.assertFalse(Plan(170, 46, True).wide)

    def test_lane_behind_a_lower_office_is_blocked_on_both_sides(self):
        for cols, rows in [(200, 60), (276, 70)]:
            with self.subTest(cols=cols, rows=rows):
                plan = Plan(cols, rows, True)
                free = [panel for panel in plan.panels if panel.free]
                self.assertTrue(any(panel.slope > 0 for panel in free))
                self.assertTrue(any(panel.slope < 0 for panel in free))
                for panel in free:
                    inner = panel.x if panel.slope > 0 else panel.x + BAY_W - 1
                    self.assertTrue(plan.blocks(inner, plan.floor_edge(inner) + 4), panel)

    def test_partition_closes_the_gap_behind_a_lower_office(self):
        for cols, rows in [(200, 60), (276, 70)]:
            with self.subTest(cols=cols, rows=rows):
                plan = Plan(cols, rows, True)
                canvas = sprites.Canvas(plan.cols, plan.height)
                draw_side_walls(canvas, plan)
                for panel in plan.panels:
                    if not panel.free:
                        continue
                    inner = panel.x if panel.slope > 0 else panel.x + BAY_W - 1
                    step = 1 if panel.slope > 0 else -1
                    x = inner + 10 * step
                    if not 0 <= x < canvas.width:
                        continue
                    self.assertEqual(canvas.rows[panel.y - 3 - 10 // 3][x], OUTLINE, panel)

    def test_warehouse_stays_on_the_table_on_every_page(self):
        office = Office(200, 60)
        office.set_workers([worker(f"a{i}", f"p{i}") for i in range(9)])
        hall = office.hall
        self.assertGreater(hall.pages(), 1)
        tx, ty = hall.plan.table
        for _ in range(9):
            self.assertNotIn(WAREHOUSE, hall.visible_keys())
            self.assertEqual(hall.key_at(tx + 3, (ty + 8) // 2), WAREHOUSE)
            hall.select(1)
        self.assertEqual(hall.selected_key, WAREHOUSE)
        self.assertEqual(hall.page(), hall.pages() - 1)

    def test_warehouse_label_sits_on_top_of_the_parcel(self):
        office = Office(200, 60)
        office.set_workers([worker("a0", "p0")])
        hall = office.hall
        tx, ty = hall.plan.table
        frame = hall.render()
        row = (ty + 7) // 2 - 1
        text = "".join(cell[0] for cell in frame.cells[row])
        label = "Todas as sessões"
        self.assertIn(label, text)
        self.assertEqual(text.index(label), tx + 7 - len(label) // 2)
        self.assertIn(ty + 7, range(2 * (row + 1), 2 * (row + 1) + 2))

    def test_partition_stays_in_front_of_earlier_panels_but_not_their_windows(self):
        wall = (168, 186, 216)
        wall_tones = {shade(wall, 0.82), shade(wall, 0.98)}
        tones = wall_tones | {OUTLINE}
        for cols, rows in [(200, 60), (276, 70)]:
            count = len(Plan(cols, rows, True).panels)
            for workers in (count, 1):
                with self.subTest(cols=cols, rows=rows, workers=workers):
                    office = Office(cols, rows)
                    office.set_workers([worker(f"a{i}", f"p{i}") for i in range(workers)])
                    hall = office.hall
                    floor = hall._background()
                    covered = 0
                    for j, owner in enumerate(hall.plan.panels):
                        if not owner.free:
                            continue
                        inner = owner.x if owner.slope > 0 else owner.x + BAY_W - 1
                        step = 1 if owner.slope > 0 else -1
                        for panel in hall.plan.panels[:j]:
                            if panel.slope == 0:
                                continue
                            for col in range(BAY_W):
                                x = panel.x + col
                                if (x - inner) * step < 0:
                                    continue
                                drop = abs(x - inner) // SLOPE
                                top = owner.y - CAP - drop
                                bottom = owner.y - CAP + drop + 1
                                last = panel.y + panel.shift(col) + BAY_H - 1
                                window = panel.y + panel.shift(col) + WINDOW[1] + 1
                                if not top < last <= bottom:
                                    continue
                                covered += 1
                                self.assertIn(floor.rows[last][x], tones)
                                self.assertNotIn(floor.rows[window][x], wall_tones)
                    self.assertGreater(covered, 0)

    def test_nobody_stops_on_the_table_in_the_hall(self):
        office = Office(188, 46)
        office.set_workers([worker(f"a{i}", f"p{i}") for i in range(3)])
        table = office.hall.plan
        for _ in range(1500):
            office.step()
            office.render()
            for actor in office.scene.actors.values():
                if actor.hall_foot is not None and not actor.moving:
                    self.assertFalse(table.blocks(*actor.hall_foot), actor.hall_foot)


class LifeTests(unittest.TestCase):
    def test_hands_up_poses_are_gone(self):
        self.assertNotIn("raise", sprites.POSES)
        self.assertNotIn("stretch", sprites.POSES)

    def test_idle_characters_leave_once_and_stay_out_while_idle(self):
        office = Office(200, 60)
        office.set_workers([worker("idle", "p"), worker("busy", "p", state="working", index=2)])
        idle, busy = office.scene.actors["idle"], office.scene.actors["busy"]
        kinds, seen_out, seen_back = [], False, False
        for _ in range(3000):
            office.step()
            kinds.append(idle.life.kind)
            if seen_out:
                seen_back = seen_back or not idle.away
            seen_out = seen_out or idle.away
            self.assertEqual(busy.life.kind, "work")
            self.assertFalse(busy.away)
        self.assertLessEqual(set(kinds), {"work", "desk", "out"})
        settled = [kind for kind in kinds if kind != "work"]
        self.assertLessEqual(sum(1 for a, b in zip(settled, settled[1:]) if a != b), 1)
        self.assertFalse(seen_back)

    def test_a_character_that_returns_to_work_comes_back_at_once(self):
        office = Office(200, 60)
        item = worker("idle", "p")
        office.set_workers([item])
        actor = office.scene.actors["idle"]
        actor.life.kind, actor.life.decided = "out", True
        for _ in range(500):
            office.step()
            if actor.away:
                break
        self.assertTrue(actor.away)
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


class ScrollHallTests(unittest.TestCase):
    def setUp(self):
        self.office = Office(200, 60)
        self.office.set_workers([worker(f"a{i}", f"p{i}") for i in range(9)])

    def check_scroll(self):
        hall = self.office.view()
        self.assertGreater(hall.pages(), 1)
        selected = hall.selected_key
        self.office.scroll(1)
        self.assertEqual(hall.page(), 1)
        self.assertEqual(hall.selected_key, selected)
        for _ in range(hall.pages() + 2):
            self.office.scroll(1)
        self.assertEqual(hall.page(), hall.pages() - 1)
        for _ in range(hall.pages() + 2):
            self.office.scroll(-1)
        self.assertEqual(hall.page(), 0)
        self.assertEqual(hall.selected_key, selected)

    def test_wheel_scrolls_the_hall(self):
        self.check_scroll()

    def test_wheel_scrolls_the_warehouse(self):
        self.office.toggle_warehouse()
        self.check_scroll()

    def test_arrow_after_scrolling_brings_the_view_to_the_selection(self):
        hall = self.office.view()
        self.office.scroll(1)
        self.office.select(1)
        self.assertEqual(hall.page(), hall.door_keys().index(hall.selected_key) // hall.page_size)

    def test_enter_off_page_only_brings_the_page_back(self):
        self.office.scroll(1)
        self.assertIsNone(self.office.press())
        self.assertEqual(self.office.mode, "hall")
        self.assertEqual(self.office.hall.page(), 0)


class WarehouseLabelTests(unittest.TestCase):
    def test_label_is_centered_on_the_parcel(self):
        from office.hall import PARCEL_CENTER, WAREHOUSE_LABEL, Hall
        hall = Hall(240, 68, False, "x")
        col, _ = hall._warehouse_label_at()
        middle = col + len(WAREHOUSE_LABEL) / 2
        self.assertLessEqual(abs(middle - (hall.plan.table[0] + PARCEL_CENTER)), 1)


if __name__ == "__main__":
    unittest.main()
