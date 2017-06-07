import qt
import vtk
import slicer
from ...base import SliceTrackerPlugin
from VolumeClipToLabel import VolumeClipToLabelWidget
from ....constants import SliceTrackerConstants as constants
from base import SliceTrackerSegmentationPluginBase

from SlicerDevelopmentToolboxUtils.decorators import onModuleSelected


class SliceTrackerManualSegmentationPlugin(SliceTrackerSegmentationPluginBase):

  NAME = "ManualSegmentation"

  SegmentationCanceledEvent = VolumeClipToLabelWidget.SegmentationCanceledEvent

  @property
  def clippingModelNode(self):
    return self.volumeClipToLabelWidget.logic.clippingModelNode

  @property
  def inputMarkupNode(self):
    return self.volumeClipToLabelWidget.logic.inputMarkupNode

  def __init__(self):
    super(SliceTrackerManualSegmentationPlugin, self).__init__()

  def setup(self):
    super(SliceTrackerManualSegmentationPlugin, self).setup()
    try:
      import VolumeClipWithModel
    except ImportError:
      return slicer.util.warningDisplay("Error: Could not find extension VolumeClip. Open Slicer Extension Manager and "
                                        "install VolumeClip.", "Missing Extension")

    self.volumeClipGroupBox = qt.QWidget()
    self.volumeClipGroupBoxLayout = qt.QVBoxLayout()
    self.volumeClipGroupBox.setLayout(self.volumeClipGroupBoxLayout)
    self.volumeClipToLabelWidget = VolumeClipToLabelWidget(self.volumeClipGroupBox)
    self.volumeClipToLabelWidget.setup()
    self.volumeClipToLabelWidget.selectorsGroupBoxVisible = False
    self.volumeClipToLabelWidget.colorGroupBoxVisible = False

    if self.getSetting('DeveloperMode', 'Developer').lower() == 'true':
      self.volumeClipToLabelWidget.reloadCollapsibleButton.hide()

    self.segmentationGroupBox = qt.QGroupBox("VolumeClip Segmentation")
    self.segmentationGroupBoxLayout = qt.QGridLayout()
    self.segmentationGroupBox.setLayout(self.segmentationGroupBoxLayout)
    self.segmentationGroupBoxLayout.addWidget(self.volumeClipGroupBox, 0, 0)
    self.layout().addWidget(self.segmentationGroupBox)

  @onModuleSelected(SliceTrackerPlugin.MODULE_NAME)
  def onLayoutChanged(self, layout=None):
    self._refreshClippingModelViewNodes()

  def _refreshClippingModelViewNodes(self):
    sliceNodes = [self.yellowSliceNode] if self.layoutManager.layout == constants.LAYOUT_SIDE_BY_SIDE else \
      [self.redSliceNode, self.yellowSliceNode, self.greenSliceNode]
    nodes = [self.volumeClipToLabelWidget.logic.clippingModelNode, self.volumeClipToLabelWidget.logic.inputMarkupNode]
    for node in [n for n in nodes if n]:
      self.refreshViewNodeIDs(node, sliceNodes)

  def onActivation(self):
    super(SliceTrackerManualSegmentationPlugin, self).onActivation()
    self.volumeClipToLabelWidget.logic.colorNode = self.session.mpReviewColorNode
    self.volumeClipToLabelWidget.colorSpin.setValue(self.session.segmentedLabelValue)
    self.volumeClipToLabelWidget.imageVolumeSelector.setCurrentNode(self.session.fixedVolume)
    self._addVolumeClipEventObservers()
    # if (self.session.data.usePreopData or self.session.retryMode) and self.getSetting("Use_Deep_Learning") == "false":
    #   self.layoutManager.setLayout(constants.LAYOUT_FOUR_UP)
    #   slicer.app.processEvents()
    #   self.volumeClipToLabelWidget.quickSegmentationButton.click()

  def onDeactivation(self):
    super(SliceTrackerManualSegmentationPlugin, self).onDeactivation()
    self._removeVolumeClipEventObservers()

  def _addVolumeClipEventObservers(self):
    self.volumeClipToLabelWidget.addEventObserver(self.volumeClipToLabelWidget.SegmentationStartedEvent,
                                                  self._onSegmentationStarted)
    self.volumeClipToLabelWidget.addEventObserver(self.volumeClipToLabelWidget.SegmentationCanceledEvent,
                                                  self._onSegmentationCanceled)
    self.volumeClipToLabelWidget.addEventObserver(self.volumeClipToLabelWidget.SegmentationFinishedEvent,
                                                  self._onSegmentationFinished)

  def _removeVolumeClipEventObservers(self):
    self.volumeClipToLabelWidget.removeEventObserver(self.volumeClipToLabelWidget.SegmentationStartedEvent,
                                                     self._onSegmentationStarted)
    self.volumeClipToLabelWidget.removeEventObserver(self.volumeClipToLabelWidget.SegmentationCanceledEvent,
                                                     self._onSegmentationCanceled)
    self.volumeClipToLabelWidget.removeEventObserver(self.volumeClipToLabelWidget.SegmentationFinishedEvent,
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
      self.volumeClipToLabelWidget.stopQuickSegmentationMode(cancelled=True)
      return False
    return True

  def _onSegmentationCanceled(self, caller, event):
    self.invokeEvent(self.SegmentationCanceledEvent)

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def _onSegmentationFinished(self, caller, event, labelNode):
    displayNode = labelNode.GetDisplayNode()
    displayNode.SetAndObserveColorNodeID(self.session.mpReviewColorNode.GetID())
    self.volumeClipToLabelWidget.colorSpin.setValue(self.session.segmentedLabelValue)
    self.invokeEvent(self.SegmentationFinishedEvent, labelNode)