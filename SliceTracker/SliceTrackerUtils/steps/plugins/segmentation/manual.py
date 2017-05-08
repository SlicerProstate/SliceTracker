import qt
import vtk
import slicer
from ...base import SliceTrackerPlugin
from VolumeClipToLabel import VolumeClipToLabelWidget
from Editor import EditorWidget
import EditorLib
from ....constants import SliceTrackerConstants as constants
from base import SliceTrackerSegmentationPluginBase

from SlicerDevelopmentToolboxUtils.decorators import onModuleSelected


class SliceTrackerManualSegmentationPlugin(SliceTrackerSegmentationPluginBase):

  NAME = "ManualSegmentation"
  SegmentationCancelledEvent = vtk.vtkCommand.UserEvent + 437

  @property
  def clippingModelNode(self):
    return self.volumeClipToLabelWidget.logic.clippingModelNode

  @property
  def inputMarkupNode(self):
    return self.volumeClipToLabelWidget.logic.inputMarkupNode

  def __init__(self):
    super(SliceTrackerManualSegmentationPlugin, self).__init__()

  def setupIcons(self):
    self.settingsIcon = self.createIcon('icon-settings.png')

  def setup(self):
    super(SliceTrackerManualSegmentationPlugin, self).setup()
    try:
      import VolumeClipWithModel
    except ImportError:
      return slicer.util.warningDisplay("Error: Could not find extension VolumeClip. Open Slicer Extension Manager and "
                                        "install VolumeClip.", "Missing Extension")

    iconSize = qt.QSize(36, 36)
    self.volumeClipGroupBox = qt.QWidget()
    self.volumeClipGroupBoxLayout = qt.QVBoxLayout()
    self.volumeClipGroupBox.setLayout(self.volumeClipGroupBoxLayout)
    self.volumeClipToLabelWidget = VolumeClipToLabelWidget(self.volumeClipGroupBox)
    self.volumeClipToLabelWidget.setup()
    if qt.QSettings().value('Developer/DeveloperMode').lower() == 'true':
      self.volumeClipToLabelWidget.reloadCollapsibleButton.hide()
    self.volumeClipToLabelWidget.selectorsGroupBox.hide()
    self.volumeClipToLabelWidget.colorGroupBox.hide()
    self.editorWidgetButton = self.createButton("", icon=self.settingsIcon, toolTip="Show Label Editor",
                                                enabled=False, iconSize=iconSize)
    self.setupEditorWidget()
    self.segmentationGroupBox = qt.QGroupBox("VolumeClip Segmentation")
    self.segmentationGroupBoxLayout = qt.QGridLayout()
    self.segmentationGroupBox.setLayout(self.segmentationGroupBoxLayout)
    self.volumeClipToLabelWidget.segmentationButtons.layout().addWidget(self.editorWidgetButton)
    self.segmentationGroupBoxLayout.addWidget(self.volumeClipGroupBox, 0, 0)
    self.segmentationGroupBoxLayout.addWidget(self.editorWidgetParent, 1, 0)
    self.segmentationGroupBoxLayout.setRowStretch(2, 1)
    self.layout().addWidget(self.segmentationGroupBox)
    self.editorWidgetParent.hide()

  def setupEditorWidget(self):
    self.editorWidgetParent = slicer.qMRMLWidget()
    self.editorWidgetParent.setLayout(qt.QVBoxLayout())
    self.editorWidgetParent.setMRMLScene(slicer.mrmlScene)
    self.editUtil = EditorLib.EditUtil.EditUtil()
    self.editorWidget = EditorWidget(parent=self.editorWidgetParent, showVolumesFrame=False)
    self.editorWidget.setup()
    self.editorParameterNode = self.editUtil.getParameterNode()

  def setupConnections(self):
    self.editorWidgetButton.clicked.connect(self.onEditorGearIconClicked)

  def onEditorGearIconClicked(self):
    if self.editorWidgetParent.visible:
      self.disableEditorWidgetAndResetEditorTool(enabledButton=True)
    else:
      self.editorWidgetParent.show()
      displayNode = self.session.fixedLabel.GetDisplayNode()
      displayNode.SetAndObserveColorNodeID(self.session.mpReviewColorNode.GetID())
      self.editorParameterNode.SetParameter('effect', 'DrawEffect')
      self.editUtil.setLabel(self.session.segmentedLabelValue)
      self.editUtil.setLabelOutline(1)

  @onModuleSelected(SliceTrackerPlugin.MODULE_NAME)
  def onLayoutChanged(self, layout=None):
    self.refreshClippingModelViewNodes()

  def refreshClippingModelViewNodes(self):
    sliceNodes = [self.yellowSliceNode] if self.layoutManager.layout == constants.LAYOUT_SIDE_BY_SIDE else \
      [self.redSliceNode, self.yellowSliceNode, self.greenSliceNode]
    nodes = [self.volumeClipToLabelWidget.logic.clippingModelNode, self.volumeClipToLabelWidget.logic.inputMarkupNode]
    for node in [n for n in nodes if n]:
      self.refreshViewNodeIDs(node, sliceNodes)

  def onActivation(self):
    super(SliceTrackerManualSegmentationPlugin, self).onActivation()
    self.volumeClipToLabelWidget.logic.colorNode = self.session.mpReviewColorNode
    self.volumeClipToLabelWidget.onColorSelected(self.session.segmentedLabelValue)
    self.volumeClipToLabelWidget.imageVolumeSelector.setCurrentNode(self.session.fixedVolume)
    self.volumeClipToLabelWidget.addEventObserver(self.volumeClipToLabelWidget.SegmentationFinishedEvent,
                                                  self.onSegmentationFinished)
    self.volumeClipToLabelWidget.addEventObserver(self.volumeClipToLabelWidget.SegmentationCanceledEvent,
                                                  lambda caller, event: self.invokeEvent(self.SegmentationCancelledEvent))
    self.volumeClipToLabelWidget.addEventObserver(self.volumeClipToLabelWidget.SegmentationStartedEvent,
                                                  self.onSegmentationStarted)
    if (self.session.data.usePreopData or self.session.retryMode) and self.getSetting("Use_Deep_Learning") == "false":
      self.volumeClipToLabelWidget.quickSegmentationButton.click()

  def onDeactivation(self):
    super(SliceTrackerManualSegmentationPlugin, self).onDeactivation()
    self.volumeClipToLabelWidget.removeEventObserver(self.volumeClipToLabelWidget.SegmentationFinishedEvent,
                                                     self.onSegmentationFinished)
    self.volumeClipToLabelWidget.removeEventObserver(self.volumeClipToLabelWidget.SegmentationCanceledEvent,
                                                     lambda caller, event: self.invokeEvent(self.SegmentationCancelledEvent))
    self.volumeClipToLabelWidget.removeEventObserver(self.volumeClipToLabelWidget.SegmentationStartedEvent,
                                                     self.onSegmentationStarted)

  def onSegmentationStarted(self, caller, event):
    self.setupFourUpView(self.session.fixedVolume)
    self.setDefaultOrientation()
    self.invokeEvent(self.SegmentationStartedEvent)

  def disableEditorWidgetAndResetEditorTool(self, enabledButton=False):
    self.editorWidgetParent.hide()
    self.editorParameterNode.SetParameter('effect', 'DefaultTool')
    self.editorWidgetButton.setEnabled(enabledButton)

  def enableEditorWidgetButton(self):
    self.editorWidgetButton.enabled = True

  def disableEditorWidgetButton(self):
    self.disableEditorWidgetAndResetEditorTool(False)