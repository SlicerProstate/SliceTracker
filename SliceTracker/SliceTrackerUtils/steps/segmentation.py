import os
import ast
import EditorLib
import qt
import slicer
import vtk
from Editor import EditorWidget
from base import SliceTrackerStepLogic, SliceTrackerStep
from VolumeClipToLabel import VolumeClipToLabelWidget
from SlicerProstateUtils.helpers import TargetCreationWidget
from ..constants import SliceTrackerConstants


class SliceTrackerSegmentationStepLogic(SliceTrackerStepLogic):

  def __init__(self):
    super(SliceTrackerSegmentationStepLogic, self).__init__()

  def cleanup(self):
    pass

  def getRegistrationResultNameAndGeneratedSuffix(self, name):
    nOccurrences = sum([1 for result in self.session.data.getResultsAsList() if name in result.name])
    suffix = ""
    if nOccurrences:
      suffix = "_Retry_" + str(nOccurrences)
    return name, suffix


class SliceTrackerSegmentationStep(SliceTrackerStep):

  NAME = "Segmentation"
  LogicClass = SliceTrackerSegmentationStepLogic

  def __init__(self):
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.MODULE_NAME)).replace(".py", "")
    super(SliceTrackerSegmentationStep, self).__init__()
    self.resetAndInitialize()

  def resetAndInitialize(self):
    self.retryMode = False

    self.fixedVolume = None
    self.movingVolume = None
    self.fixedLabel = None
    self.movingLabel = None

    self.targets = None

  def setup(self):
    self.setupIcons()
    try:
      import VolumeClipWithModel
    except ImportError:
      return slicer.util.warningDisplay("Error: Could not find extension VolumeClip. Open Slicer Extension Manager and "
                                        "install VolumeClip.", "Missing Extension")

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

    self.applyRegistrationButton = self.createButton("Apply Registration", icon=self.greenCheckIcon, iconSize=iconSize,
                                                     toolTip="Run Registration.")
    self.applyRegistrationButton.setFixedHeight(45)

    self.editorWidgetButton = self.createButton("", icon=self.settingsIcon, toolTip="Show Label Editor",
                                                enabled=False, iconSize=iconSize)

    self.setupEditorWidget()
    self.segmentationGroupBox = qt.QGroupBox()
    self.segmentationGroupBoxLayout = qt.QGridLayout()
    self.segmentationGroupBox.setLayout(self.segmentationGroupBoxLayout)
    self.volumeClipToLabelWidget.segmentationButtons.layout().addWidget(self.editorWidgetButton)
    self.segmentationGroupBoxLayout.addWidget(self.volumeClipGroupBox, 0, 0)
    self.segmentationGroupBoxLayout.addWidget(self.editorWidgetParent, 1, 0)
    self.segmentationGroupBoxLayout.addWidget(self.applyRegistrationButton, 2, 0)
    self.segmentationGroupBoxLayout.setRowStretch(3, 1)
    self.layout().addWidget(self.segmentationGroupBox)
    self.editorWidgetParent.hide()

    # TODO: control visibility of target settings table
    self.setupTargetingStepUIElements()

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
    self.finishTargetingButton.clicked.connect(self.onFinishTargetingStepButtonClicked)
    self.startTargetingButton.clicked.connect(self.onStartTargetingButtonClicked)

  def onStartTargetingButtonClicked(self):
    self.setupFourUpView(self.session.currentSeries)
    self.fiducialsWidget.createNewFiducialNode(name="IntraopTargets")
    self.fiducialsWidget.startPlacing()

  def onFinishTargetingStepButtonClicked(self):
    self.fiducialsWidget.stopPlacing()
    if not slicer.util.confirmYesNoDisplay("Are you done setting targets and renaming them?"):
      return
    self.session.data.initialTargets = self.fiducialsWidget.currentNode
    self.session.data.initialVolume = self.fixedVolumeSelector.currentNode()
    self.createCoverProstateRegistrationResultManually()
    # self.setupPreopLoadedTargets()
    # self.hideAllTargets()
    self.openOverviewStep()
    self.fiducialsWidget.reset()

  def createCoverProstateRegistrationResultManually(self):
    fixedVolume = self.logic.getOrCreateVolumeForSeries(self.session.currentSeries)
    result = self.generateNameAndCreateRegistrationResult(fixedVolume)
    approvedRegistrationType = "bSpline"
    result.targets.original = self.session.data.initialTargets
    targetName = str(result.seriesNumber) + '-TARGETS-' + approvedRegistrationType + result.suffix
    clone = self.logic.cloneFiducials(self.session.data.initialTargets, targetName)
    # self.logic.applyDefaultTargetDisplayNode(clone)
    result.setTargets(approvedRegistrationType, clone)
    result.volumes.fixed = fixedVolume
    result.labels.fixed = self.fixedLabelSelector.currentNode()
    result.approve(approvedRegistrationType)

  def generateNameAndCreateRegistrationResult(self, fixedVolume):
    name, suffix = self.getRegistrationResultNameAndGeneratedSuffix(fixedVolume.GetName())
    result = self.registrationResults.createResult(name + suffix)
    result.suffix = suffix
    self.registrationLogic.registrationResult = result
    return result

  def onTargetListModified(self, caller, event):
    self.finishTargetingButton.enabled = self.fiducialsWidget.currentNode is not None and \
                                         self.fiducialsWidget.currentNode.GetNumberOfFiducials()

  def setupSessionObservers(self):
    super(SliceTrackerSegmentationStep, self).setupSessionObservers()
    self.session.addEventObserver(self.session.InitiateSegmentationEvent, self.onInitiateSegmentation)

  def removeSessionEventObservers(self):
    super(SliceTrackerSegmentationStep, self).removeSessionEventObservers()
    self.session.removeEventObserver(self.session.InitiateSegmentationEvent, self.onInitiateSegmentation)

  @vtk.calldata_type(vtk.VTK_STRING)
  def onInitiateSegmentation(self, caller, event, callData):
    self.resetAndInitialize()
    # TODO: movingLabel and movingVolume need to be set here?
    self.retryMode = ast.literal_eval(callData)

    if self.getSetting("Cover_Prostate") in self.session.currentSeries:
      if self.session.data.usePreopData:
        self.movingLabel = self.session.data.initialLabel
        self.movingVolume = self.session.data.initialVolume
        self.targets = self.session.data.initialTargets
    else:
      coverProstate = self.data.getMostRecentApprovedCoverProstateRegistration()
      self.movingVolume = coverProstate.volumes.fixed
      self.movingLabel = coverProstate.labels.fixed
      self.targets = coverProstate.targets.approved
    self.active = True

  def onActivation(self):
    self.volumeClipToLabelWidget.logic.colorNode = self.session.mpReviewColorNode
    self.volumeClipToLabelWidget.onColorSelected(self.session.segmentedLabelValue)
    self.startTargetingButton.enabled = not self.session.data.usePreopData
    self.fixedVolume = self.logic.getOrCreateVolumeForSeries(self.session.currentSeries)
    if not self.fixedVolume:
      return
    # self.logic.currentIntraopVolume = volume
    # self.fixedVolumeSelector.setCurrentNode(self.logic.currentIntraopVolume)
    self.volumeClipToLabelWidget.imageVolumeSelector.setCurrentNode(self.fixedVolume)
    self.layoutManager.setLayout(SliceTrackerConstants.LAYOUT_FOUR_UP)
    self.setupFourUpView(self.fixedVolume)
    self.volumeClipToLabelWidget.quickSegmentationButton.click()
    self.volumeClipToLabelWidget.addEventObserver(self.volumeClipToLabelWidget.SegmentationFinishedEvent,
                                                  self.onSegmentationFinished)
    self.setDefaultOrientation()


  @vtk.calldata_type(vtk.VTK_OBJECT)
  def onSegmentationFinished(self, caller, event, labelNode):
    _, suffix = self.logic.getRegistrationResultNameAndGeneratedSuffix(self.session.currentSeries)
    labelNode.SetName(labelNode.GetName() + suffix)
    self.fixedLabel = labelNode
    if self.session.data.usePreopData or self.retryMode:
      self.setAxialOrientation()

    # self.fixedLabelSelector.setCurrentNode(labelNode)
    self.openSegmentationComparisonStep()

  def openSegmentationComparisonStep(self):
    # self.currentStep = self.STEP_SEGMENTATION_COMPARISON
    # self.hideAllLabels()
    # self.hideAllTargets()
    # self.removeMissingPreopDataAnnotation()
    if self.session.data.usePreopData or self.retryMode:
      self.layoutManager.setLayout(SliceTrackerConstants.LAYOUT_SIDE_BY_SIDE)

      if self.retryMode:
        coverProstateRegResult = self.registrationResults.getMostRecentApprovedCoverProstateRegistration()
        if coverProstateRegResult:
          self.movingVolume = coverProstateRegResult.fixedVolume
          self.movingLabel = coverProstateRegResult.fixedLabel
          self.targets = coverProstateRegResult.approvedTargets

      self.setupScreenForSegmentationComparison("red", self.movingVolume, self.movingLabel)
      self.setupScreenForSegmentationComparison("yellow", self.fixedVolume, self.fixedLabel)
      self.setAxialOrientation()
      self.applyRegistrationButton.setEnabled(1 if self.inputsAreSet() else 0)
      self.editorWidgetButton.setEnabled(True)
      self.centerLabelsOnVisibleSliceWidgets()
    else:
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
    return not (self.movingVolume is None and self.fixedVolume is None and
                self.movingLabel is None and self.fixedLabel is None and
                self.targets is None)
