#!/usr/bin/env bash
SLICER="/Applications/Slicer.app/Contents/MacOS/Slicer"

$SLICER --python-code "from SliceTracker import SliceTrackerSlicelet; slicelet=SliceTrackerSlicelet();" --no-splash --no-main-window