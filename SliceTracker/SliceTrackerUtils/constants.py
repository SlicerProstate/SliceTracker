import slicer
from SlicerDevelopmentToolboxUtils.mixins import ModuleWidgetMixin as helper

class SliceTrackerConstants(object):

  MODULE_NAME = "SliceTracker"

  PREOP_SAMPLE_DATA_URL = 'https://github.com/SlicerProstate/SliceTracker/releases/download/test-data/Preop-deid.zip'
  INTRAOP_SAMPLE_DATA_URL = 'https://github.com/SlicerProstate/SliceTracker/releases/download/test-data/Intraop-deid.zip'

  JSON_FILENAME = "results.json"

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
  LAYOUT_FOUR_UP_QUANTITATIVE = slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpPlotView
  LAYOUT_SIDE_BY_SIDE = slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView
  ALLOWED_LAYOUTS = [LAYOUT_SIDE_BY_SIDE, LAYOUT_FOUR_UP, LAYOUT_RED_SLICE_ONLY, LAYOUT_FOUR_UP_QUANTITATIVE]

  PLANNING_IMAGE = "PLANNING IMAGE"
  COVER_PROSTATE = "COVER PROSTATE"
  COVER_TEMPLATE = "COVER TEMPLATE"
  GUIDANCE_IMAGE = "GUIDANCE"
  VIBE_IMAGE = "VIBE"
  OTHER_IMAGE = "OTHER"

  TRACKABLE_IMAGE_TYPES = [COVER_PROSTATE, COVER_TEMPLATE, GUIDANCE_IMAGE]

  ZFrame_INSTRUCTION_STEPS = {1: "Scroll and click into ZFrame center to set ROI center",
                              2: "Click outside of upper right ZFrame corner to set ROI border"}

  IntraopSeriesSelectorToolTip = """
  <html>
    <head>
      <style type="text/css"> </style>
    </head>
    <body style="font-family:'Lucida Grande',sans-serif; font-size: 12pt; font-weight: 400; font-style: normal;border: 1px solid black;margin-top:0px;">
      <table cellspacing=5>
        <tbody>
          <tr>
            <td>
              <img src="%s">
            </td>
            <td style="vertical-align: middle">
              <strong>tracked</strong>(registration result available)
            </td>
          </tr>
          <tr>
            <td>
              <img src="%s">
            </td>
            <td style="vertical-align: middle">
              <strong>untracked</strong>(no registration result available)
            </td>
          </tr>
          <tr>
            <td>
              <img src="%s">
            </td>
            <td style="vertical-align: middle">
              <strong>skipped</strong>(no registration result available)
            </td>
          </tr>
          <tr>
            <td style="vertical-align: middle">
              <img src="%s">
            </td>
            <td>
              <strong>rejected</strong>(non satisfactory/approved registration result available)
            </td>
          </tr>
        </tbody>
      </table>
    </body>
  </html>
  """ % (helper.createAndGetRawColoredPixelMap("green"), helper.createAndGetRawColoredPixelMap("yellow"),
         helper.createAndGetRawColoredPixelMap("red"), helper.createAndGetRawColoredPixelMap("grey"))