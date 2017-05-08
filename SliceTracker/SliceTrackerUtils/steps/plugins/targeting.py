import qt
import vtk
from ...constants import SliceTrackerConstants as constants
from ..base import SliceTrackerPlugin

from SlicerDevelopmentToolboxUtils.helpers import SliceAnnotation
from SlicerDevelopmentToolboxUtils.widgets import TargetCreationWidget
from targets import SliceTrackerTargetTablePlugin


class SliceTrackerTargetingPlugin(SliceTrackerPlugin):

  NAME = "Targeting"
  TargetingStartedEvent = vtk.vtkCommand.UserEvent + 335
  TargetingFinishedEvent = vtk.vtkCommand.UserEvent + 336

  def __init__(self):
    super(SliceTrackerTargetingPlugin, self).__init__()

  def setup(self):
    super(SliceTrackerTargetingPlugin, self).setup()
    self.targetTablePlugin = SliceTrackerTargetTablePlugin()
    self.addPlugin(self.targetTablePlugin)

    self.targetingGroupBox = qt.QGroupBox("Target Placement")
    self.targetingGroupBoxLayout = qt.QFormLayout()
    self.targetingGroupBox.setLayout(self.targetingGroupBoxLayout)
    self.fiducialsWidget = TargetCreationWidget(DEFAULT_FIDUCIAL_LIST_NAME="IntraopTargets",
                                                ICON_SIZE=qt.QSize(36, 36))
    self.fiducialsWidget.addEventObserver(self.fiducialsWidget.TargetingStartedEvent, self.onTargetingStarted)
    self.fiducialsWidget.addEventObserver(self.fiducialsWidget.TargetingFinishedEvent, self.onTargetingFinished)
    self.targetingGroupBoxLayout.addRow(self.targetTablePlugin)
    self.targetingGroupBoxLayout.addRow(self.fiducialsWidget)
    self.targetingGroupBoxLayout.addRow(self.fiducialsWidget.buttons)
    self.layout().addWidget(self.targetingGroupBox, 1, 0, 2, 2)

  def noPreopAndTargetsWereNotDefined(self):
    return (not self.session.data.usePreopData and not self.session.movingTargets) or self.session.retryMode

  def onActivation(self):
    super(SliceTrackerTargetingPlugin, self).onActivation()
    self.fiducialsWidget.show()
    self.targetTablePlugin.visible = False

    if not self.noPreopAndTargetsWereNotDefined():
      self.fiducialsWidget.visible = False
      self.fiducialsWidget.currentNode = self.session.movingTargets
      self.targetTablePlugin.visible = True
      self.targetTablePlugin.currentTargets = self.session.movingTargets

    self.targetingGroupBox.visible = not self.session.data.usePreopData and not self.session.retryMode

  def onDeactivation(self):
    super(SliceTrackerTargetingPlugin, self).onDeactivation()
    self.fiducialsWidget.reset()
    self.removeSliceAnnotations()

  def startTargeting(self):
    self.fiducialsWidget.startPlacing()

  def onTargetingStarted(self, caller, event):
    self.addSliceAnnotations()
    self.fiducialsWidget.show()
    self.targetTablePlugin.visible = False
    self.setupFourUpView(self.session.currentSeriesVolume, clearLabels=False)
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

  def onTargetingFinished(self, caller, event):
    self.removeSliceAnnotations()
    if self.fiducialsWidget.hasTargetListAtLeastOneTarget():
      self.session.movingTargets = self.fiducialsWidget.currentNode
      self.session.setupPreopLoadedTargets()
      self.fiducialsWidget.visible = False
      self.targetTablePlugin.visible = True
      self.targetTablePlugin.currentTargets = self.fiducialsWidget.currentNode
    else:
      self.session.movingTargets = None

    self.invokeEvent(self.TargetingFinishedEvent)