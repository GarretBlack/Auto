import sys

from clicer import main as automation_main
from gui import main as gui_main


if "--run-automation" in sys.argv:
    sys.argv = [arg for arg in sys.argv if arg != "--run-automation"]
    raise SystemExit(automation_main())

raise SystemExit(gui_main())
