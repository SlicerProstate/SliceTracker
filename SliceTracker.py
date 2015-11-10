import os
import math, re
from __main__ import vtk, qt, ctk, slicer
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
  GREEN = qt.QColor(qt.Qt.green)
  GRAY = qt.QColor(qt.Qt.gray)


class STYLE:

  GRAY_BACKGROUND_WHITE_FONT  = 'background-color: rgb(130,130,130); ' \
                                           'color: rgb(255,255,255)'
  WHITE_BACKGROUND            = 'background-color: rgb(255,255,255)'
  LIGHT_GRAY_BACKGROUND       = 'background-color: rgb(230,230,230)'
  ORANGE_BACKGROUND           = 'background-color: rgb(255,102,0)'


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
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

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
    self.setTabsEnabled([1, 2, 3], False)
    self.setSetting('PreopLocation', path)
    self.loadPreopData()
    self.updateSeriesSelectorTable()
    self.reRegistrationMode = False
    self.reRegButton.setEnabled(False)
    self.intraopDirButton.setEnabled(True)
    self.outputDirButton.setEnabled(True)
    self._updateOutputDir()

  @property
  def intraopDataDir(self):
    return self.logic.intraopDataDir

  @intraopDataDir.setter
  def intraopDataDir(self, path):
    self.logic.setReceivedNewImageDataCallback(self.onNewImageDataReceived)
    self.logic.intraopDataDir = path
    self.setSetting('IntraopLocation', path)

  @property
  def outputDir(self):
    return self.logic.outputDir

  @outputDir.setter
  def outputDir(self, path):
    if os.path.exists(path):
      # patient_id-biopsy_DICOM_study_date-study_time
      self._outputRoot = path
      self.setSetting('OutputLocation', path)
      self._updateOutputDir()

  def __init__(self, parent=None):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    assert slicer.dicomDatabase
    self.dicomDatabase = slicer.dicomDatabase
    self.logic = SliceTrackerLogic()
    self.layoutManager = slicer.app.layoutManager()
    self.markupsLogic = slicer.modules.markups.logic()
    self.volumesLogic = slicer.modules.volumes.logic()
    self.modulePath = slicer.modules.slicetracker.path.replace(self.moduleName + ".py", "")
    self.iconPath = os.path.join(self.modulePath, 'Resources/Icons')
    self._outputRoot = None

  def _updateOutputDir(self):
    if self._outputRoot and self.patientID and self.currentStudyDate:
      time = qt.QTime().currentTime().toString().replace(":", "")
      dirName = self.patientID.text + "-biopsy-" + self.currentStudyDate.text + time
      self.logic.outputDir = os.path.join(self._outputRoot, dirName, "MRgBiopsy")

  def onReload(self):
    ScriptedLoadableModuleWidget.onReload(self)
    slicer.mrmlScene.Clear(0)
    self.logic = SliceTrackerLogic()

  def getSetting(self, settingName):
    settings = qt.QSettings()
    return str(settings.value(self.moduleName + '/' + settingName))

  def setSetting(self, settingName, value):
    settings = qt.QSettings()
    settings.setValue(self.moduleName + '/' + settingName, value)

  def createPatientWatchBox(self):
    patientViewBox = qt.QGroupBox()
    patientViewBox.setStyleSheet(STYLE.LIGHT_GRAY_BACKGROUND)
    patientViewBoxLayout = qt.QGridLayout()
    patientViewBox.setLayout(patientViewBoxLayout)
    self.layout.addWidget(patientViewBox)

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

  def setupIcons(self):
    self.labelSegmentationIcon = self.createIcon('icon-labelSegmentation.png')
    self.cancelSegmentationIcon = self.createIcon('icon-cancelSegmentation.png')
    self.greenCheckIcon = self.createIcon('icon-greenCheck.png')
    self.acceptedIcon = self.createIcon('icon-accept.png')
    self.discardedIcon = self.createIcon('icon-discard.png')
    self.quickSegmentationIcon = self.createIcon('icon-quickSegmentation.png')
    self.dataSelectionIcon = self.createIcon('icon-dataselection_fit.png')
    self.labelSelectionIcon = self.createIcon('icon-labelselection_fit.png')
    self.registrationSectionIcon = self.createIcon('icon-registration_fit.png')
    self.evaluationSectionIcon = self.createIcon('icon-evaluation_fit.png')
    self.newImageDataIcon = self.createIcon('icon-newImageData.png')
    self.littleDiscIcon = self.createIcon('icon-littleDisc.png')
    self.undoIcon = self.createIcon('icon-undo.png')
    self.redoIcon = self.createIcon('icon-redo.png')

  def createTabWidget(self):
    self.tabWidget = qt.QTabWidget()
    self.layout.addWidget(self.tabWidget)

    self.tabBar = self.tabWidget.childAt(1, 1)

    self.dataSelectionGroupBox = qt.QGroupBox()
    self.labelSelectionGroupBox = qt.QGroupBox()
    self.registrationGroupBox = qt.QGroupBox()
    self.evaluationGroupBox = qt.QGroupBox()
    self.tabWidget.setIconSize(qt.QSize(110, 50))

    self.dataSelectionGroupBoxLayout = qt.QFormLayout()
    self.labelSelectionGroupBoxLayout = qt.QFormLayout()
    self.registrationGroupBoxLayout = qt.QFormLayout()
    self.evaluationGroupBoxLayout = qt.QFormLayout()

    self.dataSelectionGroupBox.setLayout(self.dataSelectionGroupBoxLayout)
    self.labelSelectionGroupBox.setLayout(self.labelSelectionGroupBoxLayout)
    self.registrationGroupBox.setLayout(self.registrationGroupBoxLayout)
    self.evaluationGroupBox.setLayout(self.evaluationGroupBoxLayout)

    self.tabWidget.addTab(self.dataSelectionGroupBox, self.dataSelectionIcon, '')
    self.tabWidget.addTab(self.labelSelectionGroupBox, self.labelSelectionIcon, '')
    self.tabWidget.addTab(self.registrationGroupBox, self.registrationSectionIcon, '')
    self.tabWidget.addTab(self.evaluationGroupBox, self.evaluationSectionIcon, '')

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    try:
      import VolumeClipWithModel
    except ImportError:
      return self.warningDialog("Error: Could not find extension VolumeClip. Open Slicer Extension Manager and install "
                                "VolumeClip.", "Missing Extension")

    self.seriesItems = []
    self.revealCursor = None

    self.quickSegmentationActive = False
    self.comingFromPreopTag = False
    self.logic.retryMode = False

    self.createPatientWatchBox()
    self.setupIcons()
    self.createTabWidget()

    self.setupSliceWidgets()
    self.setupDataSelectionStep()
    self.setupProstateSegmentationStep()
    self.setupRegistrationStep()
    self.setupRegistrationEvaluationStep()

    self.setupConnections()

    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)
    self.setAxialOrientation()

    self.setTabsEnabled([1, 2, 3], False)

    self.currentTabIndex = 0
    self.showAcceptRegistrationWarning = False
    self.tabWidget.setCurrentIndex(0)

    self.logic.setupColorTable(colorFile=os.path.join(self.modulePath,'Resources/Colors/PCampReviewColors.csv'))
    self.removeSliceAnnotations()

  def setupSliceWidgets(self):
    self.setupRedSliceWidget()
    self.setupYellowSliceWidget()
    self.setupGreenSliceWidget()

  def setupRedSliceWidget(self):
    self.redWidget = self.layoutManager.sliceWidget('Red')
    self.compositeNodeRed = self.redWidget.mrmlSliceCompositeNode()
    self.redSliceLogic = self.redWidget.sliceLogic()
    self.redSliceView = self.redWidget.sliceView()
    self.redSliceNode = self.redSliceLogic.GetSliceNode()
    self.currentFOVRed = []

  def setupYellowSliceWidget(self):
    self.yellowWidget = self.layoutManager.sliceWidget('Yellow')
    self.compositeNodeYellow = self.yellowWidget.mrmlSliceCompositeNode()
    self.yellowSliceLogic = self.yellowWidget.sliceLogic()
    self.yellowSliceView = self.yellowWidget.sliceView()
    self.yellowSliceNode = self.yellowSliceLogic.GetSliceNode()
    self.currentFOVYellow = []

  def setupGreenSliceWidget(self):
    self.greenWidget = self.layoutManager.sliceWidget('Green')
    self.compositeNodeGreen = self.greenWidget.mrmlSliceCompositeNode()
    self.greenSliceLogic = self.greenWidget.sliceLogic()
    self.greenSliceNode = self.greenSliceLogic.GetSliceNode()

  def setStandardOrientation(self):
    self.redSliceNode.SetOrientationToAxial()
    self.yellowSliceNode.SetOrientationToSagittal()
    self.greenSliceNode.SetOrientationToCoronal()

  def setAxialOrientation(self):
    self.redSliceNode.SetOrientationToAxial()
    self.yellowSliceNode.SetOrientationToAxial()
    self.greenSliceNode.SetOrientationToAxial()

  def setupDataSelectionStep(self):
    # helperPixmap = qt.QPixmap(os.path.join(self.iconPath, 'icon-infoBox.png'))
    # helperPixmap = helperPixmap.scaled(qt.QSize(20, 20))
    # self.helperLabel = self.createLabel("", pixmap=helperPixmap, toolTip="This is the information you needed, right?")
    # rowLayout.addWidget(self.helperLabel)

    self.preopDirButton = self.createDirectoryButton(text="Preop Directory", caption="Choose Preop Location",
                                                     directory=self.getSetting('PreopLocation'), toolTip="Preop Directory")
    self.dataSelectionGroupBoxLayout.addRow(self.preopDirButton)

    self.outputDirButton = self.createDirectoryButton(caption="Choose Data Output Location", toolTip="Output Directory",
                                                      enabled=False)
    self.dataSelectionGroupBoxLayout.addRow(self.outputDirButton)

    self.intraopDirButton = self.createDirectoryButton(text="Intraop Directory", caption="Choose Intraop Location",
                                                       directory=self.getSetting('IntraopLocation'),
                                                       toolTip="Intraop Directory", enabled=False)
    self.dataSelectionGroupBoxLayout.addRow(self.intraopDirButton)

    self.targetTable = qt.QTableWidget()
    self.clearTargetTable()
    self.dataSelectionGroupBoxLayout.addRow(self.targetTable)

    self.intraopSeriesSelector = ctk.ctkCollapsibleGroupBox()
    self.intraopSeriesSelector.setTitle("Intraop series")
    self.dataSelectionGroupBoxLayout.addRow(self.intraopSeriesSelector)
    intraopSeriesSelectorLayout = qt.QFormLayout(self.intraopSeriesSelector)

    self.seriesView = qt.QListView()
    self.seriesView.setObjectName('SeriesTable')
    self.seriesView.setSpacing(3)
    self.seriesModel = qt.QStandardItemModel()
    self.seriesModel.setHorizontalHeaderLabels(['Series ID'])
    self.seriesView.setModel(self.seriesModel)
    self.seriesView.setSelectionMode(qt.QAbstractItemView.ExtendedSelection)
    self.seriesView.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
    intraopSeriesSelectorLayout.addWidget(self.seriesView)

    row = qt.QWidget()
    rowLayout = self.createAlignedRowLayout(row, alignment=qt.Qt.AlignRight)

    self.loadAndSegmentButton = self.createButton("Load and Segment", enabled=False, toolTip="Load and Segment")
    rowLayout.addWidget(self.loadAndSegmentButton)

    self.reRegButton = self.createButton("Re-Registration", toolTip="Re-Registration", enabled=False,
                                         styleSheet=STYLE.WHITE_BACKGROUND)
    rowLayout.addWidget(self.reRegButton)
    self.dataSelectionGroupBoxLayout.addWidget(row)

    self.saveDataButton = self.createButton('Case Completed', icon=self.littleDiscIcon, maximumWidth=150,
                                            enabled=os.path.exists(self.getSetting('OutputLocation')))

    self.outputDirButton.directory = self.getSetting('OutputLocation')
    self._outputRoot = self.outputDirButton.directory

    self.dataSelectionGroupBoxLayout.addRow(self.saveDataButton)


  def setupProstateSegmentationStep(self):

    # reference volume selector
    self.referenceVolumeSelector = self.createComboBox(nodeTypes=["vtkMRMLScalarVolumeNode", ""], noneEnabled=True,
                                                       selectNodeUponCreation=True, showChildNodeTypes=False,
                                                       toolTip="Pick the input to the algorithm.")

    self.labelSelectionGroupBoxLayout.addWidget(self.createHLayout([qt.QLabel('Reference Volume: '),
                                                                    self.referenceVolumeSelector ]))

    # Set Icon Size for the 4 Icon Items
    size = qt.QSize(70, 30)
    self.quickSegmentationButton = self.createButton('Quick Mode', icon=self.quickSegmentationIcon, iconSize=size,
                                                     styleSheet=STYLE.WHITE_BACKGROUND)

    self.labelSegmentationButton = self.createButton('Label Mode', icon=self.labelSegmentationIcon, iconSize=size,
                                                     styleSheet=STYLE.WHITE_BACKGROUND)

    self.applySegmentationButton = self.createButton("", icon=self.greenCheckIcon, iconSize=size,
                                                     styleSheet=STYLE.WHITE_BACKGROUND, enabled=False)

    self.cancelSegmentationButton = self.createButton("", icon=self.cancelSegmentationIcon,
                                                      iconSize=size, enabled=False)

    self.backButton = self.createButton("", icon=self.undoIcon, iconSize=size)
    self.forwardButton = self.createButton("", icon=self.redoIcon, iconSize=size)

    self.deactivateUndoRedoButtons()

    # Create ButtonBox to fill in those Buttons
    buttonBox1 = qt.QDialogButtonBox()
    buttonBox1.setLayoutDirection(1)
    buttonBox1.centerButtons = False
    buttonBox1.addButton(self.forwardButton, buttonBox1.ActionRole)
    buttonBox1.addButton(self.backButton, buttonBox1.ActionRole)
    buttonBox1.addButton(self.cancelSegmentationButton, buttonBox1.ActionRole)
    buttonBox1.addButton(self.applySegmentationButton, buttonBox1.ActionRole)
    buttonBox1.addButton(self.quickSegmentationButton, buttonBox1.ActionRole)
    buttonBox1.addButton(self.labelSegmentationButton, buttonBox1.ActionRole)
    self.labelSelectionGroupBoxLayout.addWidget(buttonBox1)

    # Editor Widget
    editorWidgetParent = slicer.qMRMLWidget()
    editorWidgetParent.setLayout(qt.QVBoxLayout())
    editorWidgetParent.setMRMLScene(slicer.mrmlScene)

    self.editUtil = EditorLib.EditUtil.EditUtil()
    self.editorWidget = EditorWidget(parent=editorWidgetParent, showVolumesFrame=False)
    self.editorWidget.setup()
    self.editorParameterNode = self.editUtil.getParameterNode()
    self.labelSelectionGroupBoxLayout.addRow(editorWidgetParent)

  def setupRegistrationStep(self):
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
    self.applyBSplineRegistrationButton = self.createButton("Apply Registration", icon=self.greenCheckIcon,
                                                            toolTip="Run the algorithm.")
    self.applyBSplineRegistrationButton.setFixedHeight(45)

    self.registrationGroupBoxLayout.addRow("Preop Image Volume: ", self.preopVolumeSelector)
    self.registrationGroupBoxLayout.addRow("Preop Label Volume: ", self.preopLabelSelector)
    self.registrationGroupBoxLayout.addRow("Intraop Image Volume: ", self.intraopVolumeSelector)
    self.registrationGroupBoxLayout.addRow("Intraop Label Volume: ", self.intraopLabelSelector)
    self.registrationGroupBoxLayout.addRow("Targets: ", self.fiducialSelector)
    self.registrationGroupBoxLayout.addRow(self.applyBSplineRegistrationButton)

  def setupRegistrationEvaluationStep(self):
    # Buttons which registration step should be shown
    groupBoxDisplay = qt.QGroupBox("Display")
    groupBoxDisplayLayout = qt.QFormLayout(groupBoxDisplay)
    self.evaluationGroupBoxLayout.addWidget(groupBoxDisplay)

    self.resultSelector = ctk.ctkComboBox()
    self.resultSelector.setFixedWidth(250)

    self.acceptRegistrationResultButton = self.createButton("Accept Result")
    self.retryRegistrationButton = self.createButton("Retry")
    self.skipRegistrationResultButton = self.createButton("Skip Result")

    self.acceptedRegistrationResultLabel = self.createLabel("", pixmap=self.acceptedIcon.pixmap(20, 20), hidden=True)
    self.discardedRegistrationResultLabel = self.createLabel("", pixmap=self.discardedIcon.pixmap(20, 20), hidden=True)
    self.registrationResultStatus = self.createLabel("accepted!", hidden=True)

    groupBoxDisplayLayout.addWidget(self.createHLayout([qt.QLabel('Registration Result'), self.resultSelector,
                                    self.acceptRegistrationResultButton, self.retryRegistrationButton,
                                    self.skipRegistrationResultButton, self.acceptedRegistrationResultLabel,
                                    self.discardedRegistrationResultLabel, self.registrationResultStatus]))

    self.showPreopResultButton = self.createButton('Show Cover Prostate')
    self.showRigidResultButton = self.createButton('Show Rigid Result')
    self.showAffineResultButton = self.createButton('Show Affine Result')
    self.showBSplineResultButton = self.createButton('Show BSpline Result')

    self.registrationButtonGroup = qt.QButtonGroup()
    self.registrationButtonGroup.addButton(self.showPreopResultButton, 1)
    self.registrationButtonGroup.addButton(self.showRigidResultButton, 2)
    self.registrationButtonGroup.addButton(self.showAffineResultButton, 3)
    self.registrationButtonGroup.addButton(self.showBSplineResultButton, 4)

    groupBoxDisplayLayout.addWidget(self.createHLayout([self.showPreopResultButton, self.showRigidResultButton,
                                                     self.showAffineResultButton, self.showBSplineResultButton]))

    self.visualEffectsGroupBox = qt.QGroupBox("Visual Evaluation")
    self.groupBoxLayout = qt.QFormLayout(self.visualEffectsGroupBox)
    self.evaluationGroupBoxLayout.addWidget(self.visualEffectsGroupBox)

    self.fadeSlider = ctk.ctkSliderWidget()
    self.fadeSlider.minimum = 0
    self.fadeSlider.maximum = 1.0
    self.fadeSlider.value = 0
    self.fadeSlider.singleStep = 0.05

    self.rockCount = 0
    self.rockTimer = qt.QTimer()
    self.rockCheckBox = qt.QCheckBox("Rock")
    self.rockCheckBox.checked = False

    self.flickerTimer = qt.QTimer()
    self.flickerCheckBox = qt.QCheckBox("Flicker")
    self.flickerCheckBox.checked = False

    animaHolder = self.createVLayout([self.rockCheckBox, self.flickerCheckBox])

    self.groupBoxLayout.addWidget(self.createHLayout([qt.QLabel('Opacity'), self.fadeSlider, animaHolder]))

    self.revealCursorCheckBox = qt.QCheckBox("Use RevealCursor")
    self.revealCursorCheckBox.checked = False
    self.groupBoxLayout.addRow("", self.revealCursorCheckBox)

    self.needleTipButton = qt.QPushButton('Set needle-tip')
    self.evaluationGroupBoxLayout.addWidget(self.needleTipButton)

  def setTabsEnabled(self, indexes, enabled):
    for index in indexes:
      self.tabBar.setTabEnabled(index, enabled)

  def createAlignedRowLayout(self, firstRow, alignment):
    rowLayout = qt.QHBoxLayout()
    rowLayout.setAlignment(alignment)
    firstRow.setLayout(rowLayout)
    rowLayout.setDirection(0)
    return rowLayout

  def setupConnections(self):

    def setupButtonConnections():
      self.preopDirButton.directorySelected.connect(self.onPreopDirSelected)
      self.outputDirButton.directorySelected.connect(self.onOutputDirSelected)
      self.intraopDirButton.directorySelected.connect(self.onIntraopDirSelected)
      self.reRegButton.clicked.connect(self.onReRegistrationClicked)
      self.forwardButton.clicked.connect(self.onForwardButtonClicked)
      self.backButton.clicked.connect(self.onBackButtonClicked)
      self.applyBSplineRegistrationButton.clicked.connect(self.onApplyRegistrationClicked)
      self.needleTipButton.clicked.connect(self.onNeedleTipButtonClicked)
      self.quickSegmentationButton.clicked.connect(self.onQuickSegmentationButtonClicked)
      self.cancelSegmentationButton.clicked.connect(self.onCancelSegmentationButtonClicked)
      self.labelSegmentationButton.clicked.connect(self.onLabelSegmentationButtonClicked)
      self.applySegmentationButton.clicked.connect(self.onApplySegmentationButtonClicked)
      self.acceptRegistrationResultButton.clicked.connect(self.onAcceptRegistrationResultButtonClicked)
      self.skipRegistrationResultButton.clicked.connect(self.onSkipRegistrationResultButtonClicked)
      self.retryRegistrationButton.clicked.connect(self.onRetryRegistrationButtonClicked)
      self.loadAndSegmentButton.clicked.connect(self.onLoadAndSegmentButtonClicked)
      self.saveDataButton.clicked.connect(self.onSaveDataButtonClicked)
      self.registrationButtonGroup.connect('buttonClicked(int)', self.onRegistrationButtonChecked)

    def setupSelectorConnections():
      self.referenceVolumeSelector.connect('currentNodeChanged(bool)', self.onTab2clicked)
      self.resultSelector.connect('currentIndexChanged(int)', self.onRegistrationResultSelected)
      self.preopVolumeSelector.connect('currentNodeChanged(bool)', self.updateRegistrationOverviewTab)
      self.intraopVolumeSelector.connect('currentNodeChanged(bool)', self.updateRegistrationOverviewTab)
      self.intraopLabelSelector.connect('currentNodeChanged(bool)', self.updateRegistrationOverviewTab)
      self.preopLabelSelector.connect('currentNodeChanged(bool)', self.updateRegistrationOverviewTab)
      self.fiducialSelector.connect('currentNodeChanged(bool)', self.updateRegistrationOverviewTab)

    def setupCheckBoxConnections():
      self.rockCheckBox.connect('toggled(bool)', self.onRockToggled)
      self.flickerCheckBox.connect('toggled(bool)', self.onFlickerToggled)
      self.revealCursorCheckBox.connect('toggled(bool)', self.revealToggled)

    def setupOtherConnections():
      self.tabWidget.connect('currentChanged(int)', self.onTabWidgetClicked)
      self.fadeSlider.connect('valueChanged(double)', self.changeOpacity)
      self.rockTimer.connect('timeout()', self.onRockToggled)
      self.flickerTimer.connect('timeout()', self.onFlickerToggled)
      self.seriesModel.itemChanged.connect(self.updateSeriesSelectionButtons)

    setupCheckBoxConnections()
    setupButtonConnections()
    setupSelectorConnections()
    setupOtherConnections()

  def onRegistrationButtonChecked(self, buttonId):
    self.hideAllTargets()
    if buttonId == 1:
      self.onPreopResultClicked()
    elif buttonId == 2:
      self.onRigidResultClicked()
    elif buttonId == 3:
      if not self.currentResult.affineTargets:
        return self.onRegistrationButtonChecked(4)
      self.onAffineResultClicked()
    elif buttonId == 4:
      self.onBSplineResultClicked()
    self.activeRegistrationResultButtonId = buttonId

  def cleanup(self):
    ScriptedLoadableModuleWidget.cleanup(self)

  def deactivateUndoRedoButtons(self):
    self.forwardButton.setEnabled(0)
    self.backButton.setEnabled(0)

  def updateUndoRedoButtons(self, observer=None, caller=None):
    self.updateBackButton()
    self.updateForwardButton()

  def updateBackButton(self):
    if self.logic.inputMarkupNode.GetNumberOfFiducials() > 0:
      self.backButton.setEnabled(1)
    else:
      self.backButton.setEnabled(0)

  def updateForwardButton(self):
    if self.deletedMarkups.GetNumberOfFiducials() > 0:
      self.forwardButton.setEnabled(1)
    else:
      self.forwardButton.setEnabled(0)

  def onLoadAndSegmentButtonClicked(self):
    self.logic.retryMode = False
    selectedSeriesList = self.getSelectedSeries()

    if len(selectedSeriesList) > 0:
      if self.reRegistrationMode:
        if not self.yesNoDialog("You are currently in the Re-Registration mode. Are you sure, that you want to "
                                "recreate the segmentation?"):
          return

      # TODO: delete volumes when starting new instead of just clearing
      self.logic.clearAlreadyLoadedSeries()
      self.logic.loadSeriesIntoSlicer(selectedSeriesList)
      if self.logic.currentIntraopVolume:
        self.tabBar.setTabEnabled(1, True)
        self.tabWidget.setCurrentIndex(1)

  def onReRegistrationClicked(self):
    logging.debug('Performing Re-Registration')

    selectedSeriesList = self.getSelectedSeries()

    if len(selectedSeriesList) == 1:
      self.logic.loadSeriesIntoSlicer(selectedSeriesList)
      if self.logic.currentIntraopVolume:
        self.onInvokeReRegistration()
    else:
      self.warningDialog("You need to select ONE series for doing a Re-Registration. Please repeat your selection and "
                         "press Re-Registration again.")

  def uncheckSeriesSelectionItems(self):
    for item in range(len(self.logic.seriesList)):
      self.seriesModel.item(item).setCheckState(0)

  def updateSeriesSelectionButtons(self, item=None):
    checkedItemCount = len(self.getSelectedSeries())
    if checkedItemCount == 0 or (self.reRegistrationMode and checkedItemCount > 1):
      self.reRegButton.setEnabled(False)
    elif self.reRegistrationMode and checkedItemCount == 1:
      self.reRegButton.setEnabled(True)
    self.loadAndSegmentButton.setEnabled(checkedItemCount != 0)

  def updateRegistrationResultSelector(self):
    for name in [result.name for result in self.registrationResults.getResultsAsList()]:
      if self.resultSelector.findText(name) == -1:
        self.resultSelector.addItem(name)
        self.resultSelector.currentIndex = self.resultSelector.findText(name)

  def onNeedleTipButtonClicked(self):
    self.needleTipButton.enabled = False
    self.logic.setNeedleTipPosition(destinationViewNode=self.yellowSliceNode, callback=self.updateTargetTable)
    self.clearTargetTable()
    self.needleTipButton.enabled = False

  def clearTargetTable(self):
    self.targetTable.clear()
    self.targetTable.setColumnCount(3)
    self.targetTable.setHorizontalHeaderLabels(['Target', 'Needle-tip distance 2D [mm]', 'Needle-tip distance 3D [mm]'])
    self.targetTable.horizontalHeader().setResizeMode(qt.QHeaderView.Stretch)

  def updateTargetTable(self, observer=None, caller=None):
    self.clearTargetTable()
    bSplineTargets = self.currentResult.bSplineTargets
    number_of_targets = bSplineTargets.GetNumberOfFiducials()

    needleTip_position, target_positions = self.logic.getNeedleTipAndTargetsPositions(bSplineTargets)

    self.targetTable.setRowCount(number_of_targets)
    self.target_items = []

    for target in range(number_of_targets):
      target_text = bSplineTargets.GetNthFiducialLabel(target)
      item = qt.QTableWidgetItem(target_text)
      self.targetTable.setItem(target, 0, item)
      # make sure to keep a reference to the item
      self.target_items.append(item)

    if len(needleTip_position) > 0:
      self.items_2D = []
      self.items_3D = []

      for index in range(number_of_targets):
        distances = self.logic.measureDistance(target_positions[index], needleTip_position)
        text_for_2D_column = ('x = ' + str(round(distances[0], 2)) + ' y = ' + str(round(distances[1], 2)))
        text_for_3D_column = str(round(distances[3], 2))

        item_2D = qt.QTableWidgetItem(text_for_2D_column)
        self.targetTable.setItem(index, 1, item_2D)
        self.items_2D.append(item_2D)
        logging.debug(str(text_for_2D_column))

        item_3D = qt.QTableWidgetItem(text_for_3D_column)
        self.targetTable.setItem(index, 2, item_3D)
        self.items_3D.append(item_3D)
        logging.debug(str(text_for_3D_column))

    self.needleTipButton.enabled = True

  def removeSliceAnnotations(self):
    try:
      self.red_renderer.RemoveActor(self.text_preop)
      self.yellow_renderer.RemoveActor(self.text_intraop)
      self.redSliceView.update()
      self.yellowSliceView.update()
    except:
      pass

  def addSliceAnnotations(self):
    self.removeSliceAnnotations()
    # TODO: adapt when zoom is changed manually
    width = self.redSliceView.width
    renderWindow = self.redSliceView.renderWindow()
    self.red_renderer = renderWindow.GetRenderers().GetItemAsObject(0)

    self.text_preop = vtk.vtkTextActor()
    self.text_preop.SetInput('PREOP')
    textProperty = self.text_preop.GetTextProperty()
    textProperty.SetFontSize(70)
    textProperty.SetColor(1, 0, 0)
    textProperty.SetBold(1)
    self.text_preop.SetTextProperty(textProperty)

    # TODO: the 90px shift to the left are hard-coded right now, it would be better to
    # take the size of the vtk.vtkTextActor and shift by that size * 0.5
    # BUT -> could not find how to get vtkViewPort from sliceWidget

    self.text_preop.SetDisplayPosition(int(width * 0.5 - 90), 50)
    self.red_renderer.AddActor(self.text_preop)
    self.redSliceView.update()

    renderWindow = self.yellowSliceView.renderWindow()
    self.yellow_renderer = renderWindow.GetRenderers().GetItemAsObject(0)

    self.text_intraop = vtk.vtkTextActor()
    self.text_intraop.SetInput('INTRAOP')
    textProperty = self.text_intraop.GetTextProperty()
    textProperty.SetFontSize(70)
    textProperty.SetColor(1, 0, 0)
    textProperty.SetBold(1)
    self.text_intraop.SetTextProperty(textProperty)
    self.text_intraop.SetDisplayPosition(int(width * 0.5 - 140), 50)
    self.yellow_renderer.AddActor(self.text_intraop)
    self.yellowSliceView.update()

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
    """Turn the RevealCursor on or off
    """
    if self.revealCursor:
      self.revealCursor.tearDown()
    if checked:
      import CompareVolumes
      self.revealCursor = CompareVolumes.LayerReveal()

  def onRockToggled(self):
    if self.rockCheckBox.checked:
      self.flickerCheckBox.setEnabled(False)
      self.rockTimer.start(50)
      self.fadeSlider.value = 0.5 + math.sin(self.rockCount / 10.) / 2.
      self.rockCount += 1
    else:
      self.flickerCheckBox.setEnabled(True)
      self.rockTimer.stop()
      self.fadeSlider.value = 0.0

  def onFlickerToggled(self):
    if self.flickerCheckBox.checked:
      self.rockCheckBox.setEnabled(False)
      self.flickerTimer.start(300)
      self.fadeSlider.value = 1.0 if self.fadeSlider.value == 0.0 else 0.0
    else:
      self.rockCheckBox.setEnabled(True)
      self.flickerTimer.stop()
      self.fadeSlider.value = 0.0

  def onPreopDirSelected(self):
    self.preopDataDir = self.preopDirButton.directory

  def onIntraopDirSelected(self):
    self.intraopDataDir = self.intraopDirButton.directory

  def onOutputDirSelected(self):
    self.outputDir = self.outputDirButton.directory

  def onSaveDataButtonClicked(self):
    return self.notificationDialog(self.logic.save())

  def onTabWidgetClicked(self):
    if self.tabWidget.currentIndex == 0:
      self.onTab1clicked()
    if self.tabWidget.currentIndex == 1:
      self.onTab2clicked()
    if self.tabWidget.currentIndex == 2:
      self.onTab3clicked()
    if self.tabWidget.currentIndex == 3:
      self.onTab4clicked()

  def onTab1clicked(self):
    # (re)set the standard Icon
    self.removeSliceAnnotations()
    if self.currentTabIndex == 3:
      lastRegistrationResult = self.registrationResults.getMostRecentResult()
      if not lastRegistrationResult.accepted and not lastRegistrationResult.skipped:
        self.warningDialog("You need to accept or retry the most recent registration before continuing "
                            "with further registrations.")
        self.tabWidget.setCurrentIndex(3)
    self.currentTabIndex = 0
    self.tabBar.setTabIcon(0, self.dataSelectionIcon)
    self.uncheckVisualEffects()

  def uncheckVisualEffects(self):
    self.flickerCheckBox.checked = False
    self.rockCheckBox.checked = False

  def onTab2clicked(self):
    if self.logic.retryMode:
      self.setTabsEnabled([0], False)

    self.removeSliceAnnotations()

    self.referenceVolumeSelector.setCurrentNode(self.logic.currentIntraopVolume)
    self.intraopVolumeSelector.setCurrentNode(self.logic.currentIntraopVolume)

    enableButton = 0 if self.referenceVolumeSelector.currentNode() is None else 1
    self.labelSegmentationButton.setEnabled(enableButton)
    self.quickSegmentationButton.setEnabled(enableButton)

    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    self.compositeNodeRed.Reset()
    self.setTargetVisibility(self.preopTargets, show=False)
    self.compositeNodeRed.SetBackgroundVolumeID(self.logic.currentIntraopVolume.GetID())

    self.setStandardOrientation()
    slicer.app.applicationLogic().FitSliceToAll()

  def onTab3clicked(self):
    self.currentTabIndex = 2
    self.updateRegistrationOverviewTab()

  def updateRegistrationOverviewTab(self):
    if self.tabBar.currentIndex == 2:
      self.setupScreenAfterSegmentation()

  def inputsAreSet(self):
    return not (self.preopVolumeSelector.currentNode() is None and self.intraopVolumeSelector.currentNode() is None and
                self.preopLabelSelector.currentNode() is None and self.intraopLabelSelector.currentNode() is None and
                self.fiducialSelector.currentNode() is None)

  def onTab4clicked(self):
    if self.logic.retryMode:
      self.setTabsEnabled([0], True)
      self.logic.retryMode = False

    self.currentTabIndex = 3

    self.setTabsEnabled([1, 2], False)

    # enable re-registration function
    self.reRegButton.setEnabled(1)
    self.reRegistrationMode = True

    self.setupScreenAfterRegistration()
    self.addSliceAnnotations()

  def updateCurrentPatientAndViewBox(self, currentFile):
    self.currentID = self.logic.getDICOMValue(currentFile, DICOMTAGS.PATIENT_ID)
    self.patientID.setText(self.currentID)
    self.updatePatientBirthdate(currentFile)
    self.updateCurrentStudyDate()
    self.updatePreopStudyDate(currentFile)
    self.updatePatientName(currentFile)

  def updatePreopStudyDate(self, currentFile):
    preopStudyDateDICOM = self.logic.getDICOMValue(currentFile, DICOMTAGS.STUDY_DATE)
    formattedDate = preopStudyDateDICOM[0:4] + "-" + preopStudyDateDICOM[4:6] + "-" + \
                    preopStudyDateDICOM[6:8]
    self.preopStudyDate.setText(formattedDate)

  def updateCurrentStudyDate(self):
    currentStudyDate = qt.QDate().currentDate()
    self.currentStudyDate.setText(str(currentStudyDate))

  def updatePatientBirthdate(self, currentFile):
    currentBirthDateDICOM = self.logic.getDICOMValue(currentFile, DICOMTAGS.PATIENT_BIRTH_DATE)
    if currentBirthDateDICOM is None:
      self.patientBirthDate.setText('No Date found')
    else:
      # convert date of birth from 19550112 (yyyymmdd) to 1955-01-12
      currentBirthDateDICOM = str(currentBirthDateDICOM)
      self.currentBirthDate = currentBirthDateDICOM[0:4] + "-" + currentBirthDateDICOM[
                                                                 4:6] + "-" + currentBirthDateDICOM[6:8]
      self.patientBirthDate.setText(self.currentBirthDate)

  def updatePatientName(self, currentFile):
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

  def updateSeriesSelectorTable(self):
    self.seriesModel.clear()
    self.seriesItems = []
    seriesList = self.logic.seriesList
    for series in seriesList:
      sItem = qt.QStandardItem(series)
      self.seriesItems.append(sItem)
      self.seriesModel.appendRow(sItem)
      sItem.setCheckable(0)
      color = COLOR.YELLOW
      seriesNumber = int(series.split(": ")[0])
      if self.logic.registrationResultWasAccepted(seriesNumber):
        color = COLOR.GREEN
      elif self.logic.registrationResultWasSkipped(seriesNumber):
        color = COLOR.RED
      elif self.logic.registrationResultWasRejected(seriesNumber):
        color = COLOR.GRAY
      else:
        sItem.setCheckable(1)
      self.seriesModel.setData(sItem.index(), color, qt.Qt.BackgroundRole)

    for item in list(reversed(range(len(seriesList)))):
      series = self.seriesModel.item(item).text()
      if "PROSTATE" in series or "GUIDANCE" in series:
        self.seriesModel.item(item).setCheckState(1)
        break
    self.updateSeriesSelectionButtons()

  def resetShowResultButtons(self, checkedButton):
    checked = STYLE.GRAY_BACKGROUND_WHITE_FONT
    unchecked = STYLE.WHITE_BACKGROUND
    for button in self.registrationButtonGroup.buttons():
      button.setStyleSheet(checked if button is checkedButton else unchecked)

  def onRegistrationResultSelected(self):
    self.hideAllTargets()

    self.currentResult = self.resultSelector.currentText

    # TODO: think about the following lines
    # depends on: if a previous registration was retried, which results were accepted:
    #             Is this the case, we need to take the label of the redone registration
    self.logic.currentIntraopVolume = self.registrationResults.getMostRecentResult().fixedVolume
    self.preopVolume = self.registrationResults.getMostRecentResult().movingVolume

    self.showAffineResultButton.setEnabled("GUIDANCE" not in self.resultSelector.currentText)

    self.onRegistrationButtonChecked(self.activeRegistrationResultButtonId)
    self.updateRegistrationResultStatus()
    self.updateTargetTable()

  def hideAllTargets(self):
    for result in self.registrationResults.getResultsAsList():
      for targetNode in [targets for targets in result.targets.values() if targets]:
        self.setTargetVisibility(targetNode, show=False)

  def onPreopResultClicked(self):
    self.saveCurrentSliceViewPositions()
    self.resetShowResultButtons(checkedButton=self.showPreopResultButton)

    self.unlinkImages()

    self.compositeNodeRed.SetBackgroundVolumeID(self.currentResult.movingVolume.GetID())
    self.compositeNodeRed.SetForegroundVolumeID(self.currentResult.fixedVolume.GetID())

    fiducialNode = self.currentResult.originalTargets
    self.setTargetVisibility(fiducialNode)

    self.setDefaultFOV(self.redSliceLogic)

    # jump to first markup slice
    self.markupsLogic.JumpSlicesToNthPointInMarkup(fiducialNode.GetID(), 0)

    restoredSlicePositions = self.savedSlicePositions
    self.setFOV(self.yellowSliceLogic, restoredSlicePositions['yellowFOV'], restoredSlicePositions['yellowOffset'])

    self.comingFromPreopTag = True

  def onRigidResultClicked(self):
    self.displayRegistrationResults(button=self.showRigidResultButton, registrationType='rigid')

  def onAffineResultClicked(self):
    self.displayRegistrationResults(button=self.showAffineResultButton, registrationType='affine')

  def onBSplineResultClicked(self):
    self.displayRegistrationResults(button=self.showBSplineResultButton, registrationType='bSpline')

  def displayRegistrationResults(self, button, registrationType):
    self.resetShowResultButtons(checkedButton=button)

    self.linkImages()
    self.setCurrentRegistrationResultSliceViews(registrationType)

    if self.comingFromPreopTag:
      self.resetSliceViews()
    else:
      self.setDefaultFOV(self.redSliceLogic)
      self.setDefaultFOV(self.yellowSliceLogic)

    self.showTargets(registrationType=registrationType)
    self.visualEffectsGroupBox.setEnabled(True)

  def setDefaultFOV(self, sliceLogic):
    sliceLogic.FitSliceToAll()
    FOV = sliceLogic.GetSliceNode().GetFieldOfView()
    self.setFOV(sliceLogic, [FOV[0] * 0.5, FOV[1] * 0.5, FOV[2]])

  def setFOV(self, sliceLogic, FOV, offset=None):
    sliceNode = sliceLogic.GetSliceNode()
    sliceLogic.StartSliceNodeInteraction(2)
    sliceNode.SetFieldOfView(FOV[0], FOV[1], FOV[2])
    if offset:
      sliceNode.SetSliceOffset(offset)
    sliceLogic.EndSliceNodeInteraction()

  def unlinkImages(self):
    self._linkImages(0)

  def linkImages(self):
    self._linkImages(1)

  def _linkImages(self, link):
    self.compositeNodeRed.SetLinkedControl(link)
    self.compositeNodeYellow.SetLinkedControl(link)

  def setCurrentRegistrationResultSliceViews(self, registrationType):
    self.compositeNodeYellow.SetBackgroundVolumeID(self.currentResult.fixedVolume.GetID())
    self.compositeNodeRed.SetForegroundVolumeID(self.currentResult.fixedVolume.GetID())
    self.compositeNodeRed.SetBackgroundVolumeID(self.currentResult.getVolume(registrationType).GetID())

  def showTargets(self, registrationType):
    self.setTargetVisibility(self.currentResult.rigidTargets, show=registrationType == 'rigid')
    self.setTargetVisibility(self.currentResult.bSplineTargets, show=registrationType == 'bSpline')
    if self.currentResult.affineTargets:
      self.setTargetVisibility(self.currentResult.affineTargets, show=registrationType == 'affine')
    targets = getattr(self.currentResult, registrationType+'Targets')
    self.markupsLogic.JumpSlicesToNthPointInMarkup(targets.GetID(), 0)

  def setTargetVisibility(self, targetNode, show=True):
    self.markupsLogic.SetAllMarkupsVisibility(targetNode, show)

  def resetSliceViews(self):

    restoredSliceOptions = self.savedSlicePositions

    self.redSliceLogic.FitSliceToAll()
    self.yellowSliceLogic.FitSliceToAll()

    self.setFOV(self.yellowSliceLogic, restoredSliceOptions['yellowFOV'], restoredSliceOptions['yellowOffset'])
    self.setFOV(self.redSliceLogic, restoredSliceOptions['redFOV'], restoredSliceOptions['redOffset'])

    self.comingFromPreopTag = False

  def saveCurrentSliceViewPositions(self):
    self.savedSlicePositions = {'redOffset': self.redSliceNode.GetSliceOffset(),
                                'yellowOffset': self.yellowSliceNode.GetSliceOffset(),
                                'redFOV': self.redSliceNode.GetFieldOfView(),
                                'yellowFOV': self.yellowSliceNode.GetFieldOfView()}

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

  def loadPCAMPReviewProcessedData(self):
    resourcesDir = os.path.join(self.preopDataDir, 'RESOURCES')
    self.preopTargetsPath = os.path.join(self.preopDataDir, 'Targets')

    if not os.path.exists(resourcesDir):
      self.confirmDialog("The selected directory does not fit the PCampReview directory structure. Make sure that you "
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
          self.confirmDialog("No segmentations found.\nMake sure that you used PCampReview for segmenting the prostate "
                             "first and using its output as the preop data input here.")
          return False
        self.preopImagePath = self.seriesMap[series]['NRRDLocation']
        self.preopSegmentationPath = segmentationPath

        self.preopSegmentations = os.listdir(segmentationPath)

        logging.debug(str(self.preopSegmentations))

        break

    return True

  def loadPreopData(self):
    if not self.loadPCAMPReviewProcessedData():
      return
    self.configureSliceNodesForPreopData()
    if not self.loadT2Label() or not self.loadPreopVolume() or not self.loadPreopTargets():
      self.warningDialog("Loading preop data failed.\nMake sure that the correct directory structure like PCampReview "
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

    # set markups for registration
    self.fiducialSelector.setCurrentNode(self.preopTargets)

    # jump to first markup slice
    self.markupsLogic.JumpSlicesToNthPointInMarkup(self.preopTargets.GetID(), 0)

    # Set Fiducial Properties
    markupsDisplayNode = self.preopTargets.GetDisplayNode()
    markupsDisplayNode.SetTextScale(1.9)
    markupsDisplayNode.SetGlyphScale(1.0)

    self.compositeNodeRed.SetLabelOpacity(1)

    # set Layout to redSliceViewOnly
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    self.setDefaultFOV(self.redSliceLogic)

    # TODO: Update target table, but not with registered targets ...
    # self.updateTargetTable()

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

  def getSelectedSeries(self):
    checkedItems = [x for x in self.seriesItems if x.checkState()] if self.seriesItems else []
    return [x.text() for x in checkedItems]

  def onCancelSegmentationButtonClicked(self):
    if self.yesNoDialog("Do you really want to cancel the segmentation process?"):
      if self.quickSegmentationActive:
        self.setQuickSegmentationModeOFF()
      else:
        self.editorParameterNode.SetParameter('effect', 'DefaultTool')
        slicer.mrmlScene.RemoveNode(self.currentIntraopLabel)
        self.compositeNodeRed.SetLabelVolumeID(None)
      self.setSegmentationButtons(segmentationActive=False)

  def onQuickSegmentationButtonClicked(self):
    self.clearCurrentLabels()
    self.setBackgroundToCurrentReferenceVolume()
    self.setQuickSegmentationModeON()

  def setBackgroundToCurrentReferenceVolume(self):
    self.compositeNodeRed.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())
    self.compositeNodeYellow.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())
    self.compositeNodeGreen.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())

  def clearCurrentLabels(self):
    self.compositeNodeRed.SetLabelVolumeID(None)
    self.compositeNodeYellow.SetLabelVolumeID(None)
    self.compositeNodeGreen.SetLabelVolumeID(None)

  def setQuickSegmentationModeON(self):
    self.quickSegmentationActive = True
    self.logic.deleteClippingData()
    self.setSegmentationButtons(segmentationActive=True)
    self.deactivateUndoRedoButtons()
    self.setupQuickModeHistory()
    self.logic.runQuickSegmentationMode()
    self.logic.inputMarkupNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.updateUndoRedoButtons)

  def setupQuickModeHistory(self):
    try:
      self.deletedMarkups.Reset()
    except AttributeError:
      self.deletedMarkups = slicer.vtkMRMLMarkupsFiducialNode()
      self.deletedMarkups.SetName('deletedMarkups')

  def setQuickSegmentationModeOFF(self):
    self.quickSegmentationActive = False
    self.setSegmentationButtons(segmentationActive=False)
    self.deactivateUndoRedoButtons()
    self.resetToRegularViewMode()

  def resetToRegularViewMode(self):
    interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
    interactionNode.SwitchToViewTransformMode()
    interactionNode.SetPlaceModePersistence(0)

  def changeOpacity(self, value):
    self.compositeNodeRed.SetForegroundOpacity(value)

  def onAcceptRegistrationResultButtonClicked(self):
    self.currentResult.accept()
    for result in self.registrationResults.getResultsAsList():
      if result is not self.currentResult:
        if self.currentResult.seriesNumber == result.seriesNumber:
          result.skip()
    self.updateRegistrationResultStatus()

  def onSkipRegistrationResultButtonClicked(self):
    self.currentResult.skip()
    self.updateRegistrationResultStatus()

  def updateRegistrationResultStatus(self):
    if self.currentResult.accepted or self.currentResult.skipped:
      self.acceptRegistrationResultButton.hide()
      self.retryRegistrationButton.hide()
      self.skipRegistrationResultButton.hide()
      self.registrationResultStatus.show()
      if self.currentResult.accepted and not self.currentResult.skipped:
        self.discardedRegistrationResultLabel.hide()
        self.acceptedRegistrationResultLabel.show()
        self.registrationResultStatus.setText("accepted!")
      elif self.currentResult.skipped:
        self.acceptedRegistrationResultLabel.hide()
        self.discardedRegistrationResultLabel.show()
        if self.currentResult.accepted:
          self.registrationResultStatus.setText("skipped!")
        else:
          self.registrationResultStatus.setText("discarded!")
    else:
      self.acceptRegistrationResultButton.show()
      self.retryRegistrationButton.show()
      self.skipRegistrationResultButton.show()
      self.acceptedRegistrationResultLabel.hide()
      self.discardedRegistrationResultLabel.hide()
      self.registrationResultStatus.hide()
    self.updateSeriesSelectorTable()

  def onApplySegmentationButtonClicked(self):
    self.setAxialOrientation()
    if self.quickSegmentationActive is True:
      self.onQuickSegmentationFinished()
    else:
      self.onLabelSegmentationFinished()

  def setSegmentationButtons(self, segmentationActive=False):
    self.quickSegmentationButton.setEnabled(not segmentationActive)
    self.labelSegmentationButton.setEnabled(not segmentationActive)
    self.applySegmentationButton.setEnabled(segmentationActive)
    self.cancelSegmentationButton.setEnabled(segmentationActive)

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

  def onLabelSegmentationFinished(self):
    continueSegmentation = False
    deleteMask = False
    if self.isIntraopLabelValid():
      logic = EditorLib.DilateEffectLogic(self.editUtil.getSliceLogic())
      logic.erode(0, '4', 1)
      self.setupScreenAfterSegmentation()
    else:
      if self.yesNoDialog("You need to do a label segmentation. Do you want to continue using the label mode?"):
        continueSegmentation = True
      else:
        deleteMask = True
    if not continueSegmentation:
      self.editorParameterNode.SetParameter('effect', 'DefaultTool')
      self.setSegmentationButtons(segmentationActive=False)
      if deleteMask:
        slicer.mrmlScene.RemoveNode(self.currentIntraopLabel)

  def isIntraopLabelValid(self):
    labelAddress = sitkUtils.GetSlicerITKReadWriteAddress(self.currentIntraopLabel.GetName())
    labelImage = sitk.ReadImage(labelAddress)

    ls = sitk.LabelStatisticsImageFilter()
    ls.Execute(labelImage, labelImage)
    return ls.GetNumberOfLabels() == 2

  def setupScreenAfterSegmentation(self):
    self.clearCurrentLabels()

    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView)

    if self.logic.retryMode:
      coverProstateRegResult = self.registrationResults.getMostRecentAcceptedCoverProstateRegistration()
      if coverProstateRegResult:
        self.preopVolumeSelector.setCurrentNode(coverProstateRegResult.fixedVolume)
        self.preopLabelSelector.setCurrentNode(coverProstateRegResult.fixedLabel)
        self.fiducialSelector.setCurrentNode(coverProstateRegResult.bSplineTargets)

    preopVolume = self.preopVolumeSelector.currentNode()
    preopLabel = self.preopLabelSelector.currentNode()
    intraopVolume = self.intraopVolumeSelector.currentNode()
    intraopLabel = self.intraopLabelSelector.currentNode()

    # set up preop image and label
    self.compositeNodeRed.SetReferenceBackgroundVolumeID(preopVolume.GetID())
    self.compositeNodeRed.SetLabelVolumeID(preopLabel.GetID())

    # set up intraop image and label
    self.compositeNodeYellow.SetReferenceBackgroundVolumeID(intraopVolume.GetID())
    self.compositeNodeYellow.SetLabelVolumeID(intraopLabel.GetID())

    # rotate volume to plane
    self.redSliceNode.RotateToVolumePlane(preopVolume)
    self.yellowSliceNode.RotateToVolumePlane(intraopLabel)

    self.redSliceLogic.FitSliceToAll()
    self.yellowSliceLogic.FitSliceToAll()

    self.yellowSliceNode.SetFieldOfView(86, 136, 3.5)
    self.redSliceNode.SetFieldOfView(86, 136, 3.5)

    self.tabBar.setTabEnabled(2, True)
    self.tabBar.currentIndex = 2

    self.applyBSplineRegistrationButton.setEnabled(1 if self.inputsAreSet() else 0)

  def onLabelSegmentationButtonClicked(self):
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    self.clearCurrentLabels()
    self.setSegmentationButtons(segmentationActive=True)
    self.compositeNodeRed.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())

    referenceVolume = self.referenceVolumeSelector.currentNode()
    self.currentIntraopLabel = self.volumesLogic.CreateAndAddLabelVolume(slicer.mrmlScene, referenceVolume,
                                                                         referenceVolume.GetName() + '-label')
    self.intraopLabelSelector.setCurrentNode(self.currentIntraopLabel)
    selectionNode = slicer.app.applicationLogic().GetSelectionNode()
    selectionNode.SetReferenceActiveVolumeID(referenceVolume.GetID())
    selectionNode.SetReferenceActiveLabelVolumeID(self.currentIntraopLabel.GetID())
    slicer.app.applicationLogic().PropagateVolumeSelection(50)

    self.compositeNodeRed.SetLabelOpacity(1)

    # set color table
    logging.debug('intraopLabelID : ' + str(self.currentIntraopLabel.GetID()))

    # set color table
    displayNode = self.currentIntraopLabel.GetDisplayNode()
    displayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNode1')

    parameterNode = self.editUtil.getParameterNode()
    parameterNode.SetParameter('effect', 'DrawEffect')

    self.editUtil.setLabel(1)
    self.editUtil.setLabelOutline(1)

  def onApplyRegistrationClicked(self):
    self.progress = self.makeProgressIndicator(4, 1)
    self.logic.applyRegistration(fixedVolume=self.intraopVolumeSelector.currentNode(),
                                 sourceVolume=self.preopVolumeSelector.currentNode(),
                                 fixedLabel=self.intraopLabelSelector.currentNode(),
                                 movingLabel=self.preopLabelSelector.currentNode(),
                                 targets=self.fiducialSelector.currentNode())
    self.progress.close()
    self.progress = None
    self.finalizeRegistrationStep()
    logging.debug('Registration is done')

  def onInvokeReRegistration(self):
    self.progress = self.makeProgressIndicator(4, 1)
    self.logic.applyReRegistration(progressCallback=self.updateProgressBar)
    self.progress.close()
    self.progress = None
    self.finalizeRegistrationStep()
    logging.debug('Re-Registration is done')

  def updateProgressBar(self, **kwargs):
    if self.progress:
      for key, value in kwargs.iteritems():
        if hasattr(self.progress, key):
          setattr(self.progress, key, value)

  def onRetryRegistrationButtonClicked(self):
    # if self.yesNoDialog("Do you really want to discard the current registration results and reate a new segmentation "
    #                     "label on the current needle image?"):
    # self.logic.deleteRegistrationResult(-1)
    self.logic.retryMode = True
    self.tabWidget.setCurrentIndex(1)

  def finalizeRegistrationStep(self):
    self.updateDisplayedTargets()
    self.activeRegistrationResultButtonId = 4
    self.updateRegistrationResultSelector()
    self.tabWidget.setCurrentIndex(3)
    self.uncheckSeriesSelectionItems()
    self.currentResult.printSummary()

  def updateDisplayedTargets(self):
    for targetNode in [targets for targets in self.currentResult.targets.values() if targets]:
      slicer.mrmlScene.AddNode(targetNode)

  def setupScreenAfterRegistration(self):

    self.compositeNodeRed.SetForegroundVolumeID(self.logic.currentIntraopVolume.GetID())
    self.compositeNodeRed.SetBackgroundVolumeID(self.registrationResults.getMostRecentResult().rigidVolume.GetID())
    self.compositeNodeYellow.SetBackgroundVolumeID(self.logic.currentIntraopVolume.GetID())

    self.redSliceLogic.FitSliceToAll()
    self.yellowSliceLogic.FitSliceToAll()

    self.refreshViewNodeIDs(self.preopTargets, self.redSliceNode)
    for targetNode in [targets for targets in self.currentResult.targets.values() if targets]:
      self.refreshViewNodeIDs(targetNode, self.yellowSliceNode)

    self.resetToRegularViewMode()

    # set Side By Side View to compare volumes
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView)

    # Hide Labels
    self.compositeNodeRed.SetLabelOpacity(0)
    self.compositeNodeYellow.SetLabelOpacity(0)

    self.setAxialOrientation()

    self.tabBar.setTabEnabled(3, True)

    self.onBSplineResultClicked()

  def refreshViewNodeIDs(self, targets, sliceNode):
    # remove view node ID's from Red Slice view
    displayNode = targets.GetDisplayNode()
    displayNode.RemoveAllViewNodeIDs()
    displayNode.AddViewNodeID(sliceNode.GetID())

  def onNewImageDataReceived(self, **kwargs):
    newFileList = kwargs.pop('newList')
    self.patientCheckAfterImport(newFileList)
    # change icon of tabBar if user is not in Data selection tab
    if not self.tabWidget.currentIndex == 0:
      self.tabBar.setTabIcon(0, self.newImageDataIcon)


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
    self.reRegistrationMode = False
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

  def registrationResultWasAccepted(self, seriesNumber):
    results = self.registrationResults.getResultsBySeriesNumber(seriesNumber)
    return any(result.accepted is True for result in results) if len(results) else False

  def registrationResultWasSkipped(self, seriesNumber):
    results = self.registrationResults.getResultsBySeriesNumber(seriesNumber)
    return any(result.skipped is True for result in results) if len(results) else False

  def registrationResultWasRejected(self, seriesNumber):
    results = self.registrationResults.getResultsBySeriesNumber(seriesNumber)
    return all(result.rejected is True for result in results) if len(results) else False

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

  def createVolumeAndTransformNodes(self, registrationTypes, suffix):
    for regType in registrationTypes:
      isBSpline = regType == 'bSpline'
      self.currentResult.setVolume(regType, self.createScalarVolumeNode(suffix + '-VOLUME-' + regType))
      self.currentResult.setTransform(regType, self.createTransformNode(suffix + '-TRANSFORM-' + regType, isBSpline))

  def transformTargets(self, registrations, targets, prefix):
    if targets:
      for registration in registrations:
        name = prefix + '-TARGETS-' + registration
        clone = self.cloneFiducialAndTransform(name, targets, self.currentResult.getTransform(registration))
        self.currentResult.setTargets(registration, clone)

  def applyRegistration(self, fixedVolume, sourceVolume, fixedLabel, movingLabel, targets, progressCallback=None):

    self.progressCallback = progressCallback
    if not self.retryMode:
      self.registrationResults = RegistrationResults()
    name = self.generateNameForRegistrationResult(fixedVolume)
    result = self.registrationResults.createResult(name)
    result.fixedVolume = fixedVolume
    result.fixedLabel = fixedLabel
    result.movingLabel = movingLabel
    result.originalTargets = targets
    result.movingVolume = self.volumesLogic.CloneVolume(slicer.mrmlScene, sourceVolume, 'movingVolume-PREOP-INTRAOP')

    self.createVolumeAndTransformNodes(['rigid', 'affine', 'bSpline'], str(result.seriesNumber))

    self.doRigidRegistration(movingBinaryVolume=self.currentResult.movingLabel, initializeTransformMode="useCenterOfROIAlign")
    self.doAffineRegistration()
    self.doBSplineRegistration(initialTransform=self.currentResult.affineTransform, useScaleVersor3D=False,
                               useScaleSkewVersor3D=True,
                               movingBinaryVolume=self.currentResult.movingLabel, useAffine=False, samplingPercentage="0.002",
                               maskInferiorCutOffFromCenter="1000", numberOfHistogramBins="50",
                               numberOfMatchPoints="10", metricSamplingStrategy="Random", costMetric="MMI")
    self.transformTargets(['rigid', 'affine', 'bSpline'], result.originalTargets, str(result.seriesNumber))
    result.movingVolume = sourceVolume

  def applyReRegistration(self, progressCallback=None):

    self.progressCallback = progressCallback

    # moving volume: copy last fixed volume
    # TODO: think about retried segmentations
    coverProstateRegResult = self.registrationResults.getMostRecentAcceptedCoverProstateRegistration()

    # take the 'intraop label map', which is always fixed label in the very first preop-intraop registration
    lastRigidTfm = self.registrationResults.getLastRigidTransformation()

    name = self.generateNameForRegistrationResult(self.currentIntraopVolume)
    result = self.registrationResults.createResult(name)
    result.fixedVolume = self.currentIntraopVolume
    result.fixedLabel = self.volumesLogic.CreateAndAddLabelVolume(slicer.mrmlScene, self.currentIntraopVolume,
                                                                  self.currentIntraopVolume.GetName() + '-label')
    result.originalTargets = coverProstateRegResult.bSplineTargets
    sourceVolume = coverProstateRegResult.fixedVolume
    result.movingVolume = self.volumesLogic.CloneVolume(slicer.mrmlScene, sourceVolume, 'movingVolumeReReg')

    self.BRAINSResample(inputVolume=coverProstateRegResult.fixedLabel, referenceVolume=self.currentIntraopVolume,
                        outputVolume=result.fixedLabel, warpTransform=lastRigidTfm)

    self.createVolumeAndTransformNodes(['rigid', 'bSpline'], str(result.seriesNumber))

    self.doRigidRegistration(initialTransform=lastRigidTfm)
    self.dilateMask(result.fixedLabel)
    self.doBSplineRegistration(initialTransform=self.currentResult.rigidTransform, useScaleVersor3D=True,
                               useScaleSkewVersor3D=True, useAffine=True)

    self.transformTargets(['rigid', 'bSpline'], result.originalTargets, str(result.seriesNumber))
    result.movingVolume = sourceVolume

  def generateNameForRegistrationResult(self, intraopVolume):
    name = intraopVolume.GetName()
    nOccurences = sum([1 for result in self.registrationResults.getResultsAsList() if name in result.name])
    if nOccurences:
      name = name + "_Retry_" + str(nOccurences)
    return name

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

  def createLoadableFileListFromSelection(self, selectedSeriesList):

    if os.path.exists(self._intraopDataDir):
      self.loadableList = {}
      for series in selectedSeriesList:
        self.loadableList[series] = []

      for dcm in self.getFileList(self._intraopDataDir):
        currentFile = os.path.join(self._intraopDataDir, dcm)
        seriesNumberDescription = self.makeSeriesNumberDescription(currentFile)
        if seriesNumberDescription and seriesNumberDescription in selectedSeriesList:
          self.loadableList[seriesNumberDescription].append(currentFile)

  def loadSeriesIntoSlicer(self, selectedSeries):
    self.createLoadableFileListFromSelection(selectedSeries)
    self.currentIntraopVolume = None

    for series in [s for s in selectedSeries if s not in self.alreadyLoadedSeries.keys()]:
      files = self.loadableList[series]
      # create DICOMScalarVolumePlugin and load selectedSeries data from files into slicer
      scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()

      loadables = scalarVolumePlugin.examine([files])

      name = loadables[0].name
      self.currentIntraopVolume = scalarVolumePlugin.load(loadables[0])
      self.currentIntraopVolume.SetName(name)
      slicer.mrmlScene.AddNode(self.currentIntraopVolume)
      self.alreadyLoadedSeries[series] = self.currentIntraopVolume

  def waitingForSeriesToBeCompleted(self):

    logging.debug('**  new data in intraop directory detected **')
    logging.debug('waiting 5 more seconds for the series to be completed')

    qt.QTimer.singleShot(5000, self.importDICOMSeries)

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

    self.seriesList = sorted(self.seriesList, key=lambda series: int(series.split(": ")[0]))

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
    # TODO: set color is somehow not working here
    needleTipMarkupDisplayNode.SetColor(1, 1, 50)
    return needleTipMarkupNode

  def startNeedleTipPlacingMode(self):

    mlogic = slicer.modules.markups.logic()
    mlogic.SetActiveListID(self.needleTipMarkupNode)
    slicer.modules.markups.logic().StartPlaceMode(0)

  def measureDistance(self, target_position, needleTip_position):

    # calculate 2D distance
    distance_2D_x = abs(target_position[0] - needleTip_position[0])
    distance_2D_y = abs(target_position[1] - needleTip_position[1])
    distance_2D_z = abs(target_position[2] - needleTip_position[2])

    # calculate 3D distance
    distance_3D = self.get3dDistance(needleTip_position, target_position)

    return [distance_2D_x, distance_2D_y, distance_2D_z, distance_3D]

  def get3dDistance(self, needleTip_position, target_position):

    rulerNode = slicer.vtkMRMLAnnotationRulerNode()
    rulerNode.SetPosition1(target_position)
    rulerNode.SetPosition2(needleTip_position)
    distance_3D = rulerNode.GetDistanceMeasurement()
    return distance_3D

  def setupColorTable(self, colorFile):

    self.PCampReviewColorNode = slicer.vtkMRMLColorTableNode()
    colorNode = self.PCampReviewColorNode
    colorNode.SetName('PCampReview')
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
    clippingModelDisplayNode.SetColor((20, 180, 250))
    slicer.mrmlScene.AddNode(clippingModelDisplayNode)
    self.clippingModelNode.SetAndObserveDisplayNodeID(clippingModelDisplayNode.GetID())

  def labelMapFromClippingModel(self, inputVolume):
    """
    PARAMETER FOR MODELTOLABELMAP CLI MODULE:
    Parameter (0/0): sampleDistance
    Parameter (0/1): labelValue
    Parameter (1/0): InputVolume
    Parameter (1/1): surface
    Parameter (1/2): OutputVolume
    """
    outputLabelMap = slicer.vtkMRMLLabelMapVolumeNode()
    slicer.mrmlScene.AddNode(outputLabelMap)

    if outputLabelMap:
      'outoutLabelMap is here!'

    # define params
    params = {'sampleDistance': 0.1, 'labelValue': 5, 'InputVolume': inputVolume.GetID(),
              'surface': self.clippingModelNode.GetID(), 'OutputVolume': outputLabelMap.GetID()}

    logging.debug(params)
    # run ModelToLabelMap-CLI Module
    slicer.cli.run(slicer.modules.modeltolabelmap, None, params, wait_for_completion=True)

    # use label contours
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").SetUseLabelOutline(True)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").SetUseLabelOutline(True)

    # rotate volume to plane
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").RotateToVolumePlane(outputLabelMap)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").RotateToVolumePlane(outputLabelMap)

    # set Layout to redSliceViewOnly
    lm = slicer.app.layoutManager()
    lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    # fit Slice View to FOV
    red = lm.sliceWidget('Red')
    redLogic = red.sliceLogic()
    redLogic.FitSliceToAll()

    # set Label Opacity Back
    redWidget = lm.sliceWidget('Red')
    compositeNodeRed = redWidget.mrmlSliceCompositeNode()
    # compositeNodeRed.SetLabelVolumeID(outputLabelMap.GetID())
    compositeNodeRed.SetLabelOpacity(1)
    return outputLabelMap

  def BRAINSResample(self, inputVolume, referenceVolume, outputVolume, warpTransform):
    """
    Parameter (0/0): inputVolume
    Parameter (0/1): referenceVolume
    Parameter (1/0): outputVolume
    Parameter (1/1): pixelType
    Parameter (2/0): deformationVolume
    Parameter (2/1): warpTransform
    Parameter (2/2): interpolationMode
    Parameter (2/3): inverseTransform
    Parameter (2/4): defaultValue
    Parameter (3/0): gridSpacing
    Parameter (4/0): numberOfThreads
    """

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
    return self.getMostRecentAcceptedCoverProstateRegistration().originalTargets

  @property
  @onExceptReturnNone
  def intraopLabel(self):
    return self.getMostRecentAcceptedCoverProstateRegistration().fixedLabel

  @property
  @onExceptReturnNone
  def biasCorrectedResult(self):
    return self.getMostRecentAcceptedCoverProstateRegistration().movingVolume

  def __init__(self):
    self._registrationResults = OrderedDict()
    self._activeResult = None
    self.preopTargets = None

  def getResultsAsList(self):
    return self._registrationResults.values()

  def getMostRecentAcceptedCoverProstateRegistration(self):
    mostRecent = None
    for result in self._registrationResults.values():
      if "COVER PROSTATE" in result.name and result.accepted and not result.skipped:
        mostRecent = result
    return mostRecent

  def getLastRigidTransformation(self):
    nCoverProstateRegistrations = sum([1 for result in self._registrationResults.values() if "COVER PROSTATE" in result.name])
    if len(self._registrationResults) == 1 or len(self._registrationResults) == nCoverProstateRegistrations:
      logging.debug('Resampling label with same mask')
      # last registration was preop-intraop, take the same mask
      # this is an identity transform:
      lastRigidTfm = vtk.vtkGeneralTransform()
      lastRigidTfm.Identity()
    else:
      lastRigidTfm = self.getMostRecentResult().rigidTransform
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
    self.accepted = False
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

  def accept(self):
    self.accepted = True
    self.skipped = False
    self.rejected = False

  def skip(self):
    self.skipped = True
    self.accepted = False
    self.rejected = False

  def reject(self):
    self.rejected = True
    self.skipped = False
    self.accepted = False

  def printSummary(self):
    logging.debug('# ___________________________  registration output  ________________________________')
    logging.debug(self.__dict__)
    logging.debug('# __________________________________________________________________________________')

