import slicer


class SliceTrackerConstants(object):

  PREOP_SAMPLE_DATA_URL = 'https://github.com/SlicerProstate/SliceTracker/releases/download/test-data/Preop-deid.zip'
  INTRAOP_SAMPLE_DATA_URL = 'https://github.com/SlicerProstate/SliceTracker/releases/download/test-data/Intraop-deid.zip'

  STEP_OVERVIEW = "Overview"
  STEP_ZFRAME_REGISTRATION = "OpenSourceZFrameRegistration"
  STEP_SEGMENTATION = "Segmentation"
  STEP_TARGETING = "Targeting"
  STEP_SEGMENTATION_COMPARISON = "SegmentationComparison"
  STEP_EVALUATION = "Evaluation"

  JSON_FILENAME = "results.json"

  SLICETRACKER_STEPS = [STEP_OVERVIEW, STEP_ZFRAME_REGISTRATION, STEP_SEGMENTATION, STEP_TARGETING,
                        STEP_SEGMENTATION_COMPARISON, STEP_EVALUATION]

  MISSING_PREOP_ANNOTATION_TEXT = "No preop data available"
  LEFT_VIEWER_SLICE_ANNOTATION_TEXT = 'BIOPSY PLAN'
  RIGHT_VIEWER_SLICE_ANNOTATION_TEXT = 'TRACKED TARGETS'
  RIGHT_VIEWER_SLICE_TRANSFORMED_ANNOTATION_TEXT = 'OLD'
  RIGHT_VIEWER_SLICE_NEEDLE_IMAGE_ANNOTATION_TEXT = 'NEW'
  APPROVED_RESULT_TEXT_ANNOTATION = "approved"
  REJECTED_RESULT_TEXT_ANNOTATION = "rejected"
  SKIPPED_RESULT_TEXT_ANNOTATION = "skipped"

  LAYOUT_RED_SLICE_ONLY = slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView
  LAYOUT_FOUR_UP = slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView
  LAYOUT_SIDE_BY_SIDE = slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView
  ALLOWED_LAYOUTS = [LAYOUT_SIDE_BY_SIDE, LAYOUT_FOUR_UP, LAYOUT_RED_SLICE_ONLY]

  COVER_PROSTATE = "COVER PROSTATE"
  COVER_TEMPLATE = "COVER TEMPLATE"
  GUIDANCE_IMAGE = "GUIDANCE"

  TRACKABLE_IMAGE_TYPES = [COVER_PROSTATE, COVER_TEMPLATE, GUIDANCE_IMAGE]

  ZFrame_INSTRUCTION_STEPS = {1: "Scroll and click into ZFrame center to set ROI center",
                              2: "Click outside of upper right ZFrame corner to set ROI border"}