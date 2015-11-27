import os
import math, re, sys
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from Utils.mixins import ModuleWidgetMixin, ModuleLogicMixin
from Editor import EditorWidget
import SimpleITK as sitk
import sitkUtils
import EditorLib
import logging
from subprocess import Popen


class DICOMTAGS:

  PATIENT_NAME          = '0010,0010'
  PATIENT_ID            = '0010,0020'
  PATIENT_BIRTH_DATE    = '0010,0030'
  SERIES_DESCRIPTION    = '0008,103E'
  SERIES_NUMBER         = '0020,0011'
  STUDY_DATE            = '0008,0020'
  STUDY_TIME            = '0008,0030'
  ACQUISITION_TIME      = '0008,0032'


class COLOR:

  RED = qt.QColor(qt.Qt.red)
  YELLOW = qt.QColor(qt.Qt.yellow)
  GREEN = qt.QColor(qt.Qt.darkGreen)
  GRAY = qt.QColor(qt.Qt.gray)


class STYLE:

  GRAY_BACKGROUND_WHITE_FONT  = 'background-color: rgb(130,130,130); ' \
                                           'color: rgb(255,255,255)'
  WHITE_BACKGROUND            = 'background-color: rgb(255,255,255)'
  LIGHT_GRAY_BACKGROUND       = 'background-color: rgb(230,230,230)'
  ORANGE_BACKGROUND           = 'background-color: rgb(255,102,0)'
  YELLOW_BACKGROUND           = 'background-color: yellow;'
  GREEN_BACKGROUND            = 'background-color: green;'
  GRAY_BACKGROUND             = 'background-color: gray;'
  RED_BACKGROUND              = 'background-color: red;'


class SliceTracker(ScriptedLoadableModule):

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "SliceTracker"
    self.parent.categories = ["Radiology"]
    self.parent.dependencies = []
    self.parent.contributors = ["Peter Behringer (SPL), Christian Herz (SPL), Andriy Fedorov (SPL)"]
    self.parent.helpText = """ SliceTracker facilitates support of MRI-guided targeted prostate biopsy. """
    self.parent.acknowledgementText = """Surgical Planning Laboratory, Brigham and Women's Hospital, Harvard
                                          Medical School, Boston, USA This work was supported in part by the National
                                          Institutes of Health through grants U24 CA180918,
                                          R01 CA111288 and P41 EB015898."""


class SliceTrackerWidget(ScriptedLoadableModuleWidget, ModuleWidgetMixin):

  LEFT_VIEWER_SLICE_ANNOTATION_TEXT = 'BIOPSY PLAN'
  RIGHT_VIEWER_SLICE_ANNOTATION_TEXT = 'TRACKED TARGETS'
  APPROVED_RESULT_TEXT_ANNOTATION = "approved"
  REJECTED_RESULT_TEXT_ANNOTATION = "rejected"
  SKIPPED_RESULT_TEXT_ANNOTATION = "skipped"

  @property
  def registrationResults(self):
    return self.logic.registrationResults

  @property
  def currentResult(self):
    return self.registrationResults.activeResult

  @currentResult.setter
  def currentResult(self, series):
    self.registrationResults.activeResult = series

  @property
  def preopDataDir(self):
    return self.logic.preopDataDir

  @preopDataDir.setter
  def preopDataDir(self, path):
    self.logic.preopDataDir = path
    self.setSetting('PreopLocation', path)
    self.loadPreopData()
    self.intraopSeriesSelector.clear()
    self.intraopDirButton.setEnabled(True)
    self.trackTargetsButton.setEnabled(False)
    self._updateOutputDir()
    self.preopDirButton.text = self.preopDirButton.directory

  @property
  def intraopDataDir(self):
    return self.logic.intraopDataDir

  @intraopDataDir.setter
  def intraopDataDir(self, path):
    self.collapsibleDirectoryConfigurationArea.collapsed = True
    self.logic.setReceivedNewImageDataCallback(self.onNewImageDataReceived)
    self.logic.intraopDataDir = path
    self.setSetting('IntraopLocation', path)
    self.intraopDirButton.text = self.intraopDirButton.directory

  @property
  def outputDir(self):
    return self.logic.outputDir

  @outputDir.setter
  def outputDir(self, path):
    if os.path.exists(path):
      self._outputRoot = path
      self.setSetting('OutputLocation', path)
      self._updateOutputDir()
      self.caseCompletedButton.setEnabled(True)
      self.outputDirButton.text = self.outputDirButton.directory

  def __init__(self, parent=None):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    self.logic = SliceTrackerLogic()
    self.markupsLogic = slicer.modules.markups.logic()
    self.volumesLogic = slicer.modules.volumes.logic()
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.moduleName))
    self.iconPath = os.path.join(self.modulePath, 'Resources/Icons')
    self._outputRoot = None
    self.setupIcons()

  def onReload(self):
    ScriptedLoadableModuleWidget.onReload(self)
    slicer.mrmlScene.Clear(0)
    self.logic = SliceTrackerLogic()
    self.removeSliceAnnotations()

  def cleanup(self):
    ScriptedLoadableModuleWidget.cleanup(self)

  def _updateOutputDir(self):
    if self._outputRoot and self.patientID and self.currentStudyDate:
      time = qt.QTime().currentTime().toString().replace(":", "")
      dirName = self.patientID.text + "-biopsy-" + self.currentStudyDate.text + time
      self.logic.outputDir = os.path.join(self._outputRoot, dirName, "MRgBiopsy")

  def createPatientWatchBox(self):
    self.patientWatchBox, patientViewBoxLayout = self._createWatchBox(maximumHeight=90)

    self.patientID = qt.QLabel('None')
    self.patientName = qt.QLabel('None')
    self.patientBirthDate = qt.QLabel('None')
    self.preopStudyDate = qt.QLabel('None')
    self.currentStudyDate = qt.QLabel('None')

    patientViewBoxLayout.addWidget(self.createHLayout([qt.QLabel('Patient ID: '), self.patientID], margin=1))
    patientViewBoxLayout.addWidget(self.createHLayout([qt.QLabel('Patient Name: '), self.patientName], margin=1))
    patientViewBoxLayout.addWidget(self.createHLayout([qt.QLabel('Date of Birth: '), self.patientBirthDate], margin=1))
    patientViewBoxLayout.addWidget(self.createHLayout([qt.QLabel('Preop Study Date: '), self.preopStudyDate], margin=1))
    patientViewBoxLayout.addWidget(self.createHLayout([qt.QLabel('Current Study Date: '), self.currentStudyDate], margin=1))

  def createRegistrationWatchBox(self):
    self.registrationWatchBox, registrationWatchBoxLayout = self._createWatchBox(maximumHeight=40)
    self.currentRegisteredSeries = qt.QLabel('None')
    self.registrationSettingsButton = self.createButton("", icon=self.settingsIcon, styleSheet="border:none;",
                                                        maximumWidth=16)
    self.registrationSettingsButton.setCursor(qt.Qt.PointingHandCursor)
    registrationWatchBoxLayout.addWidget(self.createHLayout([qt.QLabel('Current Series:'), self.currentRegisteredSeries,
                                                             self.registrationSettingsButton], margin=1))
    self.registrationWatchBox.hide()

  def _createWatchBox(self, maximumHeight):
    watchBox = qt.QGroupBox()
    watchBox.maximumHeight = maximumHeight
    watchBox.setStyleSheet(STYLE.LIGHT_GRAY_BACKGROUND)
    watchBoxLayout = qt.QGridLayout()
    watchBox.setLayout(watchBoxLayout)
    self.layout.addWidget(watchBox)
    return watchBox, watchBoxLayout

  def setupIcons(self):
    self.cancelSegmentationIcon = self.createIcon('icon-cancelSegmentation.png')
    self.greenCheckIcon = self.createIcon('icon-greenCheck.png')
    self.quickSegmentationIcon = self.createIcon('icon-quickSegmentation.png')
    self.newImageDataIcon = self.createIcon('icon-newImageData.png')
    self.littleDiscIcon = self.createIcon('icon-littleDisc.png')
    self.settingsIcon = self.createIcon('icon-settings.png')
    self.undoIcon = self.createIcon('icon-undo.png')
    self.redoIcon = self.createIcon('icon-redo.png')

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    try:
      import VolumeClipWithModel
    except ImportError:
      return self.warningDialog("Error: Could not find extension VolumeClip. Open Slicer Extension Manager and install "
                                "VolumeClip.", "Missing Extension")

    self.ratingWindow = RatingWindow(maximumValue=5)
    self.seriesItems = []
    self.revealCursor = None
    self.currentTargets = None

    self.logic.retryMode = False

    self.createPatientWatchBox()
    self.createRegistrationWatchBox()

    self.setupSliceWidgets()
    self.setupTargetingStepUIElements()
    self.setupSegmentationUIElements()
    self.setupRegistrationStepUIElements()
    self.setupEvaluationStepUIElements()

    self.setupConnections()

    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)
    self.setAxialOrientation()

    self.showAcceptRegistrationWarning = False

    # TODO: should be fixed when we are sure, that there will not be any old versions of mpReview
    colorFile = os.path.join(self.modulePath,'Resources/Colors/PCampReviewColors.csv')
    if not os.path.exists(colorFile):
      colorFile = os.path.join(self.modulePath,'Resources/Colors/mpReviewColors.csv')
    self.logic.setupColorTable(colorFile=colorFile)
    self.layout.addStretch()

  def setupSliceWidgets(self):
    self.setupRedSliceWidget()
    self.setupYellowSliceWidget()
    self.setupGreenSliceWidget()

  def setupRedSliceWidget(self):
    self.redWidget = self.layoutManager.sliceWidget('Red')
    self.redCompositeNode = self.redWidget.mrmlSliceCompositeNode()
    self.redSliceView = self.redWidget.sliceView()
    self.redSliceLogic = self.redWidget.sliceLogic()
    self.redSliceNode = self.redSliceLogic.GetSliceNode()
    self.redFOV = []

  def setupYellowSliceWidget(self):
    self.yellowWidget = self.layoutManager.sliceWidget('Yellow')
    self.yellowCompositeNode = self.yellowWidget.mrmlSliceCompositeNode()
    self.yellowSliceLogic = self.yellowWidget.sliceLogic()
    self.yellowSliceView = self.yellowWidget.sliceView()
    self.yellowSliceNode = self.yellowSliceLogic.GetSliceNode()
    self.yellowFOV = []

  def setupGreenSliceWidget(self):
    self.greenWidget = self.layoutManager.sliceWidget('Green')
    self.greenCompositeNode = self.greenWidget.mrmlSliceCompositeNode()
    self.greenSliceLogic = self.greenWidget.sliceLogic()
    self.greenSliceNode = self.greenSliceLogic.GetSliceNode()

  def setDefaultOrientation(self):
    self.redSliceNode.SetOrientationToAxial()
    self.yellowSliceNode.SetOrientationToSagittal()
    self.greenSliceNode.SetOrientationToCoronal()

  def setAxialOrientation(self):
    self.redSliceNode.SetOrientationToAxial()
    self.yellowSliceNode.SetOrientationToAxial()
    self.greenSliceNode.SetOrientationToAxial()

  def setupTargetingStepUIElements(self):
    self.targetingGroupBox = qt.QGroupBox()
    self.targetingGroupBoxLayout = qt.QGridLayout()
    self.targetingGroupBox.setLayout(self.targetingGroupBoxLayout)

    self.preopDirButton = self.createDirectoryButton(text="Preop Directory", caption="Choose Preop Location",
                                                     directory=self.getSetting('PreopLocation'))
    self.outputDirButton = self.createDirectoryButton(caption="Choose Data Output Location")
    self.intraopDirButton = self.createDirectoryButton(text="Intraop Directory", caption="Choose Intraop Location",
                                                       directory=self.getSetting('IntraopLocation'), enabled=False)

    self.trackTargetsButton = self.createButton("Track targets", toolTip="Track targets", enabled=False)
    self.caseCompletedButton = self.createButton('Case completed', enabled=os.path.exists(self.getSetting('OutputLocation')))
    self.setupTargetsTable()
    self.setupIntraopSeriesSelector()
    self.outputDirButton.directory = self.getSetting('OutputLocation')
    self._outputRoot = self.outputDirButton.directory
    self.caseCompletedButton.setEnabled(self._outputRoot is not None)

    self.collapsibleDirectoryConfigurationArea = ctk.ctkCollapsibleButton()
    self.collapsibleDirectoryConfigurationArea.text = "Directory Settings"
    self.directoryConfigurationLayout = qt.QGridLayout(self.collapsibleDirectoryConfigurationArea)
    self.directoryConfigurationLayout.addWidget(self.preopDirButton, 1, 0, 1, qt.QSizePolicy.ExpandFlag)
    self.directoryConfigurationLayout.addWidget(self.createHelperLabel("Please select the mpReview preprocessed preop "
                                                                       "data here."), 1, 1, 1, 1, qt.Qt.AlignRight)
    self.directoryConfigurationLayout.addWidget(self.outputDirButton, 2, 0, 1, qt.QSizePolicy.ExpandFlag)
    self.directoryConfigurationLayout.addWidget(self.createHelperLabel("Please select the output directory where all "
                                                                       "data will be saved"), 2, 1, 1, 1, qt.Qt.AlignRight)
    self.directoryConfigurationLayout.addWidget(self.intraopDirButton, 3, 0, 1, qt.QSizePolicy.ExpandFlag)
    self.directoryConfigurationLayout.addWidget(self.createHelperLabel("Please select the intraop directory where new "
                                                                       "DICOM data will be arriving during the biopsy")
                                                , 3, 1, 1, 1, qt.Qt.AlignRight)

    self.targetingGroupBoxLayout.addWidget(self.collapsibleDirectoryConfigurationArea, 0, 0)
    self.targetingGroupBoxLayout.addWidget(self.targetTable, 1, 0)
    self.targetingGroupBoxLayout.addWidget(self.intraopSeriesSelector, 2, 0)
    self.targetingGroupBoxLayout.addWidget(self.trackTargetsButton, 3, 0)
    self.targetingGroupBoxLayout.addWidget(self.caseCompletedButton, 4, 0)
    self.layout.addWidget(self.targetingGroupBox)

  def createHelperLabel(self, toolTipText=""):
    helperPixmap = qt.QPixmap(os.path.join(self.iconPath, 'icon-infoBox.png'))
    helperPixmap = helperPixmap.scaled(qt.QSize(20, 20))
    label = self.createLabel("", pixmap=helperPixmap, toolTip=toolTipText)
    label.setCursor(qt.Qt.PointingHandCursor)
    return label

  def setupTargetsTable(self):
    self.targetTable = qt.QTableWidget()
    self.targetTable.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
    self.targetTable.maximumHeight = 150
    self.clearTargetTable()

  def setupIntraopSeriesSelector(self):
    self.intraopSeriesSelector = qt.QComboBox()
    self.seriesModel = qt.QStandardItemModel()
    self.intraopSeriesSelector.setModel(self.seriesModel)

  def setupSegmentationUIElements(self):
    iconSize = qt.QSize(70, 30)

    self.referenceVolumeSelector = self.createComboBox(nodeTypes=["vtkMRMLScalarVolumeNode", ""], noneEnabled=True,
                                                       selectNodeUponCreation=True, showChildNodeTypes=False)
    self.quickSegmentationButton = self.createButton('Quick Mode', icon=self.quickSegmentationIcon, iconSize=iconSize,
                                                     styleSheet=STYLE.WHITE_BACKGROUND)
    self.applySegmentationButton = self.createButton("", icon=self.greenCheckIcon, iconSize=iconSize,
                                                     styleSheet=STYLE.WHITE_BACKGROUND, enabled=False)
    self.cancelSegmentationButton = self.createButton("", icon=self.cancelSegmentationIcon,
                                                      iconSize=iconSize, enabled=False)
    self.backButton = self.createButton("", icon=self.undoIcon, iconSize=iconSize, enabled=False)
    self.forwardButton = self.createButton("", icon=self.redoIcon, iconSize=iconSize, enabled=False)

    self.applyRegistrationButton = self.createButton("Apply Registration", icon=self.greenCheckIcon,
                                                     toolTip="Run Registration.")
    self.applyRegistrationButton.setFixedHeight(45)

    self.editorWidgetButton = self.createButton("", icon=self.settingsIcon, toolTip="Show Label Editor",
                                                enabled=False)

    segmentationButtons = self.setupSegmentationButtonBox()
    self.setupEditorWidget()

    self.segmentationGroupBox = qt.QGroupBox()
    self.segmentationGroupBoxLayout = qt.QFormLayout()
    self.segmentationGroupBox.setLayout(self.segmentationGroupBoxLayout)
    self.segmentationGroupBoxLayout.addWidget(self.createHLayout([segmentationButtons, self.editorWidgetButton]))
    self.segmentationGroupBoxLayout.addRow(self.editorWidgetParent)
    self.segmentationGroupBoxLayout.addRow(self.applyRegistrationButton)
    self.segmentationGroupBox.hide()
    self.editorWidgetParent.hide()

  def setupSegmentationButtonBox(self):
    segmentationButtons = qt.QDialogButtonBox()
    segmentationButtons.setLayoutDirection(1)
    segmentationButtons.centerButtons = False
    segmentationButtons.addButton(self.forwardButton, segmentationButtons.ActionRole)
    segmentationButtons.addButton(self.backButton, segmentationButtons.ActionRole)
    segmentationButtons.addButton(self.cancelSegmentationButton, segmentationButtons.ActionRole)
    segmentationButtons.addButton(self.applySegmentationButton, segmentationButtons.ActionRole)
    segmentationButtons.addButton(self.quickSegmentationButton, segmentationButtons.ActionRole)
    return segmentationButtons

  def setupEditorWidget(self):
    self.editorWidgetParent = slicer.qMRMLWidget()
    self.editorWidgetParent.setLayout(qt.QVBoxLayout())
    self.editorWidgetParent.setMRMLScene(slicer.mrmlScene)
    self.editUtil = EditorLib.EditUtil.EditUtil()
    self.editorWidget = EditorWidget(parent=self.editorWidgetParent, showVolumesFrame=False)
    self.editorWidget.setup()
    self.editorParameterNode = self.editUtil.getParameterNode()

  def setupRegistrationStepUIElements(self):
    self.registrationGroupBox = qt.QGroupBox()
    self.registrationGroupBoxLayout = qt.QFormLayout()
    self.registrationGroupBox.setLayout(self.registrationGroupBoxLayout)
    self.preopVolumeSelector = self.createComboBox(nodeTypes=["vtkMRMLScalarVolumeNode", ""], showChildNodeTypes=False,
                                                   selectNodeUponCreation=True, toolTip="Pick algorithm input.")
    self.preopLabelSelector = self.createComboBox(nodeTypes=["vtkMRMLLabelMapVolumeNode", ""], showChildNodeTypes=False,
                                                  selectNodeUponCreation=False, toolTip="Pick algorithm input.")
    self.intraopVolumeSelector = self.createComboBox(nodeTypes=["vtkMRMLScalarVolumeNode", ""], noneEnabled=True,
                                                     showChildNodeTypes=False, selectNodeUponCreation=True,
                                                     toolTip="Pick algorithm input.")
    self.intraopLabelSelector = self.createComboBox(nodeTypes=["vtkMRMLLabelMapVolumeNode", ""],
                                                    showChildNodeTypes=False,
                                                    selectNodeUponCreation=True, toolTip="Pick algorithm input.")
    self.fiducialSelector = self.createComboBox(nodeTypes=["vtkMRMLMarkupsFiducialNode", ""], noneEnabled=True,
                                                showChildNodeTypes=False, selectNodeUponCreation=False,
                                                toolTip="Select the Targets")
    self.registrationGroupBoxLayout.addRow("Preop Image Volume: ", self.preopVolumeSelector)
    self.registrationGroupBoxLayout.addRow("Preop Label Volume: ", self.preopLabelSelector)
    self.registrationGroupBoxLayout.addRow("Intraop Image Volume: ", self.intraopVolumeSelector)
    self.registrationGroupBoxLayout.addRow("Intraop Label Volume: ", self.intraopLabelSelector)
    self.registrationGroupBoxLayout.addRow("Targets: ", self.fiducialSelector)
    self.registrationGroupBox.hide()

  def setupEvaluationStepUIElements(self):
    self.registrationEvaluationGroupBox = qt.QGroupBox()
    self.registrationEvaluationGroupBoxLayout = qt.QGridLayout()
    self.registrationEvaluationGroupBox.setLayout(self.registrationEvaluationGroupBoxLayout)
    self.registrationEvaluationGroupBox.hide()

    self.setupCollapsibleRegistrationArea()
    self.setupRegistrationValidationButtons()
    self.needleTipButton = qt.QPushButton('Set needle-tip')
    self.registrationEvaluationGroupBoxLayout.addWidget(self.registrationGroupBox, 1, 0)
    self.registrationEvaluationGroupBoxLayout.addWidget(self.segmentationGroupBox, 2, 0)
    self.registrationEvaluationGroupBoxLayout.addWidget(self.collapsibleRegistrationArea, 3, 0)
    self.registrationEvaluationGroupBoxLayout.addWidget(self.evaluationButtonsGroupBox, 5, 0)
    # self.targetingGroupBoxLayout.addWidget(self.needleTipButton)
    self.layout.addWidget(self.registrationEvaluationGroupBox)

  def setupRegistrationValidationButtons(self):
    self.approveRegistrationResultButton = self.createButton("Approve Result")
    self.retryRegistrationButton = self.createButton("Retry")
    self.skipRegistrationResultButton = self.createButton("Skip Result")
    self.rejectRegistrationResultButton = self.createButton("Reject Result")
    self.evaluationButtonsGroupBox = self.createHLayout([self.skipRegistrationResultButton, self.retryRegistrationButton,
                                                         self.approveRegistrationResultButton, self.rejectRegistrationResultButton])
    self.evaluationButtonsGroupBox.enabled = False

  def setupCollapsibleRegistrationArea(self):
    self.collapsibleRegistrationArea = ctk.ctkCollapsibleButton()
    self.collapsibleRegistrationArea.text = "Registration Results"
    self.registrationGroupBoxDisplayLayout = qt.QFormLayout(self.collapsibleRegistrationArea)

    #TODO: selector should be used to show only registrations (retried) of the current series
    self.resultSelector = ctk.ctkComboBox()
    self.resultSelector.setFixedWidth(250)
    self.registrationResultAlternatives = self.createHLayout([qt.QLabel('Alternative Registration Result'), self.resultSelector])
    self.registrationGroupBoxDisplayLayout.addWidget(self.registrationResultAlternatives)

    self.showRigidResultButton = self.createButton('Rigid')
    self.showAffineResultButton = self.createButton('Affine')
    self.showBSplineResultButton = self.createButton('BSpline')

    self.registrationButtonGroup = qt.QButtonGroup()
    self.registrationButtonGroup.addButton(self.showRigidResultButton, 1)
    self.registrationButtonGroup.addButton(self.showAffineResultButton, 2)
    self.registrationButtonGroup.addButton(self.showBSplineResultButton, 3)

    self.registrationGroupBoxDisplayLayout.addWidget(
      self.createHLayout([self.showRigidResultButton, self.showAffineResultButton, self.showBSplineResultButton]))

    self.setupVisualEffectsUIElements()
    self.registrationGroupBoxDisplayLayout.addWidget(self.visualEffectsGroupBox)

  def setupVisualEffectsUIElements(self):
    self.fadeSlider = ctk.ctkSliderWidget()
    self.fadeSlider.minimum = 0
    self.fadeSlider.maximum = 1.0
    self.fadeSlider.value = 0
    self.fadeSlider.singleStep = 0.05

    self.rockCount = 0
    self.rockTimer = qt.QTimer()
    self.rockTimer.setInterval(50)
    self.rockCheckBox = qt.QCheckBox("Rock")
    self.rockCheckBox.checked = False

    self.flickerTimer = qt.QTimer()
    self.flickerTimer.setInterval(400)
    self.flickerCheckBox = qt.QCheckBox("Flicker")
    self.flickerCheckBox.checked = False

    self.animaHolderLayout = self.createVLayout([self.rockCheckBox, self.flickerCheckBox])
    self.revealCursorCheckBox = qt.QCheckBox("Use RevealCursor")
    self.revealCursorCheckBox.checked = False

    self.visualEffectsGroupBox = qt.QGroupBox("Visual Evaluation")
    self.visualEffectsGroupBoxLayout = qt.QFormLayout(self.visualEffectsGroupBox)
    self.visualEffectsGroupBoxLayout.addWidget(self.createHLayout([qt.QLabel('Opacity'), self.fadeSlider,
                                                                   self.animaHolderLayout]))
    self.visualEffectsGroupBoxLayout.addRow("", self.revealCursorCheckBox)

  def setupConnections(self):

    def setupButtonConnections():
      self.preopDirButton.directorySelected.connect(lambda: setattr(self, "preopDataDir", self.preopDirButton.directory))
      self.outputDirButton.directorySelected.connect(lambda: setattr(self, "outputDir", self.outputDirButton.directory))
      self.intraopDirButton.directorySelected.connect(lambda: setattr(self, "intraopDataDir", self.intraopDirButton.directory))
      self.forwardButton.clicked.connect(self.onForwardButtonClicked)
      self.backButton.clicked.connect(self.onBackButtonClicked)
      self.editorWidgetButton.clicked.connect(self.onEditorGearIconClicked)
      self.applyRegistrationButton.clicked.connect(lambda: self.onInvokeRegistration(initial=True))
      # self.needleTipButton.clicked.connect(self.onNeedleTipButtonClicked)
      self.quickSegmentationButton.clicked.connect(self.onQuickSegmentationButtonClicked)
      self.cancelSegmentationButton.clicked.connect(self.onCancelSegmentationButtonClicked)
      self.trackTargetsButton.clicked.connect(self.onTrackTargetsButtonClicked)
      self.applySegmentationButton.clicked.connect(self.onApplySegmentationButtonClicked)
      self.approveRegistrationResultButton.clicked.connect(self.onApproveRegistrationResultButtonClicked)
      self.skipRegistrationResultButton.clicked.connect(self.onSkipRegistrationResultButtonClicked)
      self.rejectRegistrationResultButton.clicked.connect(self.onRejectRegistrationResultButtonClicked)
      self.retryRegistrationButton.clicked.connect(self.onRetryRegistrationButtonClicked)
      self.caseCompletedButton.clicked.connect(self.onSaveDataButtonClicked)
      self.registrationSettingsButton.clicked.connect(self.showRegistrationDetails)
      self.registrationButtonGroup.connect('buttonClicked(int)', self.onRegistrationButtonChecked)

    def setupSelectorConnections():
      self.resultSelector.connect('currentIndexChanged(QString)', self.onRegistrationResultSelected)
      self.intraopSeriesSelector.connect('currentIndexChanged(QString)', self.onIntraopSeriesSelectionChanged)
      # self.preopVolumeSelector.connect('currentNodeChanged(bool)', self.setupScreenAfterSegmentation)
      # self.intraopVolumeSelector.connect('currentNodeChanged(bool)', self.setupScreenAfterSegmentation)
      # self.intraopLabelSelector.connect('currentNodeChanged(bool)', self.setupScreenAfterSegmentation)
      # self.preopLabelSelector.connect('currentNodeChanged(bool)', self.setupScreenAfterSegmentation)
      # self.fiducialSelector.connect('currentNodeChanged(bool)', self.setupScreenAfterSegmentation)

    def setupCheckBoxConnections():
      self.rockCheckBox.connect('toggled(bool)', self.onRockToggled)
      self.flickerCheckBox.connect('toggled(bool)', self.onFlickerToggled)
      self.revealCursorCheckBox.connect('toggled(bool)', self.revealToggled)

    def setupOtherConnections():
      self.fadeSlider.connect('valueChanged(double)', self.changeOpacity)
      self.rockTimer.connect('timeout()', self.onRockToggled)
      self.flickerTimer.connect('timeout()', self.onFlickerToggled)
      self.targetTable.connect('clicked(QModelIndex)', self.jumpToTarget)

    setupCheckBoxConnections()
    setupButtonConnections()
    setupSelectorConnections()
    setupOtherConnections()

  def showRegistrationDetails(self):
    if self.registrationGroupBox.visible:
      self.registrationGroupBox.hide()
      self.registrationGroupBox.enabled = True
    else:
      self.registrationGroupBox.show()
      self.registrationGroupBox.enabled = False

  def onRegistrationButtonChecked(self, buttonId):
    self.hideAllTargets()
    if buttonId == 1:
      self.onRigidResultClicked()
    elif buttonId == 2:
      if not self.currentResult.affineTargets:
        return self.onRegistrationButtonChecked(3)
      self.onAffineResultClicked()
    elif buttonId == 3:
      self.onBSplineResultClicked()
    self.activeRegistrationResultButtonId = buttonId

  def deactivateUndoRedoButtons(self):
    self.forwardButton.setEnabled(0)
    self.backButton.setEnabled(0)

  def updateUndoRedoButtons(self, observer=None, caller=None):
    self.forwardButton.setEnabled(self.deletedMarkups.GetNumberOfFiducials() > 0)
    self.backButton.setEnabled(self.logic.inputMarkupNode.GetNumberOfFiducials() > 0)

  def onIntraopSeriesSelectionChanged(self, selectedSeries=None):
    self.removeSliceAnnotations()
    if not selectedSeries:
      return
    seriesNumber = self.logic.getSeriesNumberFromString(selectedSeries)
    trackingPossible = self.logic.isTrackingPossible(seriesNumber)
    self.trackTargetsButton.setEnabled(trackingPossible and
                                       (self.registrationResults.getMostRecentApprovedCoverProstateRegistration() or
                                        "COVER PROSTATE" in selectedSeries))
    if not trackingPossible:
      self.configureColorsAndViewersForSelectedIntraopSeries(selectedSeries)
    self.setIntraopSeriesSelectorColorAndSliceAnnotations(selectedSeries, trackingPossible)

  def setIntraopSeriesSelectorColorAndSliceAnnotations(self, selectedSeries, trackingPossible):
    style = STYLE.YELLOW_BACKGROUND
    if not trackingPossible:
      seriesNumber = self.logic.getSeriesNumberFromString(selectedSeries)
      if self.registrationResults.registrationResultWasApproved(seriesNumber):
        style = STYLE.GREEN_BACKGROUND
        annotationText = self.APPROVED_RESULT_TEXT_ANNOTATION
      elif self.registrationResults.registrationResultWasSkipped(seriesNumber):
        style = STYLE.RED_BACKGROUND
        annotationText = self.SKIPPED_RESULT_TEXT_ANNOTATION
      else:
        style = STYLE.GRAY_BACKGROUND
        annotationText = self.REJECTED_RESULT_TEXT_ANNOTATION
      # TODO Positioning....
      self.rightViewerRegistrationResultStatusAnnotation = self._createTextActor(self.yellowSliceView, annotationText,
                                                                                 fontSize=20, xPos=0, yPos=25)
    self.intraopSeriesSelector.setStyleSheet(style)

  def configureColorsAndViewersForSelectedIntraopSeries(self, selectedSeries):
    seriesNumber = self.logic.getSeriesNumberFromString(selectedSeries)
    if self.registrationResults.registrationResultWasApproved(seriesNumber):
      self.showRegistrationResultSideBySideForSelectedSeries(selectedSeries)
    elif self.registrationResults.registrationResultWasSkipped(seriesNumber):
      self.showRegistrationResultSideBySideForSelectedSeries(selectedSeries)
    else:
      result = self.registrationResults.getResultsBySeriesNumber(seriesNumber)[0]
      self.setupScreenForDisplayingSeries(result.fixedVolume)

  def uncheckVisualEffects(self):
    self.flickerCheckBox.checked = False
    self.rockCheckBox.checked = False
    self.revealCursorCheckBox.checked = False

  def setupScreenForDisplayingSeries(self, volume):
    self.disableTargetTable()
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)
    self.redCompositeNode.Reset()
    self.redCompositeNode.SetBackgroundVolumeID(volume.GetID())
    self.setDefaultOrientation()
    slicer.app.applicationLogic().FitSliceToAll()

  def showRegistrationResultSideBySideForSelectedSeries(self, selectedSeries):
    self.targetTable.enabled = True
    seriesNumber = self.logic.getSeriesNumberFromString(self.intraopSeriesSelector.currentText)
    for result in self.registrationResults.getResultsBySeriesNumber(seriesNumber):
      if result.approved or result.skipped:
        self.setupRegistrationResultView()
        self.onRegistrationResultSelected(result.name)
        break

  def jumpToTarget(self, modelIndex=None):
    if not modelIndex:
      try:
        modelIndex = self.targetTable.selectedIndexes()[0]
      except IndexError:
        self.targetTable.selectRow(0)
        modelIndex = self.targetTable.selectedIndexes()[0]
    row = modelIndex.row()
    if not self.currentTargets:
      self.currentTargets = self.preopTargets
    self.markupsLogic.SetAllMarkupsVisibility(self.currentTargets, True)
    self.jumpSliceNodeToTarget(self.redSliceNode, self.preopTargets, row)
    self.jumpSliceNodeToTarget(self.yellowSliceNode, self.currentTargets, row)

  def jumpSliceNodeToTarget(self, sliceNode, targetNode, n):
    point = [0,0,0,0]
    targetNode.GetMarkupPointWorld(n, 0, point)
    sliceNode.JumpSlice(point[0], point[1], point[2])

  def updateRegistrationResultSelector(self):
    self.resultSelector.clear()
    results = self.registrationResults.getResultsBySeriesNumber(self.currentResult.seriesNumber)
    for result in reversed(results):
      self.resultSelector.addItem(result.name)
    self.registrationResultAlternatives.visible = len(results) > 1

  def onNeedleTipButtonClicked(self):
    self.needleTipButton.enabled = False
    self.logic.setNeedleTipPosition(destinationViewNode=self.yellowSliceNode, callback=self.updateTargetTable)
    self.clearTargetTable()
    self.needleTipButton.enabled = False

  def clearTargetTable(self):
    self.targetTable.clear()
    # TODO: change for needle tip
    # self.targetTable.setColumnCount(3)
    self.targetTable.setColumnCount(1)
    self.targetTable.setHorizontalHeaderLabels(['Targets']) #, 'Needle-tip distance 2D [mm]', 'Needle-tip distance 3D [mm]'])
    self.targetTable.horizontalHeader().setResizeMode(qt.QHeaderView.Stretch)

  def updateTargets(self, targets):
    self.clearTargetTable()
    number_of_targets = targets.GetNumberOfFiducials()
    self.targetTable.setRowCount(number_of_targets)
    for target in range(number_of_targets):
      targetText = targets.GetNthFiducialLabel(target)
      # TODO: change for needle tip
      for idx, item in enumerate([qt.QTableWidgetItem(targetText)]): #, qt.QTableWidgetItem(""), qt.QTableWidgetItem("")]):
        item.setFlags(qt.Qt.ItemIsSelectable | qt.Qt.ItemIsEnabled)
        self.targetTable.setItem(target, idx, item)

  def updateTargetTable(self, observer=None, caller=None):
    bSplineTargets = self.currentResult.bSplineTargets
    number_of_targets = bSplineTargets.GetNumberOfFiducials()
    self.updateTargets(bSplineTargets)

    needleTip_position, target_positions = self.logic.getNeedleTipAndTargetsPositions(bSplineTargets)

    # if len(needleTip_position) > 0:
    #   for index in range(number_of_targets):
    #     distance2D = self.logic.getNeedleTipTargetDistance2D(target_positions[index], needleTip_position)
    #     text_for_2D_column = ('x = ' + str(round(distance2D[0], 2)) + ' y = ' + str(round(distance2D[1], 2)))
    #     item_2D = qt.QTableWidgetItem(text_for_2D_column)
    #     self.targetTable.setItem(index, 1, item_2D)
    #     logging.debug(str(text_for_2D_column))
    #
    #     distance3D = self.logic.getNeedleTipTargetDistance3D(target_positions[index], needleTip_position)
    #     text_for_3D_column = str(round(distance3D, 2))
    #     item_3D = qt.QTableWidgetItem(text_for_3D_column)
    #     item_3D.setFlags(qt.Qt.ItemIsSelectable | qt.Qt.ItemIsEnabled)
    #     self.targetTable.setItem(index, 2, item_3D)
    #     logging.debug(str(text_for_3D_column))
    #
    # self.needleTipButton.enabled = True

  def removeSliceAnnotations(self):
    try:
      redRenderer = self.redSliceView.renderWindow().GetRenderers().GetItemAsObject(0)
      redRenderer.RemoveActor(self.leftViewerAnnotation)
      yellowRenderer = self.yellowSliceView.renderWindow().GetRenderers().GetItemAsObject(0)
      yellowRenderer.RemoveActor(self.rightViewerAnnotation)
      yellowRenderer.RemoveActor(self.rightViewerRegistrationResultStatusAnnotation)
    except:
      pass
    finally:
      self.redSliceView.update()
      self.yellowSliceView.update()

  def addSliceAnnotations(self, fontSize=30):
    self.removeSliceAnnotations()
    self.leftViewerAnnotation = self._createTextActor(self.redSliceView, self.LEFT_VIEWER_SLICE_ANNOTATION_TEXT, fontSize)
    self.rightViewerAnnotation = self._createTextActor(self.yellowSliceView, self.RIGHT_VIEWER_SLICE_ANNOTATION_TEXT, fontSize)
    self.rightViewerRegistrationResultStatusAnnotation = None

  def _createTextActor(self, sliceView, text, fontSize, xPos=-90, yPos=50):
    textActor = vtk.vtkTextActor()
    textActor.SetInput(text)
    textProperty = textActor.GetTextProperty()
    textProperty.SetFontSize(fontSize)
    textProperty.SetColor(1, 0, 0)
    textProperty.SetBold(1)
    textProperty.SetShadow(1)
    textActor.SetTextProperty(textProperty)
    textActor.SetDisplayPosition(int(sliceView.width * 0.5 + xPos), yPos)
    renderer = sliceView.renderWindow().GetRenderers().GetItemAsObject(0)
    renderer.AddActor(textActor)
    sliceView.update()
    return textActor

  def onForwardButtonClicked(self):
    numberOfDeletedTargets = self.deletedMarkups.GetNumberOfFiducials()
    logging.debug(('numberOfTargets in deletedMarkups is' + str(numberOfDeletedTargets)))
    pos = [0.0, 0.0, 0.0]

    if numberOfDeletedTargets > 0:
      self.deletedMarkups.GetNthFiducialPosition(numberOfDeletedTargets - 1, pos)

    logging.debug(('deletedMarkups.position = ' + str(pos)))

    if pos == [0.0, 0.0, 0.0]:
      logging.debug('pos was 0,0,0 -> go on')
    else:
      self.logic.inputMarkupNode.AddFiducialFromArray(pos)

      # delete it in deletedMarkups
      self.deletedMarkups.RemoveMarkup(numberOfDeletedTargets - 1)

    self.updateUndoRedoButtons()

  def onBackButtonClicked(self):
    activeFiducials = self.logic.inputMarkupNode
    numberOfTargets = activeFiducials.GetNumberOfFiducials()
    logging.debug('numberOfTargets is' + str(numberOfTargets))
    pos = [0.0, 0.0, 0.0]
    activeFiducials.GetNthFiducialPosition(numberOfTargets - 1, pos)
    logging.debug('activeFiducials.position = ' + str(pos))

    if numberOfTargets > 0:
      self.deletedMarkups.GetNthFiducialPosition(numberOfTargets - 1, pos)

    activeFiducials.GetNthFiducialPosition(numberOfTargets - 1, pos)
    logging.debug('POS BEFORE ENTRY = ' + str(pos))
    if pos == [0.0, 0.0, 0.0]:
      logging.debug('pos was 0,0,0 -> go on')
    else:
      # add it to deletedMarkups
      activeFiducials.GetNthFiducialPosition(numberOfTargets - 1, pos)
      # logging.debug(('pos = '+str(pos))
      self.deletedMarkups.AddFiducialFromArray(pos)
      logging.debug('added Markup with position ' + str(pos) + ' to the deletedMarkupsList')
      # delete it in activeFiducials
      activeFiducials.RemoveMarkup(numberOfTargets - 1)

    self.updateUndoRedoButtons()

  def revealToggled(self, checked):
    if self.revealCursor:
      self.revealCursor.tearDown()
    if checked:
      import CompareVolumes
      self.revealCursor = CompareVolumes.LayerReveal()

  def onRockToggled(self):

    def startRocking():
      self.flickerCheckBox.setEnabled(False)
      self.rockTimer.start()
      self.fadeSlider.value = 0.5 + math.sin(self.rockCount / 10.) / 2.
      self.rockCount += 1

    def stopRocking():
      self.flickerCheckBox.setEnabled(True)
      self.rockTimer.stop()
      self.fadeSlider.value = 0.0

    if self.rockCheckBox.checked:
      startRocking()
    else:
      stopRocking()

  def onFlickerToggled(self):

    def startFlickering():
      self.rockCheckBox.setEnabled(False)
      self.flickerTimer.start()
      self.fadeSlider.value = 1.0 if self.fadeSlider.value == 0.0 else 0.0

    def stopFlickering():
      self.rockCheckBox.setEnabled(True)
      self.flickerTimer.stop()
      self.fadeSlider.value = 0.0

    if self.flickerCheckBox.checked:
      startFlickering()
    else:
      stopFlickering()

  def onSaveDataButtonClicked(self):
    return self.notificationDialog(self.logic.save())

  def configureSegmentationMode(self):
    self.applyRegistrationButton.setEnabled(False)

    self.removeSliceAnnotations()

    self.referenceVolumeSelector.setCurrentNode(self.logic.currentIntraopVolume)
    self.intraopVolumeSelector.setCurrentNode(self.logic.currentIntraopVolume)

    self.quickSegmentationButton.setEnabled(self.referenceVolumeSelector.currentNode() is not None)

    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    self.redCompositeNode.Reset()
    # TODO: Display targets or not?
    # self.setTargetVisibility(self.preopTargets, show=False)
    self.redCompositeNode.SetBackgroundVolumeID(self.logic.currentIntraopVolume.GetID())

    self.setDefaultOrientation()
    slicer.app.applicationLogic().FitSliceToAll()

    self.onQuickSegmentationButtonClicked()

  def inputsAreSet(self):
    return not (self.preopVolumeSelector.currentNode() is None and self.intraopVolumeSelector.currentNode() is None and
                self.preopLabelSelector.currentNode() is None and self.intraopLabelSelector.currentNode() is None and
                self.fiducialSelector.currentNode() is None)

  def updateCurrentPatientAndViewBox(self, currentFile):
    self.currentID = self.logic.getDICOMValue(currentFile, DICOMTAGS.PATIENT_ID)
    self.patientID.setText(self.currentID)

    def updatePreopStudyDate():
      preopStudyDateDICOM = self.logic.getDICOMValue(currentFile, DICOMTAGS.STUDY_DATE)
      formattedDate = preopStudyDateDICOM[0:4] + "-" + preopStudyDateDICOM[4:6] + "-" + \
                      preopStudyDateDICOM[6:8]
      self.preopStudyDate.setText(formattedDate)

    def updateCurrentStudyDate():
      currentStudyDate = qt.QDate().currentDate()
      self.currentStudyDate.setText(str(currentStudyDate))

    def updatePatientBirthdate():
      currentBirthDateDICOM = self.logic.getDICOMValue(currentFile, DICOMTAGS.PATIENT_BIRTH_DATE)
      if currentBirthDateDICOM is None:
        self.patientBirthDate.setText('No Date found')
      else:
        # convert date of birth from 19550112 (yyyymmdd) to 1955-01-12
        currentBirthDateDICOM = str(currentBirthDateDICOM)
        self.currentBirthDate = currentBirthDateDICOM[0:4] + "-" + currentBirthDateDICOM[
                                                                   4:6] + "-" + currentBirthDateDICOM[6:8]
        self.patientBirthDate.setText(self.currentBirthDate)

    def updatePatientName():
      self.currentPatientName = None
      currentPatientNameDICOM = self.logic.getDICOMValue(currentFile, DICOMTAGS.PATIENT_NAME)
      # convert patient name from XXXX^XXXX to XXXXX, XXXXX
      if currentPatientNameDICOM:
        splitted = currentPatientNameDICOM.split('^')
        try:
          self.currentPatientName = splitted[1] + ", " + splitted[0]
        except IndexError:
          self.currentPatientName = splitted[0]
      self.patientName.setText(self.currentPatientName)

    updatePatientBirthdate()
    updateCurrentStudyDate()
    updatePreopStudyDate()
    updatePatientName()

  def updateSeriesSelectorTable(self):
    self.intraopSeriesSelector.clear()
    seriesList = self.logic.seriesList
    for series in seriesList:
      sItem = qt.QStandardItem(series)
      self.seriesItems.append(sItem)
      self.seriesModel.appendRow(sItem)
      color = COLOR.YELLOW
      seriesNumber = self.logic.getSeriesNumberFromString(series)
      if self.registrationResults.registrationResultWasApproved(seriesNumber):
        color = COLOR.GREEN
      elif self.registrationResults.registrationResultWasSkipped(seriesNumber):
        color = COLOR.RED
      elif self.registrationResults.registrationResultWasRejected(seriesNumber):
        color = COLOR.GRAY
      self.seriesModel.setData(sItem.index(), color, qt.Qt.BackgroundRole)

    substring = "GUIDANCE"
    if not self.registrationResults.getMostRecentApprovedCoverProstateRegistration():
      substring = "COVER PROSTATE"

    for item in list(reversed(range(len(seriesList)))):
      series = self.seriesModel.item(item).text()
      if substring in series:
        index = self.intraopSeriesSelector.findText(series)
        self.intraopSeriesSelector.setCurrentIndex(index)
        break
    self.onIntraopSeriesSelectionChanged()

  def resetShowResultButtons(self, checkedButton):
    checked = STYLE.GRAY_BACKGROUND_WHITE_FONT
    unchecked = STYLE.WHITE_BACKGROUND
    for button in self.registrationButtonGroup.buttons():
      button.setStyleSheet(checked if button is checkedButton else unchecked)

  def onRegistrationResultSelected(self, seriesText):
    if seriesText:
      self.hideAllTargets()
      self.currentResult = seriesText
      self.showAffineResultButton.setEnabled("GUIDANCE" not in seriesText)
      self.onRegistrationButtonChecked(self.activeRegistrationResultButtonId)
      self.updateTargetTable()

  def hideAllTargets(self):
    for result in self.registrationResults.getResultsAsList():
      for targetNode in [targets for targets in result.targets.values() if targets]:
        self.setTargetVisibility(targetNode, show=False)
    self.setTargetVisibility(self.preopTargets, show=False)

  def onRigidResultClicked(self):
    self.displayRegistrationResults(button=self.showRigidResultButton, registrationType='rigid')

  def onAffineResultClicked(self):
    self.displayRegistrationResults(button=self.showAffineResultButton, registrationType='affine')

  def onBSplineResultClicked(self):
    self.displayRegistrationResults(button=self.showBSplineResultButton, registrationType='bSpline')

  def displayRegistrationResults(self, button, registrationType):
    self.resetShowResultButtons(checkedButton=button)
    self.setCurrentRegistrationResultSliceViews(registrationType)
    self.showTargets(registrationType=registrationType)
    self.visualEffectsGroupBox.setEnabled(True)
    self.jumpToTarget()

  def setDefaultFOV(self, sliceLogic):
    sliceLogic.FitSliceToAll()
    FOV = sliceLogic.GetSliceNode().GetFieldOfView()
    self.setFOV(sliceLogic, [FOV[0] * 0.5, FOV[1] * 0.5, FOV[2]])

  def setFOV(self, sliceLogic, FOV):
    sliceNode = sliceLogic.GetSliceNode()
    sliceLogic.StartSliceNodeInteraction(2)
    sliceNode.SetFieldOfView(FOV[0], FOV[1], FOV[2])
    sliceLogic.EndSliceNodeInteraction()

  def setCurrentRegistrationResultSliceViews(self, registrationType):
    self.redCompositeNode.SetBackgroundVolumeID(self.preopVolume.GetID())
    self.redCompositeNode.SetForegroundVolumeID(None)
    self.yellowCompositeNode.SetForegroundVolumeID(self.currentResult.fixedVolume.GetID())
    self.yellowCompositeNode.SetBackgroundVolumeID(self.currentResult.getVolume(registrationType).GetID())
    self.setDefaultFOV(self.redSliceLogic)
    self.setDefaultFOV(self.yellowSliceLogic)

  def showTargets(self, registrationType):
    self.setTargetVisibility(self.currentResult.rigidTargets, show=registrationType == 'rigid')
    self.setTargetVisibility(self.currentResult.bSplineTargets, show=registrationType == 'bSpline')
    if self.currentResult.affineTargets:
      self.setTargetVisibility(self.currentResult.affineTargets, show=registrationType == 'affine')
    self.currentTargets = getattr(self.currentResult, registrationType+'Targets')
    self.setTargetVisibility(self.preopTargets)

  def setTargetVisibility(self, targetNode, show=True):
    self.markupsLogic.SetAllMarkupsVisibility(targetNode, show)

  def simulateDataIncome(self, imagePath):
    # TODO: when module ready, remove this method
    # copy DICOM Files into intraop folder
    cmd = ('cp -a ' + imagePath + '. ' + self.intraopDataDir)
    logging.debug(cmd)
    os.system(cmd)

  def configureSliceNodesForPreopData(self):
    for nodeId in ["vtkMRMLSliceNodeRed", "vtkMRMLSliceNodeYellow", "vtkMRMLSliceNodeGreen"]:
      slicer.mrmlScene.GetNodeByID(nodeId).SetUseLabelOutline(True)
    self.redSliceNode.SetOrientationToAxial()

  def loadT2Label(self):
    mostRecentFilename = self.logic.getMostRecentWholeGlantSegmentation(self.preopSegmentationPath)
    success = False
    if mostRecentFilename:
      filename = os.path.join(self.preopSegmentationPath, mostRecentFilename)
      (success, self.preopLabel) = slicer.util.loadLabelVolume(filename, returnNode=True)
      if success:
        self.preopLabel.SetName('t2-label')
        displayNode = self.preopLabel.GetDisplayNode()
        displayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNode1')
        # rotate volume to plane
        for nodeId in ["vtkMRMLSliceNodeRed", "vtkMRMLSliceNodeYellow", "vtkMRMLSliceNodeGreen"]:
          slicer.mrmlScene.GetNodeByID(nodeId).RotateToVolumePlane(self.preopLabel)
        self.preopLabelSelector.setCurrentNode(self.preopLabel)
    return success

  def loadPreopVolume(self):
    success, self.preopVolume = slicer.util.loadVolume(self.preopImagePath, returnNode=True)
    if success:
      self.preopVolume.SetName('volume-PREOP')
      self.preopVolumeSelector.setCurrentNode(self.preopVolume)
    return success

  def loadPreopTargets(self):
    mostRecentTargets = self.logic.getMostRecentTargetsFile(self.preopTargetsPath)
    success = False
    if mostRecentTargets:
      filename = os.path.join(self.preopTargetsPath, mostRecentTargets)
      success, self.preopTargets = slicer.util.loadMarkupsFiducialList(filename, returnNode=True)
      if success:
        self.preopTargets.SetName('targets-PREOP')
    return success

  def loadMpReviewProcessedData(self):
    #TODO: should be moved to logic or better use logic from mpReview
    resourcesDir = os.path.join(self.preopDataDir, 'RESOURCES')
    self.preopTargetsPath = os.path.join(self.preopDataDir, 'Targets')

    if not os.path.exists(resourcesDir):
      self.confirmDialog("The selected directory does not fit the mpReview directory structure. Make sure that you "
                         "select the study root directory which includes directories RESOURCES")
      return False

    self.seriesMap = {}

    self.patientInformationRetrieved = False

    for root, subdirs, files in os.walk(resourcesDir):
      logging.debug('Root: ' + root + ', files: ' + str(files))
      resourceType = os.path.split(root)[1]

      logging.debug('Resource: ' + resourceType)

      if resourceType == 'Reconstructions':
        for f in files:
          logging.debug('File: ' + f)
          if f.endswith('.xml'):
            metaFile = os.path.join(root, f)
            logging.debug('Ends with xml: ' + metaFile)
            try:
              (seriesNumber, seriesName) = self.logic.getSeriesInfoFromXML(metaFile)
              logging.debug(str(seriesNumber) + ' ' + seriesName)
            except:
              logging.debug('Failed to get from XML')
              continue

            volumePath = os.path.join(root, seriesNumber + '.nrrd')
            self.seriesMap[seriesNumber] = {'MetaInfo': None, 'NRRDLocation': volumePath, 'LongName': seriesName}
            self.seriesMap[seriesNumber]['ShortName'] = str(seriesNumber) + ":" + seriesName
      elif resourceType == 'DICOM' and not self.patientInformationRetrieved:
        self.logic.importStudy(root)
        for f in files:
          self.updateCurrentPatientAndViewBox(os.path.join(root, f))
          self.patientInformationRetrieved = True
          break

    logging.debug('All series found: ' + str(self.seriesMap.keys()))
    logging.debug('All series found: ' + str(self.seriesMap.values()))

    logging.debug('******************************************************************************')

    self.preopImagePath = ''
    self.preopSegmentationPath = ''
    self.preopSegmentations = []

    for series in self.seriesMap:
      seriesName = str(self.seriesMap[series]['LongName'])
      logging.debug('series Number ' + series + ' ' + seriesName)
      if re.search("ax", str(seriesName), re.IGNORECASE) and re.search("t2", str(seriesName), re.IGNORECASE):
        logging.debug(' FOUND THE SERIES OF INTEREST, ITS ' + seriesName)
        logging.debug(' LOCATION OF VOLUME : ' + str(self.seriesMap[series]['NRRDLocation']))

        path = os.path.join(self.seriesMap[series]['NRRDLocation'])
        logging.debug(' LOCATION OF IMAGE path : ' + str(path))

        segmentationPath = os.path.dirname(os.path.dirname(path))
        segmentationPath = os.path.join(segmentationPath, 'Segmentations')
        logging.debug(' LOCATION OF SEGMENTATION path : ' + segmentationPath)

        if not os.path.exists(segmentationPath):
          self.confirmDialog("No segmentations found.\nMake sure that you used mpReview for segmenting the prostate "
                             "first and using its output as the preop data input here.")
          return False
        self.preopImagePath = self.seriesMap[series]['NRRDLocation']
        self.preopSegmentationPath = segmentationPath

        self.preopSegmentations = os.listdir(segmentationPath)

        logging.debug(str(self.preopSegmentations))

        break

    return True

  def loadPreopData(self):
    # TODO: using decorators
    if not self.loadMpReviewProcessedData():
      return
    self.configureSliceNodesForPreopData()
    if not self.loadT2Label() or not self.loadPreopVolume() or not self.loadPreopTargets():
      self.warningDialog("Loading preop data failed.\nMake sure that the correct directory structure like mpReview "
                         "explains is used. SliceTracker expects a volume, label and target")
      self.intraopDirButton.setEnabled(False)
      return
    else:
      self.intraopDirButton.setEnabled(True)
    if self.yesNoDialog("Was an endorectal coil used for preop image acquisition?"):
      progress = self.makeProgressIndicator(2, 1)
      progress.labelText = '\nBias Correction'
      self.preopVolume = self.logic.applyBiasCorrection(self.preopVolume, self.preopLabel)
      progress.setValue(2)
      progress.close()
      self.preopVolumeSelector.setCurrentNode(self.preopVolume)
      self.logic.biasCorrectionDone = True
    else:
      self.logic.biasCorrectionDone = False
    logging.debug('TARGETS PREOP')
    logging.debug(self.preopTargets)

    self.setTargetVisibility(self.preopTargets, show=True)
    self.updateTargets(self.preopTargets)

    # set markups for registration
    self.fiducialSelector.setCurrentNode(self.preopTargets)

    # jump to first markup slice
    self.markupsLogic.JumpSlicesToNthPointInMarkup(self.preopTargets.GetID(), 0)

    # Set Fiducial Properties
    markupsDisplayNode = self.preopTargets.GetDisplayNode()
    markupsDisplayNode.SetTextScale(1.9)
    markupsDisplayNode.SetGlyphScale(1.0)

    self.redCompositeNode.SetLabelOpacity(1)

    # set Layout to redSliceViewOnly
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    self.setDefaultFOV(self.redSliceLogic)

  def patientCheckAfterImport(self, fileList):
    for currentFile in fileList:
      currentFile = os.path.join(self.intraopDataDir, currentFile)
      patientID = self.logic.getDICOMValue(currentFile, DICOMTAGS.PATIENT_ID)
      if patientID != self.currentID and patientID is not None:
        if not self.yesNoDialog(message='WARNING: Preop data of Patient ID ' + self.currentID + ' was selected, but '
                                        ' data of patient with ID ' + patientID + ' just arrived in the income folder.'
                                        '\nDo you still want to continue?',
                                title="Patients Not Matching"):
          self.updateSeriesSelectorTable()
          return
        else:
          break
    self.updateSeriesSelectorTable()

  def onCancelSegmentationButtonClicked(self):
    if self.yesNoDialog("Do you really want to cancel the segmentation process?"):
      self.setQuickSegmentationModeOFF()

  def onQuickSegmentationButtonClicked(self):
    self.hideAllLabels()
    self.setBackgroundToCurrentReferenceVolume()
    self.setQuickSegmentationModeON()

  def setBackgroundToCurrentReferenceVolume(self):
    self.redCompositeNode.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())
    self.yellowCompositeNode.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())
    self.greenCompositeNode.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())

  def hideAllLabels(self):
    for compositeNode in [self.redCompositeNode, self.yellowCompositeNode, self.greenCompositeNode]:
      compositeNode.SetLabelVolumeID(None)

  def setQuickSegmentationModeON(self):
    self.logic.deleteClippingData()
    self.setSegmentationButtons(segmentationActive=True)
    self.deactivateUndoRedoButtons()
    self.disableEditorWidgetAndResetEditorTool()
    self.setupQuickModeHistory()
    self.logic.runQuickSegmentationMode()
    self.logic.inputMarkupNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.updateUndoRedoButtons)

  def disableEditorWidgetAndResetEditorTool(self, enabledButton=False):
    self.editorWidgetParent.hide()
    self.editorParameterNode.SetParameter('effect', 'DefaultTool')
    self.editorWidgetButton.setEnabled(enabledButton)

  def setQuickSegmentationModeOFF(self):
    self.setSegmentationButtons(segmentationActive=False)
    self.deactivateUndoRedoButtons()
    self.resetToRegularViewMode()

  def setSegmentationButtons(self, segmentationActive=False):
    self.quickSegmentationButton.setEnabled(not segmentationActive)
    self.applySegmentationButton.setEnabled(segmentationActive)
    self.cancelSegmentationButton.setEnabled(segmentationActive)

  def setupQuickModeHistory(self):
    try:
      self.deletedMarkups.Reset()
    except AttributeError:
      self.deletedMarkups = slicer.vtkMRMLMarkupsFiducialNode()
      self.deletedMarkups.SetName('deletedMarkups')

  def resetToRegularViewMode(self):
    interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
    interactionNode.SwitchToViewTransformMode()
    interactionNode.SetPlaceModePersistence(0)

  def changeOpacity(self, value):
    self.yellowCompositeNode.SetForegroundOpacity(value)

  def openEvaluationStep(self):
    self.currentRegisteredSeries.setText(self.logic.currentIntraopVolume.GetName())
    self.targetingGroupBox.hide()
    self.registrationEvaluationGroupBoxLayout.addWidget(self.targetTable, 4, 0)
    self.registrationEvaluationGroupBox.show()

  def openTargetingStep(self, ratingResult=None):
    self.activeRegistrationResultButtonId = 3
    self.hideAllLabels()
    if ratingResult:
      self.currentResult.score = ratingResult
    self.registrationWatchBox.hide()
    self.updateSeriesSelectorTable()
    self.registrationEvaluationGroupBox.hide()
    self.targetingGroupBoxLayout.addWidget(self.targetTable, 1, 0)
    self.targetingGroupBox.show()
    self.removeSliceAnnotations()
    self.uncheckVisualEffects()

  def onApproveRegistrationResultButtonClicked(self):
    self.currentResult.approve()

    if self.ratingWindow.isRatingEnabled():
      self.ratingWindow.show(disableWidget=self.parent, callback=self.openTargetingStep)
    else:
      self.openTargetingStep()

  def onSkipRegistrationResultButtonClicked(self):
    self.currentResult.skip()
    self.openTargetingStep()

  def onRejectRegistrationResultButtonClicked(self):
    results = self.registrationResults.getResultsBySeriesNumber(self.currentResult.seriesNumber)
    for result in results:
      result.reject()
    self.openTargetingStep()

  def updateRegistrationEvaluationButtons(self):
    results = self.registrationResults.getResultsBySeriesNumber(self.currentResult.seriesNumber)
    self.rejectRegistrationResultButton.setEnabled(len(results) > 1)
    self.skipRegistrationResultButton.setEnabled(len(results) == 1)

  def onApplySegmentationButtonClicked(self):
    self.setAxialOrientation()
    self.onQuickSegmentationFinished()

  def onQuickSegmentationFinished(self):
    inputVolume = self.referenceVolumeSelector.currentNode()
    continueSegmentation = False
    if self.logic.inputMarkupNode.GetNumberOfFiducials() > 3 and self.validPointsForQuickModeSet():

      self.currentIntraopLabel = self.logic.labelMapFromClippingModel(inputVolume)
      labelName = self.referenceVolumeSelector.currentNode().GetName() + '-label'
      self.currentIntraopLabel.SetName(labelName)

      displayNode = self.currentIntraopLabel.GetDisplayNode()
      displayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNode1')

      self.intraopLabelSelector.setCurrentNode(self.currentIntraopLabel)

      self.setTargetVisibility(self.logic.inputMarkupNode, show=False)
      self.logic.clippingModelNode.SetDisplayVisibility(False)
      self.setupScreenAfterSegmentation()
    else:
      if self.yesNoDialog("You need to set at least three points with an additional one situated on a distinct slice "
                          "as the algorithm input in order to be able to create a proper segmentation. This step is "
                          "essential for an efficient registration. Do you want to continue using the quick mode?"):
        continueSegmentation = True
      else:
        self.logic.deleteClippingData()
    if not continueSegmentation:
      self.setQuickSegmentationModeOFF()
      self.setSegmentationButtons(segmentationActive=False)

  def validPointsForQuickModeSet(self):
    positions = self.getMarkupSlicePositions()
    return min(positions) != max(positions)

  def getMarkupSlicePositions(self):
    markupNode = self.logic.inputMarkupNode
    nOfControlPoints = markupNode.GetNumberOfFiducials()
    positions = []
    pos = [0, 0, 0]
    for i in range(nOfControlPoints):
      markupNode.GetNthFiducialPosition(i, pos)
      positions.append(pos[2])
    return positions

  def setupScreenAfterSegmentation(self):
    self.hideAllLabels()
    self.hideAllTargets()
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView)

    if self.logic.retryMode:
      coverProstateRegResult = self.registrationResults.getMostRecentApprovedCoverProstateRegistration()
      if coverProstateRegResult:
        self.preopVolumeSelector.setCurrentNode(coverProstateRegResult.fixedVolume)
        self.preopLabelSelector.setCurrentNode(coverProstateRegResult.fixedLabel)
        self.fiducialSelector.setCurrentNode(coverProstateRegResult.bSplineTargets)

    preopVolume = self.preopVolumeSelector.currentNode()
    preopLabel = self.preopLabelSelector.currentNode()
    intraopVolume = self.intraopVolumeSelector.currentNode()
    intraopLabel = self.intraopLabelSelector.currentNode()

    self.setupScreenForSegmentationComparison("red", preopVolume, preopLabel)
    self.setupScreenForSegmentationComparison("yellow", intraopVolume, intraopLabel)
    self.applyRegistrationButton.setEnabled(1 if self.inputsAreSet() else 0)
    self.editorWidgetButton.setEnabled(True)
    self.registrationWatchBox.show()

  def setupScreenForSegmentationComparison(self, viewName, volume, label):
    compositeNode = getattr(self, viewName+"CompositeNode")
    compositeNode.SetReferenceBackgroundVolumeID(volume.GetID())
    compositeNode.SetLabelVolumeID(label.GetID())
    compositeNode.SetLabelOpacity(1)
    logic = getattr(self, viewName+"SliceLogic")
    logic.GetSliceNode().RotateToVolumePlane(volume)
    logic.FitSliceToAll()
    logic.GetSliceNode().SetFieldOfView(86, 136, 3.5)

  def onTrackTargetsButtonClicked(self):
    if self.currentResult is None or \
       self.registrationResults.getMostRecentApprovedCoverProstateRegistration() is None or \
       self.logic.retryMode or "COVER PROSTATE" in self.intraopSeriesSelector.currentText:
      self.initiateOrRetryTracking()
    else:
      self.repeatRegistrationForCurrentSelection()
    self.openEvaluationStep()

  def initiateOrRetryTracking(self):
    self.logic.loadSeriesIntoSlicer(self.intraopSeriesSelector.currentText, clearOldSeries=True)
    self.disableTargetTable()
    self.segmentationGroupBox.show()
    self.editorWidgetButton.setEnabled(False)
    self.activateRegistrationResultsArea(collapsed=True, enabled=False)
    self.registrationWatchBox.hide()
    self.configureSegmentationMode()

  def activateRegistrationResultsArea(self, collapsed, enabled):
    self.collapsibleRegistrationArea.collapsed = collapsed
    self.collapsibleRegistrationArea.enabled = enabled

  def disableTargetTable(self):
    self.hideAllTargets()
    self.targetTable.clearSelection()
    self.targetTable.enabled = False

  def repeatRegistrationForCurrentSelection(self):
    logging.debug('Performing Re-Registration')
    self.logic.loadSeriesIntoSlicer(self.intraopSeriesSelector.currentText)
    self.onInvokeRegistration(initial=False)
    self.segmentationGroupBox.hide()
    self.activateRegistrationResultsArea(collapsed=False, enabled=True)

  def onEditorGearIconClicked(self):
    if self.editorWidgetParent.visible:
      self.disableEditorWidgetAndResetEditorTool(enabledButton=True)
    else:
      self.editorWidgetParent.show()
      displayNode = self.currentIntraopLabel.GetDisplayNode()
      displayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNode1')
      self.editorParameterNode.SetParameter('effect', 'DrawEffect')
      self.editUtil.setLabel(8)
      self.editUtil.setLabelOutline(1)

  def onInvokeRegistration(self, initial=True):
    self.disableEditorWidgetAndResetEditorTool()
    self.applyRegistrationButton.setEnabled(False)
    self.progress = self.makeProgressIndicator(4, 1)
    if initial:
      self.logic.applyInitialRegistration(fixedVolume=self.intraopVolumeSelector.currentNode(),
                                          sourceVolume=self.preopVolumeSelector.currentNode(),
                                          fixedLabel=self.intraopLabelSelector.currentNode(),
                                          movingLabel=self.preopLabelSelector.currentNode(),
                                          targets=self.fiducialSelector.currentNode(),
                                          progressCallback=self.updateProgressBar)
    else:
      self.logic.applyRegistration(progressCallback=self.updateProgressBar)
    self.progress.close()
    self.progress = None
    self.finalizeRegistrationStep()
    self.registrationGroupBox.hide()
    logging.debug('Re-Registration is done')

  def updateProgressBar(self, **kwargs):
    if self.progress:
      for key, value in kwargs.iteritems():
        if hasattr(self.progress, key):
          setattr(self.progress, key, value)

  def onRetryRegistrationButtonClicked(self):
    self.logic.retryMode = True
    self.evaluationButtonsGroupBox.enabled = False
    self.onTrackTargetsButtonClicked()

  def finalizeRegistrationStep(self):
    self.targetTable.enabled = True
    self.addNewTargetsToScene()
    self.activeRegistrationResultButtonId = 3
    self.updateRegistrationResultSelector()
    self.setupRegistrationResultView()
    self.onBSplineResultClicked()
    self.organizeUIAfterRegistration()
    self.currentResult.printSummary()

  def addNewTargetsToScene(self):
    for targetNode in [targets for targets in self.currentResult.targets.values() if targets]:
      slicer.mrmlScene.AddNode(targetNode)

  def setupRegistrationResultView(self):
    self.hideAllLabels()
    self.addSliceAnnotations()
    slicer.app.applicationLogic().FitSliceToAll()

    self.refreshViewNodeIDs(self.preopTargets, self.redSliceNode)
    for targetNode in [targets for targets in self.currentResult.targets.values() if targets]:
      self.refreshViewNodeIDs(targetNode, self.yellowSliceNode)

    self.resetToRegularViewMode()

    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView)

    self.setAxialOrientation()

  def organizeUIAfterRegistration(self):
    self.registrationWatchBox.show()
    self.segmentationGroupBox.hide()
    self.activateRegistrationResultsArea(collapsed=False, enabled=True)
    self.evaluationButtonsGroupBox.enabled = True
    self.updateRegistrationEvaluationButtons()

  def refreshViewNodeIDs(self, targets, sliceNode):
    displayNode = targets.GetDisplayNode()
    displayNode.RemoveAllViewNodeIDs()
    displayNode.AddViewNodeID(sliceNode.GetID())

  def onNewImageDataReceived(self, **kwargs):
    newFileList = kwargs.pop('newList')
    self.patientCheckAfterImport(newFileList)
    # change icon of tabBar if user is not in Data selection tab
    # if not self.tabWidget.currentIndex == 0:
    #   self.tabBar.setTabIcon(0, self.newImageDataIcon)


class SliceTrackerLogic(ScriptedLoadableModuleLogic, ModuleLogicMixin):

  @property
  def preopDataDir(self):
    return self._preopDataDir

  @preopDataDir.setter
  def preopDataDir(self, path):
    if os.path.exists(path):
      self._preopDataDir = path

  @property
  def intraopDataDir(self):
    return self._intraopDataDir

  @intraopDataDir.setter
  def intraopDataDir(self, path):
    if os.path.exists(path):
      self._intraopDataDir = path
      self.startIntraopDirListener()
      self.startStoreSCP()

  @property
  def outputDir(self):
    return self._outputDir

  @outputDir.setter
  def outputDir(self, path):
    self._outputDir = path

  @property
  def currentResult(self):
      return self.registrationResults.activeResult

  @currentResult.setter
  def currentResult(self, series):
    self.registrationResults.activeResult = series
    # self.currentIntraopVolume
    # self.preop

  def __init__(self, parent=None):
    ScriptedLoadableModuleLogic.__init__(self, parent)
    self.inputMarkupNode = None
    self.clippingModelNode = None
    self.seriesList = []
    self.loadableList = {}
    self.alreadyLoadedSeries = {}
    self.needleTipMarkupNode = None
    self.storeSCPProcess = None

    self.currentIntraopVolume = None
    self.registrationResults = RegistrationResults()

    self._preopDataDir = ""
    self._intraopDataDir = ""
    self._outputDir = ""

    self._incomingDataCallback = None

    self.biasCorrectionDone = False

    self.volumesLogic = slicer.modules.volumes.logic()
    self.retryMode = False

  def __del__(self):
    if self.storeSCPProcess:
      self.storeSCPProcess.kill()
    del self.registrationResults

  def isTrackingPossible(self, seriesNumber):
    return not (self.registrationResults.registrationResultWasApproved(seriesNumber) or
                self.registrationResults.registrationResultWasSkipped(seriesNumber) or
                self.registrationResults.registrationResultWasRejected(seriesNumber))

  def setReceivedNewImageDataCallback(self, func):
    assert hasattr(func, '__call__')
    self._incomingDataCallback = func

  def save(self):
    # TODO: if registration was redone: make a sub folder and move all initial results there
    self.createDirectory(self._outputDir)

    successfullySavedData = ["The following data was successfully saved:\n"]
    failedSaveOfData = ["The following data failed to saved:\n"]

    def saveNodeData(node, extension, name=None):
      try:
        name = name if name else node.GetName()
        name = replaceUnwantedCharacters(name)
        filename = os.path.join(self._outputDir, name + extension)
        success = slicer.util.saveNode(node, filename)
        listToAdd = successfullySavedData if success else failedSaveOfData
        listToAdd.append(node.GetName())
      except AttributeError:
        failedSaveOfData.append(name)

    def replaceUnwantedCharacters(string, characters=None, replaceWith="-"):
      if not characters:
        characters = [": ", " ", ":", "/"]
      for character in characters:
        string = string.replace(character, replaceWith)
      return string

    def saveIntraopSegmentation():
      intraopLabel = self.registrationResults.intraopLabel
      if intraopLabel:
        intraopLabelName = intraopLabel.GetName().replace("label", "LABEL")
        saveNodeData(intraopLabel, '.nrrd', name=intraopLabelName)
        modelName = intraopLabel.GetName().replace("label", "MODEL")
        if self.clippingModelNode:
          saveNodeData(self.clippingModelNode, '.vtk', name=modelName)

    def saveOriginalTargets():
      originalTargets = self.registrationResults.originalTargets
      if originalTargets:
        saveNodeData(originalTargets, '.fcsv', name="PreopTargets")

    def saveBiasCorrectionResult():
      if self.biasCorrectionDone:
        biasCorrectedResult = self.registrationResults.biasCorrectedResult
        if biasCorrectedResult:
          saveNodeData(biasCorrectedResult, '.nrrd')

    def saveRegistrationResults():
      saveRegistrationCommandLineArguments()
      saveOutputTransformations()
      saveTransformedTargets()
      saveTipPosition()

    def saveRegistrationCommandLineArguments():
      for result in self.registrationResults.getResultsAsList():
        name = replaceUnwantedCharacters(result.name)
        filename = os.path.join(self._outputDir, name + "-CMD-PARAMETERS.txt")
        f = open(filename, 'w+')
        f.write(result.cmdArguments)
        f.close()

    def saveOutputTransformations():
      for result in self.registrationResults.getResultsAsList():
        for transformNode in [node for node in result.transforms.values() if node]:
          saveNodeData(transformNode, ".h5")

    def saveTransformedTargets():
      for result in self.registrationResults.getResultsAsList():
        for targetNode in [node for node in result.targets.values() if node]:
          saveNodeData(targetNode, ".fcsv")

    def saveTipPosition():
      for result in self.registrationResults.getResultsAsList():
        if result.tipPosition:
          # TODO: implement
          # prefixed with the series number
          pass

    saveIntraopSegmentation()
    saveOriginalTargets()
    saveBiasCorrectionResult()
    saveRegistrationResults()

    messageOutput = ""
    for messageList in [successfullySavedData, failedSaveOfData] :
      if len(messageList) > 1:
        for message in messageList:
          messageOutput += message + "\n"
    return messageOutput if messageOutput != "" else "There is nothing to be saved yet."

  def startStoreSCP(self):
    if self.storeSCPProcess:
      self.storeSCPProcess.kill()
    # command : $ sudo storescp -v -p 104 -od intraopDir
    pathToExe = os.path.join(slicer.app.slicerHome, 'bin', 'storescp')
    self.storeSCPProcess = Popen(["sudo", pathToExe, "-v", "-p", "104", "-od", self._intraopDataDir])
    if not self.storeSCPProcess:
      logging.error("storescp process could not be started. View log messages for further information.")

  def getSeriesInfoFromXML(self, f):
    import xml.dom.minidom
    dom = xml.dom.minidom.parse(f)
    number = self.findElement(dom, 'SeriesNumber')
    name = self.findElement(dom, 'SeriesDescription')
    name = name.replace('-', '')
    name = name.replace('(', '')
    name = name.replace(')', '')
    return number, name

  def findElement(self, dom, name):
    els = dom.getElementsByTagName('element')
    for e in els:
      if e.getAttribute('name') == name:
        return e.childNodes[0].nodeValue

  def getMostRecentWholeGlantSegmentation(self, path):
    return self.getMostRecentFile(path, "nrrd", filter="WholeGland")

  def getMostRecentTargetsFile(self, path):
    return self.getMostRecentFile(path, "fcsv")

  def getMostRecentFile(self, path, fileType, filter=None):
    assert type(fileType) is str
    files = [f for f in os.listdir(path) if f.endswith(fileType)]
    if len(files) == 0:
      return None
    mostRecent = None
    storedTimeStamp = 0
    for filename in files:
      if filter and not filter in filename:
        continue
      actualFileName = filename.split(".")[0]
      timeStamp = int(actualFileName.split("-")[-1])
      if timeStamp > storedTimeStamp:
        mostRecent = filename
        storedTimeStamp = timeStamp
    return mostRecent

  def clearAlreadyLoadedSeries(self):
    for series, volume in self.alreadyLoadedSeries.iteritems():
      print "removing volume %s of series %s " % (volume.GetName(), series)
      # TODO: slicer crash when deleting volumes
      # if slicer.mrmlScene.IsNodePresent(volume):
      #   slicer.mrmlScene.RemoveNode(volume)
    self.alreadyLoadedSeries.clear()

  def applyBiasCorrection(self, volume, label):

    outputVolume = slicer.vtkMRMLScalarVolumeNode()
    outputVolume.SetName('volume-PREOP-N4')
    slicer.mrmlScene.AddNode(outputVolume)
    params = {'inputImageName': volume.GetID(),
              'maskImageName': label.GetID(),
              'outputImageName': outputVolume.GetID(),
              'numberOfIterations': '500,400,300'}

    slicer.cli.run(slicer.modules.n4itkbiasfieldcorrection, None, params, wait_for_completion=True)

    return outputVolume

  def createVolumeAndTransformNodes(self, registrationTypes, prefix, suffix=""):
    for regType in registrationTypes:
      isBSpline = regType == 'bSpline'
      self.currentResult.setVolume(regType, self.createScalarVolumeNode(prefix + '-VOLUME-' + regType + suffix))
      self.currentResult.setTransform(regType, self.createTransformNode(prefix + '-TRANSFORM-' + regType + suffix, isBSpline))

  def transformTargets(self, registrations, targets, prefix):
    if targets:
      for registration in registrations:
        name = prefix + '-TARGETS-' + registration
        clone = self.cloneFiducialAndTransform(name, targets, self.currentResult.getTransform(registration))
        self.currentResult.setTargets(registration, clone)

  def applyInitialRegistration(self, fixedVolume, sourceVolume, fixedLabel, movingLabel, targets, progressCallback=None):

    self.progressCallback = progressCallback
    if not self.retryMode:
      self.registrationResults = RegistrationResults()
    name, suffix = self.getRegistrationResultNameAndGeneratedSuffix(fixedVolume)
    result = self.registrationResults.createResult(name+suffix)
    result.fixedVolume = fixedVolume
    result.fixedLabel = fixedLabel
    result.movingLabel = movingLabel
    result.originalTargets = targets
    result.movingVolume = self.volumesLogic.CloneVolume(slicer.mrmlScene, sourceVolume, 'movingVolume-PREOP-INTRAOP')

    self.createVolumeAndTransformNodes(['rigid', 'affine', 'bSpline'], prefix=str(result.seriesNumber), suffix=suffix)

    self.doRigidRegistration(movingBinaryVolume=self.currentResult.movingLabel, initializeTransformMode="useCenterOfROIAlign")
    self.doAffineRegistration()
    self.doBSplineRegistration(initialTransform=self.currentResult.affineTransform, useScaleVersor3D=False,
                               useScaleSkewVersor3D=True,
                               movingBinaryVolume=self.currentResult.movingLabel, useAffine=False, samplingPercentage="0.002",
                               maskInferiorCutOffFromCenter="1000", numberOfHistogramBins="50",
                               numberOfMatchPoints="10", metricSamplingStrategy="Random", costMetric="MMI")
    self.transformTargets(['rigid', 'affine', 'bSpline'], result.originalTargets, str(result.seriesNumber))
    result.movingVolume = sourceVolume
    self.retryMode = False

  def applyRegistration(self, progressCallback=None):

    self.progressCallback = progressCallback

    # TODO: think about retried segmentations
    coverProstateRegResult = self.registrationResults.getMostRecentApprovedCoverProstateRegistration()

    # take the 'intraop label map', which is always fixed label in the very first preop-intraop registration
    lastRigidTfm = self.registrationResults.getLastApprovedRigidTransformation()

    name, suffix = self.getRegistrationResultNameAndGeneratedSuffix(self.currentIntraopVolume)
    result = self.registrationResults.createResult(name+suffix)
    result.fixedVolume = self.currentIntraopVolume
    result.fixedLabel = self.volumesLogic.CreateAndAddLabelVolume(slicer.mrmlScene, self.currentIntraopVolume,
                                                                  self.currentIntraopVolume.GetName() + '-label')
    result.originalTargets = coverProstateRegResult.bSplineTargets
    sourceVolume = coverProstateRegResult.fixedVolume
    result.movingVolume = self.volumesLogic.CloneVolume(slicer.mrmlScene, sourceVolume, 'movingVolumeReReg')

    self.BRAINSResample(inputVolume=coverProstateRegResult.fixedLabel, referenceVolume=self.currentIntraopVolume,
                        outputVolume=result.fixedLabel, warpTransform=lastRigidTfm)

    self.createVolumeAndTransformNodes(['rigid', 'bSpline'], prefix=str(result.seriesNumber), suffix=suffix)

    self.doRigidRegistration(initialTransform=lastRigidTfm)
    self.dilateMask(result.fixedLabel)
    self.doBSplineRegistration(initialTransform=self.currentResult.rigidTransform, useScaleVersor3D=True,
                               useScaleSkewVersor3D=True, useAffine=True)

    self.transformTargets(['rigid', 'bSpline'], result.originalTargets, str(result.seriesNumber))
    result.movingVolume = sourceVolume

  def getRegistrationResultNameAndGeneratedSuffix(self, intraopVolume):
    name = intraopVolume.GetName()
    nOccurences = sum([1 for result in self.registrationResults.getResultsAsList() if name in result.name])
    suffix = ""
    if nOccurences:
      suffix = "_Retry_" + str(nOccurences)
    return name, suffix

  def updateProgress(self, **kwargs):
    if self.progressCallback:
      self.progressCallback(**kwargs)

  def doBSplineRegistration(self, initialTransform, useScaleVersor3D, useScaleSkewVersor3D, **kwargs):
    self.updateProgress(labelText='\nBSpline registration', value=3)
    paramsBSpline = {'fixedVolume': self.currentResult.fixedVolume,
                     'movingVolume': self.currentResult.movingVolume,
                     'outputVolume': self.currentResult.bSplineVolume.GetID(),
                     'bsplineTransform': self.currentResult.bSplineTransform.GetID(),
                     'fixedBinaryVolume': self.currentResult.fixedLabel,
                     'useRigid': False,
                     'useROIBSpline': True,
                     'useBSpline': True,
                     'useScaleVersor3D': useScaleVersor3D,
                     'useScaleSkewVersor3D': useScaleSkewVersor3D,
                     'splineGridSize': "3,3,3",
                     'numberOfIterations': "1500",
                     'maskProcessing': "ROI",
                     'outputVolumePixelType': "float",
                     'backgroundFillValue': "0",
                     'interpolationMode': "Linear",
                     'minimumStepLength': "0.005",
                     'translationScale': "1000",
                     'reproportionScale': "1",
                     'skewScale': "1",
                     'fixedVolumeTimeIndex': "0",
                     'movingVolumeTimeIndex': "0",
                     'medianFilterSize': "0,0,0",
                     'ROIAutoDilateSize': "0",
                     'relaxationFactor': "0.5",
                     'maximumStepLength': "0.2",
                     'failureExitCode': "-1",
                     'numberOfThreads': "-1",
                     'debugLevel': "0",
                     'costFunctionConvergenceFactor': "1.00E+09",
                     'projectedGradientTolerance': "1.00E-05",
                     'maxBSplineDisplacement': "0",
                     'maximumNumberOfEvaluations': "900",
                     'maximumNumberOfCorrections': "25",
                     'removeIntensityOutliers': "0",
                     'ROIAutoClosingSize': "9",
                     'maskProcessingMode': "ROI",
                     'initialTransform': initialTransform}
    for key, value in kwargs.iteritems():
      paramsBSpline[key] = value

    slicer.cli.run(slicer.modules.brainsfit, None, paramsBSpline, wait_for_completion=True)
    self.currentResult.cmdArguments += "BSpline Registration Parameters: %s" % str(paramsBSpline) + "\n\n"

    self.updateProgress(labelText='\nCompleted registration', value=4)

  def doAffineRegistration(self):
    self.updateProgress(labelText='\nAffine registration', value=2)
    paramsAffine = {'fixedVolume': self.currentResult.fixedVolume,
                    'movingVolume': self.currentResult.movingVolume,
                    'fixedBinaryVolume': self.currentResult.fixedLabel,
                    'movingBinaryVolume': self.currentResult.movingLabel,
                    'outputTransform': self.currentResult.affineTransform.GetID(),
                    'outputVolume': self.currentResult.affineVolume.GetID(),
                    'maskProcessingMode': "ROI",
                    'useAffine': True,
                    'initialTransform': self.currentResult.rigidTransform}
    slicer.cli.run(slicer.modules.brainsfit, None, paramsAffine, wait_for_completion=True)
    self.currentResult.cmdArguments += "Affine Registration Parameters: %s" % str(paramsAffine) + "\n\n"

  def doRigidRegistration(self, **kwargs):
    self.updateProgress(labelText='\nRigid registration', value=2)
    paramsRigid = {'fixedVolume': self.currentResult.fixedVolume,
                   'movingVolume': self.currentResult.movingVolume,
                   'fixedBinaryVolume': self.currentResult.fixedLabel,
                   'outputTransform': self.currentResult.rigidTransform.GetID(),
                   'outputVolume': self.currentResult.rigidVolume.GetID(),
                   'maskProcessingMode': "ROI",
                   'useRigid': True,
                   'useAffine': False,
                   'useBSpline': False,
                   'useScaleVersor3D': False,
                   'useScaleSkewVersor3D': False,
                   'useROIBSpline': False}
    for key, value in kwargs.iteritems():
      paramsRigid[key] = value
    slicer.cli.run(slicer.modules.brainsfit, None, paramsRigid, wait_for_completion=True)
    self.currentResult.cmdArguments += "Rigid Registration Parameters: %s" % str(paramsRigid) + "\n\n"

  def cloneFiducialAndTransform(self, cloneName, originalTargets, transformNode):
    tfmLogic = slicer.modules.transforms.logic()
    clonedTargets = self.cloneFiducials(originalTargets, cloneName)
    clonedTargets.SetAndObserveTransformNodeID(transformNode.GetID())
    tfmLogic.hardenTransform(clonedTargets)
    return clonedTargets

  def cloneFiducials(self, original, cloneName):
    mlogic = slicer.modules.markups.logic()
    nodeId = mlogic.AddNewFiducialNode(cloneName, slicer.mrmlScene)
    clone = slicer.mrmlScene.GetNodeByID(nodeId)
    for i in range(original.GetNumberOfFiducials()):
      pos = [0.0, 0.0, 0.0]
      original.GetNthFiducialPosition(i, pos)
      name = original.GetNthFiducialLabel(i)
      clone.AddFiducial(pos[0], pos[1], pos[2])
      clone.SetNthFiducialLabel(i, name)
    return clone

  def dilateMask(self, mask):
    logging.debug('mask ' + mask.GetName() + ' is dilated')

    labelImage = sitk.ReadImage(sitkUtils.GetSlicerITKReadWriteAddress(mask.GetName()))
    labelImage = self.createGrayscaleLabelImage(labelImage)

    sitk.WriteImage(labelImage, sitkUtils.GetSlicerITKReadWriteAddress(mask.GetName()))
    logging.debug('dilate mask through')

  def createGrayscaleLabelImage(self, labelImage):
    grayscale_dilate_filter = sitk.GrayscaleDilateImageFilter()
    grayscale_dilate_filter.SetKernelRadius([12, 12, 0])
    grayscale_dilate_filter.SetKernelType(sitk.sitkBall)
    labelImage = grayscale_dilate_filter.Execute(labelImage)
    return labelImage

  def startIntraopDirListener(self):
    numberOfFiles = len(self.getFileList(self._intraopDataDir))
    self.lastFileCount = numberOfFiles
    self.createCurrentFileList(self._intraopDataDir)
    self.startTimer()

  def startTimer(self):
    currentFileCount = len(self.getFileList(self._intraopDataDir))
    if self.lastFileCount != currentFileCount:
      self.waitingForSeriesToBeCompleted()
    self.lastFileCount = currentFileCount
    qt.QTimer.singleShot(500, self.startTimer)

  def createCurrentFileList(self, directory):
    self.currentFileList = []
    for item in self.getFileList(directory):
      self.currentFileList.append(item)

    if len(self.currentFileList) > 1:
      self.thereAreFilesInTheFolderFlag = 1
      self.importDICOMSeries()
    else:
      self.thereAreFilesInTheFolderFlag = 0

  def createLoadableFileListFromSelection(self, selectedSeries):

    if os.path.exists(self._intraopDataDir):
      self.loadableList = dict()
      self.loadableList[selectedSeries] = []

      for dcm in self.getFileList(self._intraopDataDir):
        currentFile = os.path.join(self._intraopDataDir, dcm)
        seriesNumberDescription = self.makeSeriesNumberDescription(currentFile)
        if seriesNumberDescription and seriesNumberDescription in selectedSeries:
          self.loadableList[selectedSeries].append(currentFile)

  def loadSeriesIntoSlicer(self, selectedSeries, clearOldSeries=False):
    if clearOldSeries:
      self.clearAlreadyLoadedSeries()
    self.createLoadableFileListFromSelection(selectedSeries)

    if selectedSeries not in self.alreadyLoadedSeries.keys():
      files = self.loadableList[selectedSeries]
      # create DICOMScalarVolumePlugin and load selectedSeries data from files into slicer
      scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()

      loadables = scalarVolumePlugin.examine([files])

      name = loadables[0].name
      self.currentIntraopVolume = scalarVolumePlugin.load(loadables[0])
      self.currentIntraopVolume.SetName(name)
      slicer.mrmlScene.AddNode(self.currentIntraopVolume)
      self.alreadyLoadedSeries[selectedSeries] = self.currentIntraopVolume
    else:
      self.currentIntraopVolume = self.alreadyLoadedSeries[selectedSeries]

  def waitingForSeriesToBeCompleted(self):

    logging.debug('**  new data in intraop directory detected **')
    logging.debug('waiting 5 more seconds for the series to be completed')

    qt.QTimer.singleShot(5000, self.importDICOMSeries)

  def getSeriesNumberFromString(self, text):
    return int(text.split(": ")[0])

  def importDICOMSeries(self):
    indexer = ctk.ctkDICOMIndexer()
    db = slicer.dicomDatabase

    if self.thereAreFilesInTheFolderFlag == 1:
      newFileList = self.currentFileList
      self.thereAreFilesInTheFolderFlag = 0
    else:
      newFileList = list(set(self.getFileList(self._intraopDataDir)) - set(self.currentFileList))

    for currentFile in newFileList:
      currentFile = os.path.join(self._intraopDataDir, currentFile)
      indexer.addFile(db, currentFile, None)
      seriesNumberDescription = self.makeSeriesNumberDescription(currentFile)
      if seriesNumberDescription and seriesNumberDescription not in self.seriesList:
        self.seriesList.append(seriesNumberDescription)

    indexer.addDirectory(db, self._intraopDataDir)
    indexer.waitForImportFinished()

    self.seriesList = sorted(self.seriesList, key=lambda series: self.getSeriesNumberFromString(series))

    if self._incomingDataCallback:
      self._incomingDataCallback(newList=newFileList)

  def makeSeriesNumberDescription(self, dicomFile):
    seriesDescription = self.getDICOMValue(dicomFile, DICOMTAGS.SERIES_DESCRIPTION)
    seriesNumber = self.getDICOMValue(dicomFile, DICOMTAGS.SERIES_NUMBER)
    seriesNumberDescription = None
    if seriesDescription and seriesNumber:
      seriesNumberDescription = seriesNumber + ": " + seriesDescription
    return seriesNumberDescription

  def getNeedleTipAndTargetsPositions(self, registeredTargets):
    needleTip_position = self.getNeedleTipPosition()
    target_positions = self.getTargetPositions(registeredTargets)
    return [needleTip_position, target_positions]

  def getNeedleTipPosition(self):

    needleTip_position = []
    if self.needleTipMarkupNode:
      needleTip_position = [0.0, 0.0, 0.0]
      self.needleTipMarkupNode.GetNthFiducialPosition(0, needleTip_position)
      logging.debug('needleTip_position = ' + str(needleTip_position))
    return needleTip_position

  def getTargetPositions(self, registeredTargets):

    number_of_targets = registeredTargets.GetNumberOfFiducials()
    target_positions = []
    for target in range(number_of_targets):
      target_position = [0.0, 0.0, 0.0]
      registeredTargets.GetNthFiducialPosition(target, target_position)
      target_positions.append(target_position)
    logging.debug('target_positions are ' + str(target_positions))
    return target_positions

  def setNeedleTipPosition(self, destinationViewNode=None, callback=None):

    if self.needleTipMarkupNode is None:
      self.needleTipMarkupNode = self.createNeedleTipMarkupNode(destinationViewNode, callback)
    else:
      self.needleTipMarkupNode.RemoveAllMarkups()

    self.startNeedleTipPlacingMode()

  def createNeedleTipMarkupNode(self, destinationViewNode, callback=None):

    needleTipMarkupDisplayNode = slicer.vtkMRMLMarkupsDisplayNode()
    needleTipMarkupNode = slicer.vtkMRMLMarkupsFiducialNode()
    needleTipMarkupNode.SetName('needle-tip')
    slicer.mrmlScene.AddNode(needleTipMarkupDisplayNode)
    slicer.mrmlScene.AddNode(needleTipMarkupNode)
    needleTipMarkupNode.SetAndObserveDisplayNodeID(needleTipMarkupDisplayNode.GetID())
    # don't show needle tip in red Slice View
    if destinationViewNode:
      needleTipMarkupDisplayNode.AddViewNodeID(destinationViewNode.GetID())
    if callback:
      needleTipMarkupNode.AddObserver(vtk.vtkCommand.ModifiedEvent, callback)

    needleTipMarkupDisplayNode.SetTextScale(1.6)
    needleTipMarkupDisplayNode.SetGlyphScale(2.0)
    needleTipMarkupDisplayNode.SetGlyphType(12)
    return needleTipMarkupNode

  def startNeedleTipPlacingMode(self):

    mlogic = slicer.modules.markups.logic()
    mlogic.SetActiveListID(self.needleTipMarkupNode)
    slicer.modules.markups.logic().StartPlaceMode(0)

  def getNeedleTipTargetDistance2D(self, target_position, needleTip_position):
    x = abs(target_position[0] - needleTip_position[0])
    y = abs(target_position[1] - needleTip_position[1])
    return [x, y]

  def getNeedleTipTargetDistance3D(self, target_position, needleTip_position):
    rulerNode = slicer.vtkMRMLAnnotationRulerNode()
    rulerNode.SetPosition1(target_position)
    rulerNode.SetPosition2(needleTip_position)
    distance_3D = rulerNode.GetDistanceMeasurement()
    return distance_3D

  def setupColorTable(self, colorFile):

    self.mpReviewColorNode = slicer.vtkMRMLColorTableNode()
    colorNode = self.mpReviewColorNode
    colorNode.SetName('mpReview')
    slicer.mrmlScene.AddNode(colorNode)
    colorNode.SetTypeToUser()
    with open(colorFile) as f:
      n = sum(1 for line in f)
    colorNode.SetNumberOfColors(n - 1)
    import csv
    self.structureNames = []
    with open(colorFile, 'rb') as csvfile:
      reader = csv.DictReader(csvfile, delimiter=',')
      for index, row in enumerate(reader):
        colorNode.SetColor(index, row['Label'], float(row['R']) / 255,
                           float(row['G']) / 255, float(row['B']) / 255, float(row['A']))
        self.structureNames.append(row['Label'])

  def run(self):
    return True

  def runQuickSegmentationMode(self):
    self.setVolumeClipUserMode()
    self.placeFiducials()

  def setVolumeClipUserMode(self):
    lm = slicer.app.layoutManager()
    lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)

    for widgetName in ['Red', 'Green', 'Yellow']:
      slice = lm.sliceWidget(widgetName)
      sliceLogic = slice.sliceLogic()
      sliceLogic.FitSliceToAll()

    # set the mouse mode into Markups fiducial placement
    placeModePersistence = 1
    slicer.modules.markups.logic().StartPlaceMode(placeModePersistence)

  def updateModel(self, observer, caller):
    import VolumeClipWithModel
    clipLogic = VolumeClipWithModel.VolumeClipWithModelLogic()
    clipLogic.updateModelFromMarkup(self.inputMarkupNode, self.clippingModelNode)

  def deleteClippingData(self):
    slicer.mrmlScene.RemoveNode(self.clippingModelNode)
    logging.debug('deleted ModelNode')
    slicer.mrmlScene.RemoveNode(self.inputMarkupNode)
    logging.debug('deleted inputMarkupNode')

  def placeFiducials(self):

    self.clippingModelNode = slicer.vtkMRMLModelNode()
    self.clippingModelNode.SetName('clipModelNode')
    slicer.mrmlScene.AddNode(self.clippingModelNode)

    self.createClippingModelDisplayNode()
    self.createMarkupAndDisplayNodeForFiducials()
    self.inputMarkupNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.updateModel)

  def createMarkupAndDisplayNodeForFiducials(self):
    displayNode = slicer.vtkMRMLMarkupsDisplayNode()
    slicer.mrmlScene.AddNode(displayNode)
    self.inputMarkupNode = slicer.vtkMRMLMarkupsFiducialNode()
    self.inputMarkupNode.SetName('inputMarkupNode')
    slicer.mrmlScene.AddNode(self.inputMarkupNode)
    self.inputMarkupNode.SetAndObserveDisplayNodeID(displayNode.GetID())
    self.styleDisplayNode(displayNode)

  def styleDisplayNode(self, displayNode):
    displayNode.SetTextScale(0)
    displayNode.SetGlyphScale(2.0)
    displayNode.SetColor(0, 0, 0)

  def createClippingModelDisplayNode(self):
    clippingModelDisplayNode = slicer.vtkMRMLModelDisplayNode()
    clippingModelDisplayNode.SetSliceIntersectionThickness(3)
    clippingModelDisplayNode.SetColor([0.200, 0.800, 0.000]) # green for glant
    clippingModelDisplayNode.BackfaceCullingOff()
    clippingModelDisplayNode.SliceIntersectionVisibilityOn()
    clippingModelDisplayNode.SetOpacity(0.3)
    slicer.mrmlScene.AddNode(clippingModelDisplayNode)
    self.clippingModelNode.SetAndObserveDisplayNodeID(clippingModelDisplayNode.GetID())

  def labelMapFromClippingModel(self, inputVolume):
    outputLabelMap = slicer.vtkMRMLLabelMapVolumeNode()
    slicer.mrmlScene.AddNode(outputLabelMap)

    params = {'sampleDistance': 0.1, 'labelValue': 8, 'InputVolume': inputVolume.GetID(),
              'surface': self.clippingModelNode.GetID(), 'OutputVolume': outputLabelMap.GetID()}

    logging.debug(params)
    slicer.cli.run(slicer.modules.modeltolabelmap, None, params, wait_for_completion=True)

    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").SetUseLabelOutline(True)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").SetUseLabelOutline(True)

    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").RotateToVolumePlane(outputLabelMap)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").RotateToVolumePlane(outputLabelMap)

    return outputLabelMap

  def BRAINSResample(self, inputVolume, referenceVolume, outputVolume, warpTransform):

    params = {'inputVolume': inputVolume, 'referenceVolume': referenceVolume, 'outputVolume': outputVolume,
              'warpTransform': warpTransform, 'interpolationMode': 'NearestNeighbor'}

    logging.debug('about to run BRAINSResample CLI with those params: ')
    logging.debug(params)
    slicer.cli.run(slicer.modules.brainsresample, None, params, wait_for_completion=True)
    logging.debug('resample labelmap through')
    slicer.mrmlScene.AddNode(outputVolume)


class SliceTrackerTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear(0)

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_SliceTracker1()

  def test_SliceTracker1(self):
    """ Ideally you should have several levels of tests.  At the lowest level
    tests should exercise the functionality of the logic with different inputs
    (both valid and invalid).  At higher levels your tests should emulate the
    way the user would interact with your code and confirm that it still works
    the way you intended.
    One of the most important features of the tests is that it should alert other
    developers when their changes will have an impact on the behavior of your
    module.  For example, if a developer removes a feature that you depend on,
    your test should break so they know that the feature is needed.
    """
    logging.debug(' ___ performing selfTest ___ ')


from collections import OrderedDict
from Utils.decorators import onExceptReturnNone


class RegistrationResults(object):

  @property
  def activeResult(self):
    return self._getActiveResult()

  @activeResult.setter
  def activeResult(self, series):
    assert series in self._registrationResults.keys()
    self._activeResult = series

  @property
  @onExceptReturnNone
  def originalTargets(self):
    return self.getMostRecentApprovedCoverProstateRegistration().originalTargets

  @property
  @onExceptReturnNone
  def intraopLabel(self):
    return self.getMostRecentApprovedCoverProstateRegistration().fixedLabel

  @property
  @onExceptReturnNone
  def biasCorrectedResult(self):
    return self.getMostRecentApprovedCoverProstateRegistration().movingVolume

  def __init__(self):
    self._registrationResults = OrderedDict()
    self._activeResult = None
    self.preopTargets = None

  def registrationResultWasApproved(self, seriesNumber):
    results = self.getResultsBySeriesNumber(seriesNumber)
    return any(result.approved is True for result in results) if len(results) else False

  def registrationResultWasSkipped(self, seriesNumber):
    results = self.getResultsBySeriesNumber(seriesNumber)
    return any(result.skipped is True for result in results) if len(results) else False

  def registrationResultWasRejected(self, seriesNumber):
    results = self.getResultsBySeriesNumber(seriesNumber)
    return all(result.rejected is True for result in results) if len(results) else False

  def getResultsAsList(self):
    return self._registrationResults.values()

  def getMostRecentApprovedCoverProstateRegistration(self):
    mostRecent = None
    for result in self._registrationResults.values():
      if "COVER PROSTATE" in result.name and result.approved and not result.skipped:
        mostRecent = result
    return mostRecent

  def getLastApprovedRigidTransformation(self):
    nApprovedRegistrations = sum([1 for result in self._registrationResults.values() if result.approved])
    if nApprovedRegistrations == 1:
      logging.debug('Resampling label with same mask')
      # last registration was preop-intraop, take the same mask
      # this is an identity transform:
      lastRigidTfm = vtk.vtkGeneralTransform()
      lastRigidTfm.Identity()
    else:
      try:
        lastRigidTfm = self.getMostRecentApprovedResult().rigidTransform
      except AttributeError:
        lastRigidTfm = None
    return lastRigidTfm

  def getOrCreateResult(self, series):
    result = self.getResult(series)
    return result if result is not None else self.createResult(series)

  def createResult(self, series):
    assert series not in self._registrationResults.keys()
    self._registrationResults[series] = RegistrationResult(series)
    self.activeResult = series
    return self._registrationResults[series]

  @onExceptReturnNone
  def getResult(self, series):
    return self._registrationResults[series]

  def getResultsBySeriesNumber(self, seriesNumber):
    return [result for result in self.getResultsAsList() if seriesNumber == result.seriesNumber]

  def removeResult(self, series):
    try:
      del self._registrationResults[series]
    except KeyError:
      pass

  def exists(self, series):
    return series in self._registrationResults.keys()

  @onExceptReturnNone
  def _getActiveResult(self):
    return self._registrationResults[self._activeResult]

  @onExceptReturnNone
  def getMostRecentResult(self):
    lastKey = self._registrationResults.keys()[-1]
    return self._registrationResults[lastKey]

  @onExceptReturnNone
  def getMostRecentApprovedResult(self):
    for result in reversed(self._registrationResults.values()):
      if result.approved:
        return result
    return None

  @onExceptReturnNone
  def getMostRecentVolumes(self):
    return self.getMostRecentResult().volumes

  @onExceptReturnNone
  def getMostRecentTransforms(self):
    return self.getMostRecentResult().transforms

  @onExceptReturnNone
  def getMostRecentTargets(self):
    return self.getMostRecentResult().targets

  # def deleteRegistrationResult(self, series):
  #   result = self._registrationResults[series]
  #   # TODO: deleting targets causes total crash of Slicer
  #   nodesToDelete = ['fixedLabel', 'movingLabel', 'outputVolumeRigid', 'outputVolumeAffine', 'outputVolumeBSpline',
  #                    'outputTransformRigid', 'outputTransformAffine', 'outputTransformBSpline']
  #   # 'outputTargetsRigid', 'outputTargetAffine', 'outputTargetsBSpline']
  #   for node in [result[key] for key in nodesToDelete if key in result.keys()]:
  #     if node:
  #       slicer.mrmlScene.RemoveNodeReferences(node)
  #       slicer.mrmlScene.RemoveNode(node)
  #   del self._registrationResults[series]


class RegistrationResult(object):

  REGISTRATION_TYPE_NAMES = ['rigid', 'affine', 'bSpline']

  @property
  def volumes(self):
    return {'rigid': self.rigidVolume, 'affine': self.affineVolume, 'bSpline': self.bSplineVolume}

  @property
  def transforms(self):
    return {'rigid': self.rigidTransform, 'affine': self.affineTransform, 'bSpline': self.bSplineTransform}

  @property
  def targets(self):
    return {'rigid': self.rigidTargets, 'affine': self.affineTargets, 'bSpline': self.bSplineTargets}

  @property
  def name(self):
    return self._name

  @name.setter
  def name(self, name):
    splitted = name.split(': ')
    assert len(splitted) == 2
    self._name = name
    self._seriesNumber = int(splitted[0])
    self._seriesDescription = splitted[1]

  @property
  def seriesNumber(self):
    return self._seriesNumber

  @property
  def seriesDescription(self):
    return self._seriesDescription

  def __init__(self, series):
    self.name = series
    self.approved = False
    self.skipped = False
    self.rejected = False
    self.rigidVolume = None
    self.affineVolume = None
    self.bSplineVolume = None
    self.rigidTransform = None
    self.affineTransform = None
    self.bSplineTransform = None
    self.rigidTargets = None
    self.affineTargets = None
    self.bSplineTargets = None
    self.originalTargets = None

    self.movingVolume = None
    self.movingLabel = None
    self.fixedVolume = None
    self.fixedLabel = None

    self.tipPosition = None

    self.cmdArguments = ""

    self.score = None

  def __del__(self):
    # TODO: should it also delete the volumes etc.?
    pass

  def setVolume(self, regType, volume):
    self._setRegAttribute(regType, "Volume", volume)

  def getVolume(self, regType):
    return self._getRegAttribute(regType, "Volume")

  def setTransform(self, regType, transform):
    self._setRegAttribute(regType, "Transform", transform)

  def getTransform(self, regType):
    return self._getRegAttribute(regType, "Transform")

  def setTargets(self, regType, targets):
    self._setRegAttribute(regType, "Targets", targets)

  def getTargets(self, regType):
    return self._getRegAttribute(regType, "Targets")

  def _setRegAttribute(self, regType, attributeType, value):
    assert regType in self.REGISTRATION_TYPE_NAMES
    setattr(self, regType+attributeType, value)

  def _getRegAttribute(self, regType, attributeType):
    assert regType in self.REGISTRATION_TYPE_NAMES
    return getattr(self, regType+attributeType)

  def approve(self):
    self.approved = True
    self.skipped = False
    self.rejected = False

  def skip(self):
    self.skipped = True
    self.approved = False
    self.rejected = False

  def reject(self):
    self.rejected = True
    self.skipped = False
    self.approved = False

  def printSummary(self):
    logging.debug('# ___________________________  registration output  ________________________________')
    logging.debug(self.__dict__)
    logging.debug('# __________________________________________________________________________________')


class RatingWindow(qt.QWidget, ModuleWidgetMixin):

  @property
  def maximumValue(self):
    return self._maximumValue

  @maximumValue.setter
  def maximumValue(self, value):
    if value < 1:
      raise ValueError("The maximum rating value cannot be less than 1.")
    else:
      self._maximumValue = value

  def __init__(self, maximumValue, text="Please rate the registration result:", *args):
    qt.QWidget.__init__(self, *args)
    self.maximumValue = maximumValue
    self.text = text
    self.iconPath = os.path.join(os.path.dirname(sys.modules[self.__module__].__file__), 'Resources/Icons')
    self.setupIcons()
    self.setLayout(qt.QGridLayout())
    self.setWindowFlags(qt.Qt.WindowStaysOnTopHint | qt.Qt.FramelessWindowHint)
    self.setupElements()
    self.connectButtons()
    self.showRatingValue = True

  def __del__(self):
    self.disconnectButtons()

  def isRatingEnabled(self):
    return not self.disableWidgetCheckbox.checked

  def setupIcons(self):
    self.filledStarIcon = self.createIcon("icon-star-filled.png", self.iconPath)
    self.unfilledStarIcon = self.createIcon("icon-star-unfilled.png", self.iconPath)

  def show(self, disableWidget=None, callback=None):
    self.disabledWidget = disableWidget
    if disableWidget:
      disableWidget.enabled = False
    qt.QWidget.show(self)
    self.ratingScore = None
    self.callback = callback

  def setupElements(self):
    self.layout().addWidget(qt.QLabel(self.text), 0, 0)
    self.ratingButtonGroup = qt.QButtonGroup()
    for rateValue in range(1, self.maximumValue+1):
      attributeName = "button"+str(rateValue)
      setattr(self, attributeName, self.createButton('', icon=self.unfilledStarIcon))
      self.ratingButtonGroup.addButton(getattr(self, attributeName), rateValue)

    for button in list(self.ratingButtonGroup.buttons()):
      button.setCursor(qt.Qt.PointingHandCursor)

    self.ratingLabel = self.createLabel("")
    row = self.createHLayout(list(self.ratingButtonGroup.buttons()) + [self.ratingLabel])
    self.layout().addWidget(row, 1, 0)

    self.disableWidgetCheckbox = qt.QCheckBox("Don't display this window again")
    self.disableWidgetCheckbox.checked = False
    self.layout().addWidget(self.disableWidgetCheckbox, 2, 0)

  def connectButtons(self):
    self.ratingButtonGroup.connect('buttonClicked(int)', self.onRatingButtonClicked)
    for button in list(self.ratingButtonGroup.buttons()):
      button.installEventFilter(self)

  def disconnectButtons(self):
    self.ratingButtonGroup.disconnect('buttonClicked(int)', self.onRatingButtonClicked)
    for button in list(self.ratingButtonGroup.buttons()):
      button.removeEventFilter(self)

  def eventFilter(self, obj, event):
    if obj in list(self.ratingButtonGroup.buttons()) and event.type() == qt.QEvent.HoverEnter:
      self.onHoverEvent(obj)
    elif obj in list(self.ratingButtonGroup.buttons()) and event.type() == qt.QEvent.HoverLeave:
      self.onLeaveEvent()
    return qt.QWidget.eventFilter(self, obj, event)

  def onLeaveEvent(self):
    for button in list(self.ratingButtonGroup.buttons()):
      button.icon = self.unfilledStarIcon

  def onHoverEvent(self, obj):
    ratingValue = 0
    for button in list(self.ratingButtonGroup.buttons()):
      button.icon = self.filledStarIcon
      ratingValue += 1
      if obj is button:
        break
    if self.showRatingValue:
      self.ratingLabel.setText(str(ratingValue))

  def onRatingButtonClicked(self, buttonId):
    self.ratingScore = buttonId
    if self.disabledWidget:
      self.disabledWidget.enabled = True
      self.disabledWidget = None
    if self.callback:
      self.callback(self.ratingScore)
    self.hide()