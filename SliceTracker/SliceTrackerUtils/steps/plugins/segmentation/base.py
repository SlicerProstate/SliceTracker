import vtk
from ...base import SliceTrackerPlugin


class SliceTrackerSegmentationPluginBase(SliceTrackerPlugin):

  SegmentationStartedEvent = vtk.vtkCommand.UserEvent + 435
  SegmentationFinishedEvent = vtk.vtkCommand.UserEvent + 436
  SegmentationFailedEvent = vtk.vtkCommand.UserEvent + 437

  def __init__(self):
    super(SliceTrackerSegmentationPluginBase, self).__init__()
    self.reset()

  def reset(self):
    self.startTime = None
    self.endTime = None

  def startSegmentation(self):
    raise NotImplementedError

  def _onSegmentationStarted(self, caller, event):
    self.reset()
    self.startTime = self.getTime()
    self.invokeEvent(self.SegmentationStartedEvent)

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def _onSegmentationFinished(self, caller, event, labelNode):
    self.endTime = self.getTime()
    self.invokeEvent(self.SegmentationFinishedEvent, labelNode)

  def _onSegmentationFailed(self, caller, event):
    self.reset()
    self.invokeEvent(self.SegmentationFailedEvent)
