import ctk
import qt
import slicer



from SlicerDevelopmentToolboxUtils.events import SlicerDevelopmentToolboxEvents
from SlicerDevelopmentToolboxUtils.mixins import  ModuleWidgetMixin, ModuleLogicMixin
from SlicerDevelopmentToolboxUtils.icons import Icons



class SliceTrackerSegmentationValidatorPlugin(ModuleWidgetMixin):

  FinishedEvent = SlicerDevelopmentToolboxEvents.FinishedEvent
  CanceledEvent = SlicerDevelopmentToolboxEvents.CanceledEvent

  def __init__(self, inputVolume, labelNode):
    super(SliceTrackerSegmentationValidatorPlugin, self).__init__()
    self.inputVolume = inputVolume
    self.labelNode = labelNode
    self.segmentationModified = False
    self.observedSegmentation = None
    self.setup()

  def setup(self):
    self.validationWindow = qt.QDialog()
    self.validationWindow.setWindowTitle("Modify Segmentation")
    self.validationWindow.setWindowFlags(qt.Qt.WindowStaysOnTopHint)
    self.validationWindow.setLayout(qt.QGridLayout())

    self.segmentEditorWidget = slicer.qMRMLSegmentEditorWidget()
    self.segmentationNode = slicer.vtkMRMLSegmentationNode()
    slicer.mrmlScene.AddNode(self.segmentationNode)
    self.segmentationNode.CreateDefaultDisplayNodes()  # only needed for display
    self.segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(self.inputVolume)

    self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
    self.segmentEditorNode = slicer.vtkMRMLSegmentEditorNode()
    slicer.mrmlScene.AddNode(self.segmentEditorNode)
    self.segmentEditorWidget.setMRMLSegmentEditorNode(self.segmentEditorNode)
    self.segmentEditorWidget.hide()

    self.segmentEditorWidget.setSegmentationNodeSelectorVisible(False)
    self.segmentEditorWidget.setMasterVolumeNodeSelectorVisible(False)
    self.segmentEditorWidget.setSwitchToSegmentationsButtonVisible(False)
    self.segmentEditorWidget.findChild(slicer.qMRMLSegmentsTableView, "SegmentsTableView").hide()
    self.segmentEditorWidget.findChild(qt.QPushButton, "AddSegmentButton").hide()
    self.segmentEditorWidget.findChild(qt.QPushButton, "RemoveSegmentButton").hide()
    self.segmentEditorWidget.findChild(ctk.ctkMenuButton, "Show3DButton").hide()

    widget = slicer.app.layoutManager().sliceWidget("Red")
    #self.segmentEditorWidget.setFixedWidth(self.segmentEditorWidget.minimumSizeHint.width())
    if not widget:
      raise AttributeError("Slice widget with name %s not found" % self.widgetName)
    sliceNode = widget.sliceLogic().GetSliceNode()
    sliceNode.SetOrientationToAxial()
    sliceNode.RotateToVolumePlane(self.inputVolume)

    sliceLogic = widget.sliceLogic()
    sliceLogic.FitSliceToAll()
    FOV = sliceLogic.GetSliceNode().GetFieldOfView()
    self.setFOV(sliceLogic, FOV)

    self.sliceWidget = slicer.qMRMLSliceWidget()
    #self.sliceWidget.resize(1025, 723)
    self.sliceWidget.setMRMLScene(widget.mrmlScene())
    self.sliceWidget.setMRMLSliceNode(sliceNode)
    self.sliceWidget.resize(1025, 723)

    iconSize = qt.QSize(36, 36)

    self.modifySegmentButton = self.createButton("Modify Segmentation", icon=slicer.modules.segmenteditor.icon, iconSize=iconSize)
    self.confirmSegmentButton = self.createButton("Confirm Segmentation", icon=Icons.apply, iconSize=iconSize)
    self.cancelButton = self.createButton("Cancel", icon=Icons.cancel, iconSize=iconSize)

    buttonLayout = self.createHLayout([self.modifySegmentButton,self.confirmSegmentButton,self.cancelButton])

    self.validationWindow.layout().addWidget(self.segmentEditorWidget, 0, 0)
    self.validationWindow.layout().addWidget(self.sliceWidget, 0, 1)
    self.validationWindow.layout().addWidget(buttonLayout, 1, 1)

    self.modifySegmentButton.connect('clicked()', self.onModifySegmentButtonClicked)
    self.confirmSegmentButton.connect('clicked()', self.onConfirmSegmentButtonClicked)
    self.cancelButton.connect('clicked()', self.onCancelButtonClicked)

  def run(self):
    self.segmentationModified = False
    prompt = self.validationWindow.exec_()
    if prompt == qt.QDialog.Rejected:
      self.invokeEvent(self.CanceledEvent)

  def onModifySegmentButtonClicked(self):
    slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(self.labelNode, self.segmentationNode)
    segmentID = self.segmentationNode.GetSegmentation().GetNthSegment(0).GetName()
    segmentationDisplayNode = self.segmentationNode.GetDisplayNode()
    segmentationDisplayNode.SetSegmentVisibility2DFill(segmentID, False)
    self.segmentEditorWidget.setSegmentationNode(self.segmentationNode)
    self.segmentEditorWidget.setMasterVolumeNode(self.inputVolume)
    self.addSegmentationObserver(self.segmentationNode)
    self.segmentEditorWidget.show()
    self.modifySegmentButton.hide()

  def onConfirmSegmentButtonClicked(self):
    if self.segmentationModified is True:
      slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(self.segmentationNode, self.labelNode)
      ModuleLogicMixin.runBRAINSResample(inputVolume=self.labelNode, referenceVolume=self.inputVolume,
                           outputVolume=self.labelNode)
    self.cleanup()
    self.validationWindow.accept()
    self.invokeEvent(self.FinishedEvent, self.labelNode)

  def onCancelButtonClicked(self):
    self.validationWindow.close()
    self.cleanup()
    #self.invokeEvent(self.CanceledEvent)

  def addSegmentationObserver(self, segmentation):
    import vtkSegmentationCorePython as vtkSegmentationCore
    self.observedSegmentation = segmentation
    self.segmentObserver = self.observedSegmentation.AddObserver(
      vtkSegmentationCore.vtkSegmentation.RepresentationModified,
      self.onSegmentModified)

  def removeSegmentationObserver(self):
    if self.observedSegmentation:
      self.observedSegmentation.RemoveObserver(self.segmentObserver)
      self.segmentObserver = None

  def onSegmentModified(self, caller, event):
    self.segmentationModified = True

  def cleanup(self):
    self.removeSegmentationObserver()
    if self.observedSegmentation:
      slicer.mrmlScene.RemoveNode(self.segmentationNode)
      slicer.mrmlScene.RemoveNode(self.segmentEditorNode)
