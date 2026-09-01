from debugger.utils import *

banner()

logger.info("Testing logger")
logger.success("Everything works")
logger.warning("This is a warning")
logger.error("This is an error")

counter = Counter()
counter.add("Variables", 120)
counter.add("Constraints", 340)

section("Statistics")
counter.dump()

report = Report()
report.heading("Scheduler Audit")
report.add("Hello World")
report.save("test_report.txt")