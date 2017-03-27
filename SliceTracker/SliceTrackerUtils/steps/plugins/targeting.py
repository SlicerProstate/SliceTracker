import qt
import vtk
import logging
from ...constants import SliceTrackerConstants as constants
from ..base import SliceTrackerPlugin, SliceTrackerLogicBase

from SlicerProstateUtils.decorators import logmethod
from SlicerProstateUtils.helpers import SliceAnnotation
from SlicerProstateUtils.helpers import TargetCreationWidget
from targets import SliceTrackerTargetTablePlugin


class SliceTrackerTargetingPlugin(SliceTrackerPlugin):

  NAME = "Targeting"
  TargetingStartedEvent = vtk.vtkCommand.UserEvent + 335
  TargetingFinishedEvent = vtk.vtkCommand.UserEvent + 336

  def __init__(self):
    super(SliceTrackerTargetingPlugin, self).__init__()

  def setup(self):
    self.targetTablePlugin = SliceTrackerTargetTablePlugin()
    self.addPlugin(self.targetTablePlugin)
    self.layout().addWidget(self.targetTablePlugin, 0, 0, 1, 2)

    self.targetingGroupBox = qt.QGroupBox()
    self.targetingGroupBoxLayout = qt.QFormLayout()
    self.targetingGroupBox.setLayout(self.targetingGroupBoxLayout)
    self.fiducialsWidget = TargetCreationWidget()
    self.startTargetingButton = self.createButton("Place targets", enabled=True, toolTip="Start setting targets")
    self.stopTargetingButton = self.createButton("Done", enabled=False, toolTip="Finish setting targets")
    self.buttons = self.createHLayout([self.startTargetingButton, self.stopTargetingButton])
    self.targetingGroupBoxLayout.addRow(self.fiducialsWidget)
    self.targetingGroupBoxLayout.addRow(self.buttons)
    self.layout().addWidget(self.targetingGroupBox, 1, 0, 2, 2)

  def setupConnections(self):
    self.startTargetingButton.clicked.connect(self.onStartTargetingButtonClicked)
    self.stopTargetingButton.clicked.connect(self.onFinishTargetingStepButtonClicked)

  def onActivation(self):
    self.startTargetingButton.enabled = True
    self.startTargetingButton.text = "Place targets"
    self.stopTargetingButton.enabled = False
    self.targetingGroupBox.visible = not self.session.data.usePreopData and not self.session.retryMode
    self.targetTablePlugin.visible = False

  def onDeactivation(self):
    self.fiducialsWidget.reset()
    self.removeSliceAnnotations()

  def onStartTargetingButtonClicked(self):
    self.addSliceAnnotations()
    self.startTargetingButton.enabled = False
    self.fiducialsWidget.visible = True
    self.targetTablePlugin.visible = False

    self.setupFourUpView(self.session.currentSeriesVolume)
    if not self.fiducialsWidget.currentNode:
      self.fiducialsWidget.createNewFiducialNode(name="IntraopTargets")
    self.fiducialsWidget.startPlacing()

    self.fiducialsWidget.addEventObserver(vtk.vtkCommand.ModifiedEvent, self.onTargetListModified)
    self.onTargetListModified()
    self.invokeEvent(self.TargetingStartedEvent)

  def addSliceAnnotations(self):
    self.removeSliceAnnotations()
    widgets = [self.yellowWidget] if self.layoutManager.layout == constants.LAYOUT_SIDE_BY_SIDE else \
      [self.redWidget, self.yellowWidget, self.greenWidget]
    for widget in widgets:
      self.sliceAnnotations.append(SliceAnnotation(widget, "Targeting Mode", opacity=0.5, verticalAlign="top",
                                                   horizontalAlign="center"))

  def removeSliceAnnotations(self):
    self.sliceAnnotations = getattr(self, "sliceAnnotations", [])
    for annotation in self.sliceAnnotations:
      annotation.remove()
    self.sliceAnnotations = []

  def onFinishTargetingStepButtonClicked(self):
    self.removeSliceAnnotations()
    self.fiducialsWidget.stopPlacing()
    self.startTargetingButton.enabled = True
    self.startTargetingButton.text = "Modify targets"
    self.stopTargetingButton.enabled = False
    self.session.movingTargets = self.fiducialsWidget.currentNode
    self.session.setupPreopLoadedTargets()

    self.fiducialsWidget.visible = False
    self.targetTablePlugin.visible = True

    self.fiducialsWidget.removeEventObserver(vtk.vtkCommand.ModifiedEvent, self.onTargetListModified)

    self.invokeEvent(self.TargetingFinishedEvent)

  @logmethod(logging.INFO)
  def onTargetListModified(self, caller=None, event=None):
    self.targetTablePlugin.currentTargets = self.fiducialsWidget.currentNode
    self.stopTargetingButton.enabled = self.isTargetListValid()

  def isTargetListValid(self):
    return self.fiducialsWidget.currentNode is not None and self.fiducialsWidget.currentNode.GetNumberOfFiducials()
