"""
Constructive proof that scheduler_feasible_test.db is actually solvable:
build an explicit valid timetable by hand (simple greedy placement), honoring
every hard constraint solver.py enforces:
  - teacher no-overlap
  - room no-overlap
  - student no-overlap (for every enrolled student)
  - room capacity + room_type (requires_lab) compatibility
  - period + duration <= slots_per_day (no crossing day boundary)
  - lectures of the same course land on distinct days (prevent_same_day)

If this succeeds, an explicit satisfying assignment exists -> the dataset is
provably feasible, independent of CP-SAT. If solver.py still reports
INFEASIBLE on this same data, that is proof of a remaining code bug, not a
data problem.
"""

import sqlite3
from collections import defaultdict

conn = sqlite3.connect("scheduler.db")
conn.row_factory = sqlite3.Row

cfg = dict(conn.execute("SELECT * FROM solver_config WHERE id=1").fetchone())
spd, dpw = cfg["slots_per_day"], cfg["days_per_week"]

courses = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM courses")}
rooms = [dict(r) for r in conn.execute("SELECT * FROM rooms")]
tas = {r["course_id"]: r["teacher_id"] for r in conn.execute("SELECT * FROM teacher_assignments")}
enrollment = defaultdict(list)
for r in conn.execute("SELECT * FROM enrollment"):
    enrollment[r["course_id"]].append(r["student_id"])

def compatible_rooms(course):
    return [r for r in rooms if r["capacity"] >= course["students_per_lecture"]
            and (not course["requires_lab"] or r["room_type"] in ("Laboratory", "Computer Lab"))]

# occupancy trackers: (day, period) -> busy, per teacher/room/student
teacher_busy = defaultdict(set)   # teacher_id -> set of (day, period)
room_busy = defaultdict(set)      # room_id -> set of (day, period)
student_busy = defaultdict(set)   # student_id -> set of (day, period)
course_days_used = defaultdict(set)  # course_id -> set of days already used

placements = []
lectures = []
for cid, c in courses.items():
    for ln in range(c["lectures_per_week"]):
        lectures.append((cid, ln))

failed = []
for cid, ln in lectures:
    c = courses[cid]
    dur = c["duration"]
    teacher_id = tas[cid]
    comp_rooms = compatible_rooms(c)
    students = enrollment.get(cid, [])
    placed = False

    for day in range(1, dpw + 1):
        if day in course_days_used[cid]:
            continue  # same-day constraint: one lecture of this course per day
        for period in range(1, spd - dur + 2):
            slots = [(day, period + k) for k in range(dur)]
            if any(s in teacher_busy[teacher_id] for s in slots):
                continue
            if any(any(s in student_busy[sid] for s in slots) for sid in students):
                continue
            for room in comp_rooms:
                if any(s in room_busy[room["id"]] for s in slots):
                    continue
                # place it
                for s in slots:
                    teacher_busy[teacher_id].add(s)
                    room_busy[room["id"]].add(s)
                    for sid in students:
                        student_busy[sid].add(s)
                course_days_used[cid].add(day)
                placements.append((cid, ln, teacher_id, room["id"], day, period, dur))
                placed = True
                break
            if placed:
                break
        if placed:
            break
    if not placed:
        failed.append((cid, ln))

print(f"Total lectures to place: {len(lectures)}")
print(f"Successfully placed (constructive proof of feasibility): {len(placements)}")
print(f"Failed to place: {len(failed)}")
if failed:
    print("FAILED lectures:", failed)
else:
    print("\nRESULT: A valid schedule was constructed by hand.")
    print("This dataset is PROVABLY FEASIBLE, independent of CP-SAT.")
    print("\nSample of constructed schedule (course_id, lecture#, teacher_id, room_id, day, period, duration):")
    for p in placements[:10]:
        print(" ", p)

# Independent re-verification pass: re-check the constructed schedule from
# scratch for any conflict, to make sure the greedy placement above didn't
# silently violate anything.
conflicts = []
occ_teacher = defaultdict(list)
occ_room = defaultdict(list)
occ_student = defaultdict(list)
for cid, ln, tid, rid, day, period, dur in placements:
    for k in range(dur):
        slot = (day, period + k)
        occ_teacher[tid].append((slot, cid, ln))
        occ_room[rid].append((slot, cid, ln))
        for sid in enrollment.get(cid, []):
            occ_student[sid].append((slot, cid, ln))

for label, occ in [("teacher", occ_teacher), ("room", occ_room), ("student", occ_student)]:
    for eid, entries in occ.items():
        seen = {}
        for slot, cid, ln in entries:
            if slot in seen and seen[slot] != (cid, ln):
                conflicts.append((label, eid, slot, seen[slot], (cid, ln)))
            seen[slot] = (cid, ln)

print(f"\nIndependent conflict re-check: {len(conflicts)} conflicts found "
      f"({'CLEAN' if not conflicts else 'PROBLEM'})")
