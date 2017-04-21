#!/usr/bin/env bash
SLICER="/home/parallels/sources/cpp/Slicer/Build/Slicer-build/Slicer"

$SLICER --python-code "from SliceTracker import SliceTrackerSlicelet; slicelet=SliceTrackerSlicelet();" --no-splash --no-main-window