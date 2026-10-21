"""Keep tests away from the real cache, budget ledger, results and logs."""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="cube-race-tests-")
for var, sub in (("DATA_DIR", "data"), ("RESULTS_DIR", "results"), ("LOG_DIR", "logs")):
    os.environ[var] = os.path.join(_tmp, sub)
os.environ["PROVIDER"] = "mock"
os.environ["OPENROUTER_API_KEY"] = ""
