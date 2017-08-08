import qt
import vtk
import slicer

from ...base import SliceTrackerPlugin
from ....constants import SliceTrackerConstants as constants
from base import SliceTrackerSegmentationPluginBase
from SurfaceCutToLabel import SurfaceCutToLabelWidget

from SlicerDevelopmentToolboxUtils.decorators import onModuleSelected


class SliceTrackerManualSegmentationPlugin(SliceTrackerSegmentationPluginBase):

  NAME = "ManualSegmentation"

  SegmentationCanceledEvent = SurfaceCutToLabelWidget.SegmentationCanceledEvent

  @property
  def segmentModelNode(self):
    return self.surfaceCutToLabelWidget.logic.segmentModelNode

  @property
  def inputMarkupNode(self):
    return self.surfaceCutToLabelWidget.logic.inputMarkupNode

  def __init__(self):
    super(SliceTrackerManualSegmentationPlugin, self).__init__()

  def setup(self):
    super(SliceTrackerManualSegmentationPlugin, self).setup()

    self.surfaceCutGroupBox = qt.QWidget()
    self.surfaceCutGroupBox.setLayout(qt.QVBoxLayout())
    self.surfaceCutToLabelWidget = SurfaceCutToLabelWidget(self.surfaceCutGroupBox)
    self.surfaceCutToLabelWidget.setup()
    self.surfaceCutToLabelWidget.selectorsGroupBoxVisible = False
    self.surfaceCutToLabelWidget.colorGroupBoxVisible = False

    if self.getSetting('DeveloperMode', 'Developer').lower() == 'true':
      self.surfaceCutToLabelWidget.reloadCollapsibleButton.hide()

    self.segmentationGroupBox = qt.QGroupBox("SurfaceCut Segmentation")
    self.segmentationGroupBoxLayout = qt.QGridLayout()
    self.segmentationGroupBox.setLayout(self.segmentationGroupBoxLayout)
    self.segmentationGroupBoxLayout.addWidget(self.surfaceCutGroupBox, 0, 0)
    self.layout().addWidget(self.segmentationGroupBox)

  @onModuleSelected(SliceTrackerPlugin.MODULE_NAME)
  def onLayoutChanged(self, layout=None):
    self._refreshSegmentModelViewNodes()

  def _refreshSegmentModelViewNodes(self):
    sliceNodes = [self.yellowSliceNode] if self.layoutManager.layout == constants.LAYOUT_SIDE_BY_SIDE else \
      [self.redSliceNode, self.yellowSliceNode, self.greenSliceNode]
    nodes = [self.surfaceCutToLabelWidget.logic.segmentModelNode, self.surfaceCutToLabelWidget.logic.inputMarkupNode]
    for node in [n for n in nodes if n]:
      self.refreshViewNodeIDs(node, sliceNodes)

  def onActivation(self):
    super(SliceTrackerManualSegmentationPlugin, self).onActivation()
    self.surfaceCutToLabelWidget.logic.colorNode = self.session.mpReviewColorNode
    self.surfaceCutToLabelWidget.colorSpin.setValue(self.session.segmentedLabelValue)
    self.surfaceCutToLabelWidget.imageVolumeSelector.setCurrentNode(self.session.fixedVolume)
    self._addSurfaceCutEventObservers()
    # if (self.session.data.usePreopData or self.session.retryMode) and self.getSetting("Use_Deep_Learning") == "false":
    #   self.layoutManager.setLayout(constants.LAYOUT_FOUR_UP)
    #   slicer.app.processEvents()
    #   self.surfaceCutToLabelWidget.quickSegmentationButton.click()

  def onDeactivation(self):
    super(SliceTrackerManualSegmentationPlugin, self).onDeactivation()
    self._removeSurfacCutEventObservers()

  def _addSurfaceCutEventObservers(self):
    self.surfaceCutToLabelWidget.addEventObserver(self.surfaceCutToLabelWidget.SegmentationStartedEvent,
                                                  self._onSegmentationStarted)
    self.surfaceCutToLabelWidget.addEventObserver(self.surfaceCutToLabelWidget.SegmentationCanceledEvent,
                                                  self._onSegmentationCanceled)
    self.surfaceCutToLabelWidget.addEventObserver(self.surfaceCutToLabelWidget.SegmentationFinishedEvent,
                                                  self._onSegmentationFinished)

  def _removeSurfacCutEventObservers(self):
    self.surfaceCutToLabelWidget.removeEventObserver(self.surfaceCutToLabelWidget.SegmentationStartedEvent,
                                                     self._onSegmentationStarted)
    self.surfaceCutToLabelWidget.removeEventObserver(self.surfaceCutToLabelWidget.SegmentationCanceledEvent,
                                                     self._onSegmentationCanceled)
    self.surfaceCutToLabelWidget.removeEventObserver(self.surfaceCutToLabelWidget.SegmentationFinishedEvent,
                                                     self._onSegmentationFinished)

  def _onSegmentationStarted(self, caller, event):
    if self.getSetting("Use_Deep_Learning") == "true":
      if not self._preCheckExistingSegmentation():
        return
    self.setupFourUpView(self.session.fixedVolume)
    self.setDefaultOrientation()
    self.invokeEvent(self.SegmentationStartedEvent)

  def _preCheckExistingSegmentation(self):
    if not slicer.util.confirmYesNoDisplay("The automatic segmentation will be overwritten. Do you want to proceed?",
                                           windowTitle="SliceTracker"):
      self.surfaceCutToLabelWidget.stopQuickSegmentationMode(cancelled=True)
      return False
    return True

  def _onSegmentationCanceled(self, caller, event):
    self.invokeEvent(self.SegmentationCanceledEvent)

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def _onSegmentationFinished(self, caller, event, labelNode):
    displayNode = labelNode.GetDisplayNode()
    displayNode.SetAndObserveColorNodeID(self.session.mpReviewColorNode.GetID())
    self.surfaceCutToLabelWidget.colorSpin.setValue(self.session.segmentedLabelValue)
    self.invokeEvent(self.SegmentationFinishedEvent, labelNode)