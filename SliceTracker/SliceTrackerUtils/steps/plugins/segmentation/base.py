import vtk
from ...base import SliceTrackerPlugin


class SliceTrackerSegmentationPluginBase(SliceTrackerPlugin):

  SegmentationStartedEvent = vtk.vtkCommand.UserEvent + 435
  SegmentationFinishedEvent = vtk.vtkCommand.UserEvent + 436

  def __init__(self):
    super(SliceTrackerSegmentationPluginBase, self).__init__()

  def startSegmentation(self):
    raise NotImplementedError

  def _onSegmentationStarted(self, caller, event):
    self.invokeEvent(self.SegmentationStartedEvent)

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def _onSegmentationFinished(self, caller, event, labelNode):
    self.invokeEvent(self.SegmentationFinishedEvent, labelNode)
