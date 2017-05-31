import os
import ast
import qt
import slicer
import vtk
from base import SliceTrackerLogicBase, SliceTrackerStep
from SlicerDevelopmentToolboxUtils.helpers import SliceAnnotation
from SlicerDevelopmentToolboxUtils.decorators import onModuleSelected
from plugins.targeting import SliceTrackerTargetingPlugin
from plugins.segmentation.manual import SliceTrackerManualSegmentationPlugin
from plugins.segmentation.automatic import SliceTrackerAutomaticSegmentationPlugin
from ..constants import SliceTrackerConstants as constants


class SliceTrackerSegmentationStepLogic(SliceTrackerLogicBase):

  def __init__(self):
    super(SliceTrackerSegmentationStepLogic, self).__init__()


class SliceTrackerSegmentationStep(SliceTrackerStep):

  NAME = "Segmentation"
  LogicClass = SliceTrackerSegmentationStepLogic

  def __init__(self):
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.MODULE_NAME)).replace(".py", "")
    super(SliceTrackerSegmentationStep, self).__init__()
    self.resetAndInitialize()

  def resetAndInitialize(self):
    self.session.retryMode = False


  def setupIcons(self):
    self.finishStepIcon = self.createIcon('icon-start.png')
    self.backIcon = self.createIcon('icon-back.png')

  def setup(self):
    super(SliceTrackerSegmentationStep, self).setup()
    self.setupManualSegmentationPlugin()
    self.setupTargetingPlugin()
    self.setupAutomaticSegmentationPlugin()
    self.setupNavigationButtons()

  def setupTargetingPlugin(self):
    self.targetingPlugin = SliceTrackerTargetingPlugin()
    self.targetingPlugin.addEventObserver(self.targetingPlugin.TargetingStartedEvent, self.onTargetingStarted)
    self.targetingPlugin.addEventObserver(self.targetingPlugin.TargetingFinishedEvent, self.onTargetingFinished)
    self.addPlugin(self.targetingPlugin)
    self.layout().addWidget(self.targetingPlugin)

  def setupManualSegmentationPlugin(self):
    self.manualSegmentationPlugin = SliceTrackerManualSegmentationPlugin()
    self.manualSegmentationPlugin.addEventObserver(self.manualSegmentationPlugin.SegmentationStartedEvent,
                                                   self.onSegmentationStarted)
    self.manualSegmentationPlugin.addEventObserver(self.manualSegmentationPlugin.SegmentationCancelledEvent,
                                                   self.onSegmentationCancelled)
    self.manualSegmentationPlugin.addEventObserver(self.manualSegmentationPlugin.SegmentationFinishedEvent,
                                                   self.onSegmentationFinished)
    self.addPlugin(self.manualSegmentationPlugin)
    self.layout().addWidget(self.manualSegmentationPlugin)

  def setupAutomaticSegmentationPlugin(self):
    self.automaticSegmentationPlugin = SliceTrackerAutomaticSegmentationPlugin()
    self.automaticSegmentationPlugin.addEventObserver(self.automaticSegmentationPlugin.SegmentationStartedEvent,
                                                      self.onAutomaticSegmentationStarted)
    self.automaticSegmentationPlugin.addEventObserver(self.automaticSegmentationPlugin.SegmentationFinishedEvent,
                                                      self.onAutomaticSegmentationFinished)
    self.addPlugin(self.automaticSegmentationPlugin)
    # self.layout().addWidget(self.automaticSegmentationPlugin)

  def setupNavigationButtons(self):
    iconSize = qt.QSize(36, 36)
    self.backButton = self.createButton("", icon=self.backIcon, iconSize=iconSize,
                                        toolTip="Return to last step")
    self.finishStepButton = self.createButton("", icon=self.finishStepIcon, iconSize=iconSize,
                                              toolTip="Run Registration")
    self.finishStepButton.setFixedHeight(45)
    self.layout().addWidget(self.createHLayout([self.backButton, self.finishStepButton]))

  def setupConnections(self):
    super(SliceTrackerSegmentationStep, self).setupConnections()
    self.backButton.clicked.connect(self.onBackButtonClicked)
    self.finishStepButton.clicked.connect(self.onFinishStepButtonClicked)

  @vtk.calldata_type(vtk.VTK_STRING)
  def onInitiateSegmentation(self, caller, event, callData):
    self._initiateSegmentation(ast.literal_eval(callData))

  def _initiateSegmentation(self, retryMode=False):
    self.resetAndInitialize()
    self.session.retryMode = retryMode
    self.finishStepButton.setEnabled(1 if self.inputsAreSet() else 0)
    if self.session.seriesTypeManager.isCoverProstate(self.session.currentSeries):
      if self.session.data.usePreopData:
        if self.session.retryMode:
          if not self.loadLatestCoverProstateResultData():
            self.loadInitialData()
        else:
          self.loadInitialData()
      else:
        self.session.movingVolume = self.session.currentSeriesVolume
    else:
      self.loadLatestCoverProstateResultData()
    self.active = True

  def loadInitialData(self):
    self.session.movingLabel = self.session.data.initialLabel
    self.session.movingVolume = self.session.data.initialVolume
    self.session.movingTargets = self.session.data.initialTargets

  def onActivation(self):
    self.finishStepButton.enabled = False
    self.session.fixedVolume = self.session.currentSeriesVolume
    if not self.session.fixedVolume:
      return
    self.updateAvailableLayouts()
    super(SliceTrackerSegmentationStep, self).onActivation()

  def updateAvailableLayouts(self):
    layouts = [constants.LAYOUT_RED_SLICE_ONLY, constants.LAYOUT_FOUR_UP]
    if self.session.data.usePreopData or self.session.retryMode:
      layouts.append(constants.LAYOUT_SIDE_BY_SIDE)
    self.setAvailableLayouts(layouts)

  def onDeactivation(self):
    super(SliceTrackerSegmentationStep, self).onDeactivation()

  @onModuleSelected(SliceTrackerStep.MODULE_NAME)
  def onLayoutChanged(self, layout=None):
    if self.layoutManager.layout == constants.LAYOUT_SIDE_BY_SIDE:
      self.setupSideBySideSegmentationView()
    elif self.layoutManager.layout in [constants.LAYOUT_FOUR_UP, constants.LAYOUT_RED_SLICE_ONLY]:
      self.redCompositeNode.SetLabelVolumeID(None)
      self.removeMissingPreopDataAnnotation()
      self.setBackgroundToVolumeID(self.session.currentSeriesVolume.GetID(), clearLabels=False)

  def setupSideBySideSegmentationView(self):
    # TODO: red slice view should not be possible to set target
    coverProstate = self.session.data.getMostRecentApprovedCoverProstateRegistration()
    redVolume = coverProstate.volumes.fixed if coverProstate and self.session.retryMode else self.session.data.initialVolume
    redLabel = coverProstate.labels.fixed if coverProstate and self.session.retryMode else self.session.data.initialLabel

    if redVolume and redLabel:
      self.redCompositeNode.SetBackgroundVolumeID(redVolume.GetID())
      self.redCompositeNode.SetLabelVolumeID(redLabel.GetID())
      self.redCompositeNode.SetLabelOpacity(1)
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
    self.segmentationNoPreopAnnotation = SliceAnnotation(widget, constants.MISSING_PREOP_ANNOTATION_TEXT,
                                                         opacity=0.7, color=(1, 0, 0))

  def loadLatestCoverProstateResultData(self):
    coverProstate = self.session.data.getMostRecentApprovedCoverProstateRegistration()
    if coverProstate:
      self.session.movingVolume = coverProstate.volumes.fixed
      self.session.movingLabel = coverProstate.labels.fixed
      self.session.movingTargets = coverProstate.targets.approved
      return True
    return False

  def onBackButtonClicked(self):
    if self.session.retryMode:
      self.session.retryMode = False
    if self.session.previousStep:
      self.session.previousStep.active = True

  def onFinishStepButtonClicked(self):
    self.manualSegmentationPlugin.disableEditorWidgetButton()
    self.session.data.clippingModelNode = self.manualSegmentationPlugin.clippingModelNode
    self.session.data.inputMarkupNode = self.manualSegmentationPlugin.inputMarkupNode
    if not self.session.data.usePreopData and not self.session.retryMode:
      self.createCoverProstateRegistrationResultManually()
    else:
      self.session.onInvokeRegistration(initial=True, retryMode=self.session.retryMode)

  def createCoverProstateRegistrationResultManually(self):
    fixedVolume = self.session.currentSeriesVolume
    result = self.session.generateNameAndCreateRegistrationResult(fixedVolume)
    approvedRegistrationType = "bSpline"
    result.targets.original = self.session.movingTargets
    targetName = str(result.seriesNumber) + '-TARGETS-' + approvedRegistrationType + result.suffix
    clone = self.logic.cloneFiducials(self.session.movingTargets, targetName)
    self.session.applyDefaultTargetDisplayNode(clone)
    result.setTargets(approvedRegistrationType, clone)
    result.volumes.fixed = fixedVolume
    result.labels.fixed = self.session.fixedLabel
    result.approve(approvedRegistrationType)

  def setupSessionObservers(self):
    super(SliceTrackerSegmentationStep, self).setupSessionObservers()
    self.session.addEventObserver(self.session.InitiateSegmentationEvent, self.onInitiateSegmentation)

  def removeSessionEventObservers(self):
    super(SliceTrackerSegmentationStep, self).removeSessionEventObservers()
    self.session.removeEventObserver(self.session.InitiateSegmentationEvent, self.onInitiateSegmentation)

  def onAutomaticSegmentationStarted(self, caller, event):
    self.manualSegmentationPlugin.enabled = False
    self.onSegmentationStarted(caller, event)

  def onSegmentationStarted(self, caller, event):
    self.setAvailableLayouts([constants.LAYOUT_RED_SLICE_ONLY, constants.LAYOUT_SIDE_BY_SIDE, constants.LAYOUT_FOUR_UP])
    self.targetingPlugin.enabled = False
    self.backButton.enabled = False
    self.finishStepButton.enabled = False

  def onSegmentationCancelled(self, caller, event):
    self.setAvailableLayouts([constants.LAYOUT_FOUR_UP])
    self.layoutManager.setLayout(constants.LAYOUT_FOUR_UP)
    self.backButton.enabled = True
    self.targetingPlugin.enabled = True
    if self.inputsAreSet():
      self.openSegmentationComparisonStep()
    self.finishStepButton.setEnabled(1 if self.inputsAreSet() else 0) # TODO: need to revise that

  @vtk.calldata_type(vtk.VTK_STRING)
  def onNewImageSeriesReceived(self, caller, event, callData):
    # TODO: control here to automatically activate the step
    if not self.active:
      return
    newImageSeries = ast.literal_eval(callData)
    for series in reversed(newImageSeries):
      if self.session.seriesTypeManager.isCoverProstate(series):
        if series != self.session.currentSeries:
          if not slicer.util.confirmYesNoDisplay("Another %s was received. Do you want to use this one?"
                                                  % self.getSetting("COVER_PROSTATE")):
            return
          self.session.currentSeries = series
          self.active = False
          self._initiateSegmentation()
          return

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def onAutomaticSegmentationFinished(self, caller, event, labelNode):
    self.manualSegmentationPlugin.enabled = True
    self.onSegmentationFinished(caller, event, labelNode)

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def onSegmentationFinished(self, caller, event, labelNode):
    _, suffix = self.session.getRegistrationResultNameAndGeneratedSuffix(self.session.currentSeries)
    labelNode.SetName(labelNode.GetName() + suffix)
    self.session.fixedLabel = labelNode
    self.finishStepButton.setEnabled(1 if self.inputsAreSet() else 0)
    self.backButton.enabled = True
    self.openSegmentationComparisonStep()

  def openSegmentationComparisonStep(self):
    self.setAvailableLayouts([constants.LAYOUT_SIDE_BY_SIDE])
    self.manualSegmentationPlugin.enableEditorWidgetButton()
    if self.session.data.usePreopData or self.session.retryMode:
      self.setAxialOrientation()
    self.removeMissingPreopDataAnnotation()
    self.targetingPlugin.enabled = True
    if self.session.data.usePreopData or self.session.retryMode:
      self.layoutManager.setLayout(constants.LAYOUT_SIDE_BY_SIDE)
      self.setBackgroundAndLabelForCompositeNode("red", self.session.movingVolume, self.session.movingLabel)
      self.setBackgroundAndLabelForCompositeNode("yellow", self.session.fixedVolume, self.session.fixedLabel)
      self.centerLabelsOnVisibleSliceWidgets()
    elif not self.session.movingTargets:
      self.targetingPlugin.startTargeting()
    else:
      for compositeNode, sliceNode in zip(self._compositeNodes, self._sliceNodes):
        compositeNode.SetLabelVolumeID(self.session.fixedLabel.GetID())
        compositeNode.SetLabelOpacity(1)
        sliceNode.SetUseLabelOutline(True)

  def setBackgroundAndLabelForCompositeNode(self, viewName, volume, label):
    compositeNode = getattr(self, viewName+"CompositeNode")
    compositeNode.SetReferenceBackgroundVolumeID(volume.GetID())
    compositeNode.SetLabelVolumeID(label.GetID())
    compositeNode.SetLabelOpacity(1)
    sliceNode = getattr(self, viewName+"SliceNode")
    sliceNode.SetOrientationToAxial()
    sliceNode.RotateToVolumePlane(volume)
    sliceNode.SetUseLabelOutline(True)

  def centerLabelsOnVisibleSliceWidgets(self):
    for widget in self.getAllVisibleWidgets():
      compositeNode = widget.mrmlSliceCompositeNode()
      sliceNode = widget.sliceLogic().GetSliceNode()
      labelID = compositeNode.GetLabelVolumeID()
      if labelID:
        label = slicer.mrmlScene.GetNodeByID(labelID)
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

  def onTargetingStarted(self, caller, event):
    self.manualSegmentationPlugin.enabled = False
    self.backButton.enabled = False

  def onTargetingFinished(self, caller, event):
    self.finishStepButton.setEnabled(1 if self.inputsAreSet() else 0)
    self.manualSegmentationPlugin.enabled = True
    self.backButton.enabled = True