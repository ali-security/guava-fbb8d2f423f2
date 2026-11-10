#!/bin/bash
# Poll this job's public Travis log until the test summary printed by
# util/print_skipped_tests.py has been archived. Runs as after_script, so it
# cannot change the build result. Prints a heartbeat on every poll to avoid
# Travis's 10-minute no-output kill.
URL="https://api.travis-ci.com/v3/job/${TRAVIS_JOB_ID}/log.txt"
MARK='SUMMARY TOTAL ('
waited=0
while [ "$waited" -lt 900 ]; do
  if curl -fsSL "$URL" 2>/dev/null | grep -qF "$MARK"; then
    echo "log archived after ${waited}s"
    exit 0
  fi
  echo "waiting for log archive... (${waited}s)"
  sleep 20
  waited=$((waited + 20))
done
echo "gave up waiting after ${waited}s"
exit 0
