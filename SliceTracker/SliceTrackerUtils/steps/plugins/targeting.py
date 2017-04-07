import qt
import vtk
from ...constants import SliceTrackerConstants as constants
from ..base import SliceTrackerPlugin

from SlicerProstateUtils.helpers import SliceAnnotation
from SlicerProstateUtils.widgets import TargetCreationWidget
from SlicerProstateUtils.decorators import logmethod
import logging
from targets import SliceTrackerTargetTablePlugin


class SliceTrackerTargetingPlugin(SliceTrackerPlugin):

  NAME = "Targeting"
  TargetingStartedEvent = vtk.vtkCommand.UserEvent + 335
  TargetingFinishedEvent = vtk.vtkCommand.UserEvent + 336

  def __init__(self):
    super(SliceTrackerTargetingPlugin, self).__init__()

  def setupIcons(self):
    self.setTargetsIcon = self.createIcon("icon-addFiducial.png")
    self.modifyTargetsIcon = self.createIcon("icon-modifyFiducial.png")
    self.finishIcon = self.createIcon("icon-apply.png")

  def setup(self):
    self.targetTablePlugin = SliceTrackerTargetTablePlugin()
    self.addPlugin(self.targetTablePlugin)

    iconSize = qt.QSize(36, 36)
    self.targetingGroupBox = qt.QGroupBox("Target Placement")
    self.targetingGroupBoxLayout = qt.QFormLayout()
    self.targetingGroupBox.setLayout(self.targetingGroupBoxLayout)
    self.fiducialsWidget = TargetCreationWidget()
    self.startTargetingButton = self.createButton("", enabled=True, icon=self.setTargetsIcon, iconSize=iconSize,
                                                  toolTip="Start placing targets")
    self.stopTargetingButton = self.createButton("", enabled=False, icon=self.finishIcon, iconSize=iconSize,
                                                 toolTip="Finish placing targets")
    self.buttons = self.createHLayout([self.startTargetingButton, self.stopTargetingButton])
    self.targetingGroupBoxLayout.addRow(self.targetTablePlugin)
    self.targetingGroupBoxLayout.addRow(self.fiducialsWidget)
    self.targetingGroupBoxLayout.addRow(self.buttons)
    self.layout().addWidget(self.targetingGroupBox, 1, 0, 2, 2)

  def setupConnections(self):
    self.startTargetingButton.clicked.connect(self.onStartTargetingButtonClicked)
    self.stopTargetingButton.clicked.connect(self.onFinishTargetingStepButtonClicked)

  def noPreopAndTargetsWereNotDefined(self):
    return (not self.session.data.usePreopData and not self.session.movingTargets) or self.session.retryMode

  def onActivation(self):
    self.fiducialsWidget.visible = True
    self.targetTablePlugin.visible = False

    if not self.noPreopAndTargetsWereNotDefined():
      self.fiducialsWidget.visible = False
      self.fiducialsWidget.currentNode = self.session.movingTargets
      self.targetTablePlugin.visible = True
      self.targetTablePlugin.currentTargets = self.session.movingTargets

    self.startTargetingButton.enabled = True
    self.startTargetingButton.icon = self.setTargetsIcon \
      if self.noPreopAndTargetsWereNotDefined() else self.modifyTargetsIcon
    self.startTargetingButton.toolTip = "{} targets".format("Place" if self.noPreopAndTargetsWereNotDefined()
                                                            else "Modify")
    self.stopTargetingButton.enabled = False
    self.targetingGroupBox.visible = not self.session.data.usePreopData and not self.session.retryMode

  def onDeactivation(self):
    self.fiducialsWidget.reset()
    self.removeSliceAnnotations()

  def onStartTargetingButtonClicked(self):
    self.addSliceAnnotations()
    self.startTargetingButton.enabled = False
    self.fiducialsWidget.visible = True
    self.targetTablePlugin.visible = False

    self.setupFourUpView(self.session.currentSeriesVolume, clearLabels=False)
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
    self.fiducialsWidget.removeEventObserver(vtk.vtkCommand.ModifiedEvent, self.onTargetListModified)
    self.removeSliceAnnotations()
    self.fiducialsWidget.stopPlacing()
    self.startTargetingButton.enabled = True
    self.startTargetingButton.icon = self.modifyTargetsIcon
    self.startTargetingButton.toolTip = "Modify targets"
    self.stopTargetingButton.enabled = False
    self.session.movingTargets = self.fiducialsWidget.currentNode
    self.session.setupPreopLoadedTargets()

    self.fiducialsWidget.visible = False
    self.targetTablePlugin.visible = True
    self.targetTablePlugin.currentTargets = self.fiducialsWidget.currentNode

    self.invokeEvent(self.TargetingFinishedEvent)

  @logmethod(logging.INFO)
  def onTargetListModified(self, caller=None, event=None):
    self.stopTargetingButton.enabled = self.isTargetListValid()

  def isTargetListValid(self):
    return self.fiducialsWidget.currentNode is not None and self.fiducialsWidget.currentNode.GetNumberOfFiducials()
