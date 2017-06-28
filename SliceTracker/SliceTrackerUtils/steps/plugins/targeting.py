import qt
from ...constants import SliceTrackerConstants as constants
from ..base import SliceTrackerPlugin
from targets import SliceTrackerTargetTablePlugin

from SlicerDevelopmentToolboxUtils.helpers import SliceAnnotation
from SlicerDevelopmentToolboxUtils.widgets import TargetCreationWidget


class SliceTrackerTargetingPlugin(SliceTrackerPlugin):

  NAME = "Targeting"
  TargetingStartedEvent = TargetCreationWidget.StartedEvent
  TargetingFinishedEvent = TargetCreationWidget.FinishedEvent

  def __init__(self):
    super(SliceTrackerTargetingPlugin, self).__init__()

  def setup(self):
    super(SliceTrackerTargetingPlugin, self).setup()
    self.targetTablePlugin = SliceTrackerTargetTablePlugin()
    self.addPlugin(self.targetTablePlugin)

    self._setupTargetCreationWidget()

    self.targetingGroupBox = qt.QGroupBox("Target Placement")
    self.targetingGroupBox.setLayout(qt.QFormLayout())
    self.targetingGroupBox.layout().addRow(self.targetTablePlugin)
    self.targetingGroupBox.layout().addRow(self.targetCreationWidget)
    self.targetingGroupBox.layout().addRow(self.targetCreationWidget.buttons)
    self.layout().addWidget(self.targetingGroupBox, 1, 0, 2, 2)

  def _setupTargetCreationWidget(self):
    self.targetCreationWidget = TargetCreationWidget(DEFAULT_FIDUCIAL_LIST_NAME="IntraopTargets",
                                                     ICON_SIZE=qt.QSize(36, 36))
    self.targetCreationWidget.addEventObserver(self.TargetingStartedEvent, self._onTargetingStarted)
    self.targetCreationWidget.addEventObserver(self.TargetingFinishedEvent, self._onTargetingFinished)

  def preopAvailableAndTargetsDefined(self):
    return self.session.data.usePreopData and self.session.movingTargets and not self.session.retryMode

  def onActivation(self):
    super(SliceTrackerTargetingPlugin, self).onActivation()
    self._setFiducialWidgetVisible(True)

    if self.preopAvailableAndTargetsDefined():
      self._setFiducialWidgetVisible(False)
      self._setCurrentTargets(self.session.movingTargets)

    self.targetingGroupBox.visible = not (self.session.data.usePreopData or self.session.retryMode)

  def onDeactivation(self):
    super(SliceTrackerTargetingPlugin, self).onDeactivation()
    self.targetCreationWidget.reset()
    self._removeSliceAnnotations()

  def startTargeting(self):
    self.targetCreationWidget.startPlacing()

  def _setFiducialWidgetVisible(self, visible):
    self.targetCreationWidget.visible = visible
    self.targetTablePlugin.visible = not visible

  def _setCurrentTargets(self, targetNode):
    self.targetCreationWidget.currentNode = targetNode
    self.targetTablePlugin.currentTargets = targetNode

  def _onTargetingStarted(self, caller, event):
    self._addSliceAnnotations()
    self.targetCreationWidget.show()
    self.targetTablePlugin.visible = False
    self.setupFourUpView(self.session.currentSeriesVolume, clearLabels=False)
    self.invokeEvent(self.TargetingStartedEvent)

  def _addSliceAnnotations(self):
    self._removeSliceAnnotations()
    widgets = [self.yellowWidget] if self.layoutManager.layout == constants.LAYOUT_SIDE_BY_SIDE else \
      [self.redWidget, self.yellowWidget, self.greenWidget]
    for widget in widgets:
      self.sliceAnnotations.append(SliceAnnotation(widget, "Targeting Mode", opacity=0.5, verticalAlign="top",
                                                   horizontalAlign="center"))

  def _removeSliceAnnotations(self):
    self.sliceAnnotations = getattr(self, "sliceAnnotations", [])
    for annotation in self.sliceAnnotations:
      annotation.remove()
    self.sliceAnnotations = []

  def _onTargetingFinished(self, caller, event):
    self._removeSliceAnnotations()
    if self.targetCreationWidget.hasTargetListAtLeastOneTarget():
      self.session.movingTargets = self.targetCreationWidget.currentNode
      self.session.setupPreopLoadedTargets()
      self._setFiducialWidgetVisible(False)
      self.targetTablePlugin.currentTargets = self.targetCreationWidget.currentNode
    else:
      self.session.movingTargets = None

    self.invokeEvent(self.TargetingFinishedEvent)