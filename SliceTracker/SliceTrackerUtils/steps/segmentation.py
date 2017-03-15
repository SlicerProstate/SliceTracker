import os
import ast
import EditorLib
import qt
import slicer
import vtk
from Editor import EditorWidget
from base import SliceTrackerStepLogic, SliceTrackerStep
from VolumeClipToLabel import VolumeClipToLabelWidget
from SlicerProstateUtils.helpers import TargetCreationWidget, SliceAnnotation
from ..constants import SliceTrackerConstants


class SliceTrackerSegmentationStepLogic(SliceTrackerStepLogic):

  def __init__(self):
    super(SliceTrackerSegmentationStepLogic, self).__init__()

  def cleanup(self):
    pass


class SliceTrackerSegmentationStep(SliceTrackerStep):

  NAME = "Segmentation"
  LogicClass = SliceTrackerSegmentationStepLogic

  def __init__(self):
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.MODULE_NAME)).replace(".py", "")
    super(SliceTrackerSegmentationStep, self).__init__()
    self.resetAndInitialize()

  def resetAndInitialize(self):
    self.retryMode = False

  def setup(self):
    self.setupIcons()
    try:
      import VolumeClipWithModel
    except ImportError:
      return slicer.util.warningDisplay("Error: Could not find extension VolumeClip. Open Slicer Extension Manager and "
                                        "install VolumeClip.", "Missing Extension")

    self.setupTargetingStepUIElements()

    iconSize = qt.QSize(24, 24)
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
    self.segmentationGroupBox = qt.QGroupBox()
    self.segmentationGroupBoxLayout = qt.QGridLayout()
    self.segmentationGroupBox.setLayout(self.segmentationGroupBoxLayout)
    self.volumeClipToLabelWidget.segmentationButtons.layout().addWidget(self.editorWidgetButton)
    self.segmentationGroupBoxLayout.addWidget(self.volumeClipGroupBox, 0, 0)
    self.segmentationGroupBoxLayout.addWidget(self.editorWidgetParent, 1, 0)

    self.finishedSegmentationStepButton = self.createButton("Apply Registration", icon=self.greenCheckIcon,
                                                            iconSize=iconSize, toolTip="Run Registration.")
    self.finishedSegmentationStepButton.setFixedHeight(45)
    self.segmentationGroupBoxLayout.addWidget(self.finishedSegmentationStepButton, 2, 0)
    self.segmentationGroupBoxLayout.setRowStretch(3, 1)
    self.layout().addWidget(self.segmentationGroupBox)
    self.editorWidgetParent.hide()

  def setupIcons(self):
    self.greenCheckIcon = self.createIcon('icon-greenCheck.png')
    self.settingsIcon = self.createIcon('icon-settings.png')

  def setupEditorWidget(self):
    self.editorWidgetParent = slicer.qMRMLWidget()
    self.editorWidgetParent.setLayout(qt.QVBoxLayout())
    self.editorWidgetParent.setMRMLScene(slicer.mrmlScene)
    self.editUtil = EditorLib.EditUtil.EditUtil()
    self.editorWidget = EditorWidget(parent=self.editorWidgetParent, showVolumesFrame=False)
    self.editorWidget.setup()
    self.editorParameterNode = self.editUtil.getParameterNode()

  def setupTargetingStepUIElements(self):
    self.targetingGroupBox = qt.QGroupBox()
    self.targetingGroupBoxLayout = qt.QFormLayout()
    self.targetingGroupBox.setLayout(self.targetingGroupBoxLayout)

    self.fiducialsWidget = TargetCreationWidget(self.targetingGroupBoxLayout)
    self.fiducialsWidget.addEventObserver(vtk.vtkCommand.ModifiedEvent, self.onTargetListModified)
    self.startTargetingButton = self.createButton("Set targets", enabled=True,
                                                  toolTip="Click this button to start setting targets")
    self.finishTargetingButton = self.createButton("Done setting targets", enabled=False,
                                                   toolTip="Click this button to continue after setting targets")

    self.targetingGroupBoxLayout.addRow(self.createHLayout([self.startTargetingButton, self.finishTargetingButton]))
    self.layout().addWidget(self.targetingGroupBox)

  def setupConnections(self):
    super(SliceTrackerSegmentationStep, self).setupConnections()
    self.fiducialsWidget.addEventObserver(vtk.vtkCommand.ModifiedEvent, self.onTargetListModified)
    self.startTargetingButton.clicked.connect(self.onStartTargetingButtonClicked)
    self.finishTargetingButton.clicked.connect(self.onFinishTargetingStepButtonClicked)
    self.finishedSegmentationStepButton.clicked.connect(self.onFinishedStep)

  def onActivation(self):
    self.volumeClipToLabelWidget.logic.colorNode = self.session.mpReviewColorNode
    self.volumeClipToLabelWidget.onColorSelected(self.session.segmentedLabelValue)
    self.startTargetingButton.enabled = not self.session.data.usePreopData
    self.session.fixedVolume = self.session.currentSeriesVolume
    if not self.session.fixedVolume:
      return
    self.volumeClipToLabelWidget.imageVolumeSelector.setCurrentNode(self.session.fixedVolume)
    self.layoutManager.setLayout(SliceTrackerConstants.LAYOUT_FOUR_UP)
    self.setupFourUpView(self.session.fixedVolume)
    if self.session.data.usePreopData or self.retryMode:
      self.volumeClipToLabelWidget.quickSegmentationButton.click()
    self.volumeClipToLabelWidget.addEventObserver(self.volumeClipToLabelWidget.SegmentationFinishedEvent,
                                                  self.onSegmentationFinished)
    self.setDefaultOrientation()

  def onDeactivation(self):
    self.fiducialsWidget.reset()

  @vtk.calldata_type(vtk.VTK_STRING)
  def onInitiateSegmentation(self, caller, event, callData):
    self.resetAndInitialize()
    self.retryMode = ast.literal_eval(callData)
    self.configureUIElements()
    if self.getSetting("Cover_Prostate") in self.session.currentSeries:
      if self.session.data.usePreopData:
        if self.retryMode:
          self.loadLatestCoverProstateResultData()
        else:
          self.session.movingLabel = self.session.data.initialLabel
          self.session.movingVolume = self.session.data.initialVolume
          self.session.movingTargets = self.session.data.initialTargets
      else:
        self.session.movingVolume = self.session.currentSeriesVolume
    else:
      self.loadLatestCoverProstateResultData()
    self.active = True

  def configureUIElements(self):
    self.targetingGroupBox.visible = not self.session.data.usePreopData and not self.retryMode
    text = "Apply Registration"
    if self.getSetting("Cover_Prostate") in self.session.currentSeries and not self.session.data.usePreopData:
      text = "Finish"
    self.finishedSegmentationStepButton.text = text
    self.finishedSegmentationStepButton.setEnabled(1 if self.inputsAreSet() else 0)

  def onLayoutChanged(self):
    if self.layoutManager.layout == SliceTrackerConstants.LAYOUT_SIDE_BY_SIDE:
      self.setupSideBySideSegmentationView()
    elif self.layoutManager.layout in [SliceTrackerConstants.LAYOUT_FOUR_UP,
                                       SliceTrackerConstants.LAYOUT_RED_SLICE_ONLY]:
      self.removeMissingPreopDataAnnotation()
      self.setBackgroundToVolumeID(self.session.currentSeriesVolume.GetID())
    self.refreshClippingModelViewNodes()

  def refreshClippingModelViewNodes(self):
    sliceNodes = [self.yellowSliceNode] if self.layoutManager.layout == SliceTrackerConstants.LAYOUT_SIDE_BY_SIDE else \
      [self.redSliceNode, self.yellowSliceNode, self.greenSliceNode]
    nodes = [self.volumeClipToLabelWidget.logic.clippingModelNode, self.volumeClipToLabelWidget.logic.inputMarkupNode]
    for node in [n for n in nodes if n]:
      self.refreshViewNodeIDs(node, sliceNodes)

  def setupSideBySideSegmentationView(self):
    # TODO: red slice view should not be possible to set target
    coverProstate = self.session.data.getMostRecentApprovedCoverProstateRegistration()
    redVolume = coverProstate.fixedVolume if self.retryMode and coverProstate else self.session.data.initialVolume
    redLabel = coverProstate.fixedLabel if self.retryMode and coverProstate else self.session.data.initialLabel

    if redVolume and redLabel:
      self.redCompositeNode.SetBackgroundVolumeID(redVolume.GetID())
      self.redCompositeNode.SetLabelVolumeID(redLabel.GetID())
    else:
      self.redCompositeNode.SetBackgroundVolumeID(None)
      self.redCompositeNode.SetLabelVolumeID(None)
      self.addMissingPreopDataAnnotation(self.redWidget)
    self.yellowCompositeNode.SetBackgroundVolumeID(self.session.currentSeriesVolume.GetID())
    self.setAxialOrientation()

    if redVolume and redLabel:
      self.redSliceNode.SetUseLabelOutline(True)
      self.redSliceNode.RotateToVolumePlane(redVolume)

  def removeMissingPreopDataAnnotation(self):
    self.segmentationNoPreopAnnotation = getattr(self, "segmentationNoPreopAnnotation", None)
    if self.segmentationNoPreopAnnotation:
      self.segmentationNoPreopAnnotation.remove()
      self.segmentationNoPreopAnnotation = None

  def addMissingPreopDataAnnotation(self, widget):
    self.removeMissingPreopDataAnnotation()
    self.segmentationNoPreopAnnotation = SliceAnnotation(widget, SliceTrackerConstants.MISSING_PREOP_ANNOTATION_TEXT,
                                                         opacity=0.7, color=(1, 0, 0))

  def loadLatestCoverProstateResultData(self):
    coverProstate = self.data.getMostRecentApprovedCoverProstateRegistration()
    self.session.movingVolume = coverProstate.volumes.fixed
    self.session.movingLabel = coverProstate.labels.fixed
    self.session.movingTargets = coverProstate.targets.approved

  def onFinishedStep(self):
    self.disableEditorWidgetAndResetEditorTool()
    if not self.session.data.usePreopData and not self.retryMode:
      self.createCoverProstateRegistrationResultManually()
      self.session.invokeEventForMostRecentEligibleSeries()
    else:
      self.session.onInvokeRegistration(initial=True, retryMode=self.retryMode)

  def disableEditorWidgetAndResetEditorTool(self, enabledButton=False):
    self.editorWidgetParent.hide()
    self.editorParameterNode.SetParameter('effect', 'DefaultTool')
    self.editorWidgetButton.setEnabled(enabledButton)

  def onStartTargetingButtonClicked(self):
    self.startTargetingButton.enabled = False
    self.setupFourUpView(self.session.currentSeriesVolume)
    self.fiducialsWidget.createNewFiducialNode(name="IntraopTargets")
    self.fiducialsWidget.startPlacing()

  def onFinishTargetingStepButtonClicked(self):
    self.fiducialsWidget.stopPlacing()
    if not slicer.util.confirmYesNoDisplay("Are you done setting targets and renaming them?"):
      return
    self.startTargetingButton.enabled = False
    self.finishTargetingButton.enabled = False
    self.session.movingTargets = self.fiducialsWidget.currentNode
    self.finishedSegmentationStepButton.setEnabled(1 if self.inputsAreSet() else 0)
    # self.setupPreopLoadedTargets()
    # self.hideAllTargets()

  def createCoverProstateRegistrationResultManually(self):
    fixedVolume = self.session.currentSeriesVolume
    result = self.session.generateNameAndCreateRegistrationResult(fixedVolume)
    approvedRegistrationType = "bSpline"
    result.targets.original = self.session.movingTargets
    targetName = str(result.seriesNumber) + '-TARGETS-' + approvedRegistrationType + result.suffix
    clone = self.logic.cloneFiducials(self.session.movingTargets, targetName)
    # self.logic.applyDefaultTargetDisplayNode(clone)
    result.setTargets(approvedRegistrationType, clone)
    result.volumes.fixed = fixedVolume
    result.labels.fixed = self.session.fixedLabel
    result.approve(approvedRegistrationType)

  def onTargetListModified(self, caller, event):
    self.finishTargetingButton.enabled = self.fiducialsWidget.currentNode is not None and \
                                         self.fiducialsWidget.currentNode.GetNumberOfFiducials()

  def setupSessionObservers(self):
    super(SliceTrackerSegmentationStep, self).setupSessionObservers()
    self.session.addEventObserver(self.session.InitiateSegmentationEvent, self.onInitiateSegmentation)

  def removeSessionEventObservers(self):
    super(SliceTrackerSegmentationStep, self).removeSessionEventObservers()
    self.session.removeEventObserver(self.session.InitiateSegmentationEvent, self.onInitiateSegmentation)

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def onSegmentationFinished(self, caller, event, labelNode):
    _, suffix = self.session.getRegistrationResultNameAndGeneratedSuffix(self.session.currentSeries)
    labelNode.SetName(labelNode.GetName() + suffix)
    self.session.fixedLabel = labelNode
    if self.session.data.usePreopData or self.retryMode:
      self.setAxialOrientation()
    self.openSegmentationComparisonStep()
    self.finishedSegmentationStepButton.setEnabled(1 if self.inputsAreSet() else 0)

  def openSegmentationComparisonStep(self):
    # self.hideAllLabels()
    # self.hideAllTargets()
    # self.removeMissingPreopDataAnnotation()
    if self.session.data.usePreopData or self.retryMode:
      self.layoutManager.setLayout(SliceTrackerConstants.LAYOUT_SIDE_BY_SIDE)
      self.setupScreenForSegmentationComparison("red", self.session.movingVolume, self.session.movingLabel)
      self.setupScreenForSegmentationComparison("yellow", self.session.fixedVolume, self.session.fixedLabel)
      self.setAxialOrientation()
      self.editorWidgetButton.setEnabled(True)
      self.centerLabelsOnVisibleSliceWidgets()
    elif not self.session.movingTargets:
      self.startTargetingButton.click()

  def setupScreenForSegmentationComparison(self, viewName, volume, label):
    compositeNode = getattr(self, viewName+"CompositeNode")
    compositeNode.SetReferenceBackgroundVolumeID(volume.GetID())
    compositeNode.SetLabelVolumeID(label.GetID())
    compositeNode.SetLabelOpacity(1)
    sliceNode = getattr(self, viewName+"SliceNode")
    sliceNode.RotateToVolumePlane(volume)
    sliceNode.SetUseLabelOutline(True)

  def centerLabelsOnVisibleSliceWidgets(self):
    for widget in self.getAllVisibleWidgets():
      compositeNode = widget.mrmlSliceCompositeNode()
      sliceNode = widget.sliceLogic().GetSliceNode()
      labelID = compositeNode.GetLabelVolumeID()
      if labelID:
        label =  slicer.mrmlScene.GetNodeByID(labelID)
        centroid = self.logic.getCentroidForLabel(label, self.session.segmentedLabelValue)
        if centroid:
          sliceNode.JumpSliceByCentering(centroid[0], centroid[1], centroid[2])

  def inputsAreSet(self):
    if self.session.data.usePreopData:
      return self.session.movingVolume is not None and self.session.fixedVolume is not None and \
             self.session.movingLabel is not None and self.session.fixedLabel is not None and \
             self.session.movingTargets is not None
    else:
      return self.session.fixedVolume is not None and self.session.fixedLabel is not None \
             and self.session.movingTargets is not None
