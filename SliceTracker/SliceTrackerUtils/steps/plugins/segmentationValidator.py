import ctk
import qt
import slicer
import logging

from SlicerDevelopmentToolboxUtils.events import SlicerDevelopmentToolboxEvents
from SlicerDevelopmentToolboxUtils.mixins import  ModuleWidgetMixin, ModuleLogicMixin
from SlicerDevelopmentToolboxUtils.icons import Icons
from SlicerDevelopmentToolboxUtils.decorators import logmethod


class SliceTrackerSegmentationValidatorPlugin(qt.QDialog, ModuleWidgetMixin):

  ModifiedEvent = SlicerDevelopmentToolboxEvents.StatusChangedEvent
  FinishedEvent = SlicerDevelopmentToolboxEvents.FinishedEvent
  CanceledEvent = SlicerDevelopmentToolboxEvents.CanceledEvent

  def __init__(self, inputVolume, labelNode):
    qt.QDialog.__init__(self)
    self.className = self.__class__.__name__
    self.setWindowTitle("Validate Segmentation")
    self.setWindowFlags(qt.Qt.WindowStaysOnTopHint)
    self.volumeNode = inputVolume
    self.labelNode = labelNode
    self._initializeMembers()
    self.setup()

  def _initializeMembers(self):
    self.segmentationModified = False
    self.observedSegmentation = None

  def setup(self):
    self.setLayout(qt.QGridLayout())
    self.setupSliceWidget()

    iconSize = qt.QSize(36, 36)
    self.modifySegmentButton = self.createButton("Modify Segmentation", icon=slicer.modules.segmenteditor.icon,
                                                 iconSize=iconSize)
    self.confirmSegmentButton = self.createButton("Confirm Segmentation", icon=Icons.apply, iconSize=iconSize)
    self.cancelButton = self.createButton("Cancel", icon=Icons.cancel, iconSize=iconSize)

    self.setupSegmentEditor()
    self.layout().addWidget(self.segmentEditorWidget, 0, 0, 2, 1)
    self.layout().addWidget(self.sliceWidget, 0, 1)
    self.layout().addWidget(self.createHLayout([self.modifySegmentButton,self.confirmSegmentButton,self.cancelButton]),
                            1, 1)
    self.setupConnections()

  def setupConnections(self):
    self.modifySegmentButton.clicked.connect(self.onModifySegmentButtonClicked)
    self.confirmSegmentButton.clicked.connect(self.onConfirmSegmentButtonClicked)
    self.cancelButton.clicked.connect(lambda pushed: self.close())

  def setupSliceWidget(self):
    self.sliceNode = slicer.mrmlScene.CreateNodeByClass('vtkMRMLSliceNode')
    self.sliceNode.SetName("Black")
    self.sliceNode.SetLayoutName("Black")
    self.sliceNode.SetLayoutLabel("BL")
    self.sliceNode.SetOrientationToAxial()
    slicer.mrmlScene.AddNode(self.sliceNode)
    self.sliceWidget = self.layoutManager.viewWidget(self.sliceNode)

    self.sliceLogic = slicer.app.applicationLogic().GetSliceLogic(self.sliceNode)
    self.sliceNode.SetMappedInLayout(1)

  def setupSegmentEditor(self):
    self.segmentEditorWidget = slicer.qMRMLSegmentEditorWidget()
    self.segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
    self.segmentEditorWidget.visible = False
    self.segmentEditorWidget.setSegmentationNodeSelectorVisible(False)
    self.segmentEditorWidget.setMasterVolumeNodeSelectorVisible(False)
    self.segmentEditorWidget.setSwitchToSegmentationsButtonVisible(False)
    self.segmentEditorWidget.findChild(qt.QPushButton, "AddSegmentButton").hide()
    self.segmentEditorWidget.findChild(qt.QPushButton, "RemoveSegmentButton").hide()
    self.segmentEditorWidget.findChild(ctk.ctkMenuButton, "Show3DButton").hide()
    self.segmentEditorWidget.findChild(ctk.ctkExpandableWidget, "SegmentsTableResizableFrame").hide()
    self.segmentEditorWidget.setSizePolicy(qt.QSizePolicy.Maximum, qt.QSizePolicy.Expanding)

  def _initializeSegmentationNode(self):
    self.segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
    self.segmentationNode.CreateDefaultDisplayNodes()
    self.segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(self.volumeNode)

  def _initializeSegmentEditorNode(self):
    self.segmentEditorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")
    self.segmentEditorWidget.setMRMLSegmentEditorNode(self.segmentEditorNode)

  @logmethod(logging.DEBUG)
  def run(self):
    self.segmentationModified = False
    self._initializeSegmentationNode()
    self._initializeSegmentEditorNode()

    self.sliceNode.SetMappedInLayout(1)
    self.sliceLogic.GetSliceCompositeNode().SetBackgroundVolumeID(self.volumeNode.GetID())
    self.sliceLogic.GetSliceCompositeNode().SetLabelVolumeID(self.labelNode.GetID())
    self.sliceLogic.FitSliceToAll()
    self.sliceNode.RotateToVolumePlane(self.volumeNode)
    self.sliceNode.SetUseLabelOutline(True)
    self.resize(int(slicer.util.mainWindow().width/3*2), int(slicer.util.mainWindow().height/3*2))
    result = self.exec_()
    if result == qt.QDialog.Rejected:
      logging.debug("{}: Dialog got rejected.".format(self.className))
      self.invokeEvent(self.CanceledEvent)
    elif result == qt.QDialog.Accepted:
      logging.debug("{}: Dialog got approved.".format(self.className))
      self.invokeEvent(self.FinishedEvent, self.labelNode)
    self.cleanup()

  def onModifySegmentButtonClicked(self):
    self.invokeEvent(self.ModifiedEvent)
    slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(self.labelNode, self.segmentationNode)
    segmentID = self.segmentationNode.GetSegmentation().GetNthSegment(0).GetName()
    segmentationDisplayNode = self.segmentationNode.GetDisplayNode()
    segmentationDisplayNode.SetSegmentVisibility2DFill(segmentID, False)
    self.segmentEditorWidget.setSegmentationNode(self.segmentationNode)
    self.segmentEditorWidget.setMasterVolumeNode(self.volumeNode)
    self.addSegmentationObserver(self.segmentationNode)
    self.segmentEditorWidget.show()
    self.modifySegmentButton.hide()

  def onConfirmSegmentButtonClicked(self):
    if self.segmentationModified is True:
      volumesLogic = slicer.modules.volumes.logic()
      clonedLabelNode = volumesLogic.CloneVolume(slicer.mrmlScene, self.labelNode,
                                                 self.labelNode.GetName() + "_modified")
      self.labelNode = clonedLabelNode
      slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(self.segmentationNode, self.labelNode)
      ModuleLogicMixin.runBRAINSResample(inputVolume=self.labelNode, referenceVolume=self.volumeNode,
                                         outputVolume=self.labelNode)
    self.accept()

  @logmethod(logging.DEBUG)
  def addSegmentationObserver(self, segmentation):
    import vtkSegmentationCorePython as vtkSegmentationCore
    self.observedSegmentation = segmentation
    self.segmentObserver = self.observedSegmentation.AddObserver(
      vtkSegmentationCore.vtkSegmentation.RepresentationModified,
      self.onSegmentModified)

  @logmethod(logging.DEBUG)
  def removeSegmentationObserver(self):
    if self.observedSegmentation:
      self.observedSegmentation.RemoveObserver(self.segmentObserver)
      self.segmentObserver = None

  def onSegmentModified(self, caller, event):
    self.segmentationModified = True

  @logmethod(logging.DEBUG)
  def cleanup(self):
    self.removeSegmentationObserver()
    if self.observedSegmentation:
      slicer.mrmlScene.RemoveNode(self.segmentationNode)
      slicer.mrmlScene.RemoveNode(self.segmentEditorNode)
    self.observedSegmentation = None
    self.segmentEditorWidget.hide()
    self.modifySegmentButton.show()