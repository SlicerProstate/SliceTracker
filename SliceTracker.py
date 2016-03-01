import os
import csv
import numpy
import math, re, sys
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from SliceTrackerUtils.mixins import ModuleWidgetMixin, ModuleLogicMixin
from SliceTrackerUtils.helpers import SliceAnnotation, ExtendedQMessageBox
from Editor import EditorWidget
import EditorLib
import logging
import datetime
from subprocess import Popen
from SliceTrackerUtils.ZFrameRegistration import LineMarkerRegistration


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

  WHITE_BACKGROUND            = 'background-color: rgb(255,255,255)'
  LIGHT_GRAY_BACKGROUND       = 'background-color: rgb(230,230,230)'
  ORANGE_BACKGROUND           = 'background-color: rgb(255,102,0)'
  YELLOW_BACKGROUND           = 'background-color: yellow;'
  GREEN_BACKGROUND            = 'background-color: green;'
  GRAY_BACKGROUND             = 'background-color: gray;'
  RED_BACKGROUND              = 'background-color: red;'


class SliceTrackerConstants(object):

  LEFT_VIEWER_SLICE_ANNOTATION_TEXT = 'BIOPSY PLAN'
  RIGHT_VIEWER_SLICE_ANNOTATION_TEXT = 'TRACKED TARGETS'
  RIGHT_VIEWER_SLICE_TRANSFORMED_ANNOTATION_TEXT = 'OLD'
  RIGHT_VIEWER_SLICE_NEEDLE_IMAGE_ANNOTATION_TEXT = 'NEW'
  APPROVED_RESULT_TEXT_ANNOTATION = "approved"
  REJECTED_RESULT_TEXT_ANNOTATION = "rejected"
  SKIPPED_RESULT_TEXT_ANNOTATION = "skipped"

  LAYOUT_RED_SLICE_ONLY = slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView
  LAYOUT_FOUR_UP = slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView
  LAYOUT_SIDE_BY_SIDE = slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView
  ALLOWED_LAYOUTS = [LAYOUT_SIDE_BY_SIDE, LAYOUT_FOUR_UP]

  COVER_PROSTATE = "COVER PROSTATE"
  COVER_TEMPLATE = "COVER TEMPLATE"
  GUIDANCE_IMAGE = "GUIDANCE"


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


class SliceTrackerWidget(ScriptedLoadableModuleWidget, ModuleWidgetMixin, SliceTrackerConstants):

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
    return self._preopDataDir

  @preopDataDir.setter
  def preopDataDir(self, path):
    slicer.mrmlScene.Clear(0)
    self.logic.resetAndInitializeData()
    self.updateViewSettingButtons()
    self.removeSliceAnnotations()
    self._preopDataDir = path
    self.setSetting('PreopLocation', path)
    self.loadPreopData()
    self.intraopSeriesSelector.clear()
    self.intraopDirButton.setEnabled(True)
    self.trackTargetsButton.setEnabled(False)
    self.preopDirButton.text = self.truncatePath(path) if os.path.exists(path) else "Preop directory"
    self.preopDirButton.toolTip = path
    self.intraopDirButton.blockSignals(True)
    self.intraopDirButton.directory = self.getSetting('IntraopLocation')
    self.intraopDirButton.text = "Intraop directory"
    self.intraopDirButton.blockSignals(False)
    self.updateOutputFolder()
    self.targetTable.enabled = True

  @property
  def intraopDataDir(self):
    return self.logic.intraopDataDir

  @intraopDataDir.setter
  def intraopDataDir(self, path):
    self.collapsibleDirectoryConfigurationArea.collapsed = True
    self.logic.setReceivedNewImageDataCallback(self.onNewImageDataReceived)
    self.logic.intraopDataDir = path
    self.setSetting('IntraopLocation', path)
    self.intraopDirButton.text = self.truncatePath(path) if os.path.exists(path) else "Intraop directory"
    self.intraopDirButton.toolTip = path
    self.updateOutputFolder()

  @property
  def outputDir(self):
    return self.outputDirButton.directory

  @outputDir.setter
  def outputDir(self, path):
    exists = os.path.exists(path)
    self.caseCompletedButton.enabled = exists
    self.setSetting('OutputLocation', path if exists else None)
    self.outputDirButton.text = self.truncatePath(path) if exists else "Output directory"
    self.outputDirButton.toolTip = path
    self.updateOutputFolder()

  @property
  def evaluationMode(self):
    return self._evaluationMode

  @evaluationMode.setter
  def evaluationMode(self, value):
    self._evaluationMode = value
    if value is False:
      self.registrationAssessmentMode = False
      self.disableTargetMovingMode()
      self.targetTable.disconnect('doubleClicked(QModelIndex)', self.onMoveTargetRequest)
    else:
      self.targetTable.connect('doubleClicked(QModelIndex)', self.onMoveTargetRequest)

  def __init__(self, parent=None):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    self.logic = SliceTrackerLogic()
    self.markupsLogic = slicer.modules.markups.logic()
    self.volumesLogic = slicer.modules.volumes.logic()
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.moduleName))
    self.iconPath = os.path.join(self.modulePath, 'Resources/Icons')
    self.setupIcons()

  def onReload(self):
    try:
      self.logic.stopWatching()
      self.removeSliceAnnotations()
      self.clearTargetMovementObserverAndAnnotations()
      self.resetVisualEffects()
    except:
      pass
    ScriptedLoadableModuleWidget.onReload(self)

  def cleanup(self):
    ScriptedLoadableModuleWidget.cleanup(self)
    self.removeSliceAnnotations()
    self.clearTargetMovementObserverAndAnnotations()
    self.disconnectCrosshairNode()

  def updateOutputFolder(self):
    if os.path.exists(self.outputDirButton.directory) and self.patientIDLabel.text != '' \
            and self.intraopStudyDateLabel.text != '':
      time = qt.QTime().currentTime().toString().replace(":", "")
      date = str(qt.QDate().currentDate())
      finalDirectory = self.patientIDLabel.text + "-biopsy-" + date + "-" + time
      self.generatedOutputDirectory = os.path.join(self.outputDirButton.directory, finalDirectory, "MRgBiopsy")
      self.caseCompletedButton.enabled = True
      self.collapsibleDirectoryConfigurationArea.collapsed = True
    else:
      self.generatedOutputDirectory = ""
      self.caseCompletedButton.enabled = False

  def createPatientWatchBox(self):
    self.patientWatchBox, patientViewBoxLayout = self._createWatchBox(maximumHeight=100)

    self.patientIDLabel = qt.QLabel()
    self.patientNameLabel = qt.QLabel()
    self.patientDOBLabel = qt.QLabel()
    self.preopStudyDateLabel = qt.QLabel()
    self.intraopStudyDateLabel = qt.QLabel()

    patientViewBoxLayout.addWidget(self.createHLayout([qt.QLabel('Patient ID: '), self.patientIDLabel], margin=1))
    patientViewBoxLayout.addWidget(self.createHLayout([qt.QLabel('Patient Name: '), self.patientNameLabel], margin=1))
    patientViewBoxLayout.addWidget(self.createHLayout([qt.QLabel('Date of Birth: '), self.patientDOBLabel], margin=1))
    patientViewBoxLayout.addWidget(self.createHLayout([qt.QLabel('Preop Study Date: '), self.preopStudyDateLabel], margin=1))
    patientViewBoxLayout.addWidget(self.createHLayout([qt.QLabel('Intraop Study Date: '), self.intraopStudyDateLabel], margin=1))

  def createRegistrationWatchBox(self):
    self.registrationWatchBox, registrationWatchBoxLayout = self._createWatchBox(maximumHeight=40)
    self.currentRegisteredSeries = qt.QLabel('None')
    self.registrationDetailsButton = self.createButton("", icon=self.settingsIcon, styleSheet="border:none;",
                                                       maximumWidth=16)
    self.registrationDetailsButton.setCursor(qt.Qt.PointingHandCursor)
    registrationWatchBoxLayout.addWidget(self.createHLayout([qt.QLabel('Current Series:'), self.currentRegisteredSeries,
                                                             self.registrationDetailsButton], margin=1))
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
    self.settingsIcon = self.createIcon('icon-settings.png')
    self.undoIcon = self.createIcon('icon-undo.png')
    self.redoIcon = self.createIcon('icon-redo.png')
    self.fourUpIcon = self.createIcon('icon-four-up.png')
    self.sideBySideIcon = self.createIcon('icon-side-by-side.png')
    self.crosshairIcon = self.createIcon('icon-crosshair')
    self.zFrameIcon = self.createIcon('icon-zframe')
    self.needleIcon = self.createIcon('icon-needle')
    self.templateIcon = self.createIcon('icon-template')
    self.pathIcon = self.createIcon('icon-path')
    self.revealCursorIcon = self.createIcon('icon-revealCursor')
    self.skipIcon = self.createIcon('icon-skip')
    self.retryIcon = self.createIcon('icon-retry')
    self.approveIcon = self.createIcon('icon-approve')
    self.rejectIcon = self.createIcon('icon-reject')

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    try:
      import VolumeClipWithModel
    except ImportError:
      return self.warningDialog("Error: Could not find extension VolumeClip. Open Slicer Extension Manager and install "
                                "VolumeClip.", "Missing Extension")

    self.ratingWindow = RatingWindow(maximumValue=5)
    self.sliceAnnotations = []
    self.mouseReleaseEventObservers = {}
    self.targetMovementAnnotations = []
    self.revealCursor = None
    self.currentTargets = None
    self.moveTargetMode = False
    self.currentlyMovedTargetModelIndex = None

    self.crosshairNode = None
    self.crosshairNodeObserverTag = None

    self.logic.retryMode = False
    self.logic.zFrameRegistrationSuccessful = False

    self.lastSelectedModelIndex = None

    self.notifyUserAboutNewData = True

    self.createPatientWatchBox()
    self.createRegistrationWatchBox()
    self.setupRegistrationStepUIElements()
    self.settingsArea()

    self.setupSliceWidgets()
    self.setupZFrameRegistrationUIElements()
    self.setupTargetingStepUIElements()
    self.setupSegmentationUIElements()
    self.setupEvaluationStepUIElements()

    self.setupConnections()

    self.generatedOutputDirectory = ""
    self.outputDirButton.directory = self.getSetting('OutputLocation')

    self.layoutManager.setLayout(self.LAYOUT_RED_SLICE_ONLY)
    self.setAxialOrientation()

    self.showAcceptRegistrationWarning = False

    self.registrationAssessmentMode = False
    self.evaluationMode = False
    self.layout.addStretch()

  def settingsArea(self):
    self.collapsibleSettingsArea = ctk.ctkCollapsibleButton()
    self.collapsibleSettingsArea.text = "Settings"
    self.collapsibleSettingsArea.collapsed = True
    self.settingsAreaLayout = qt.QGridLayout(self.collapsibleSettingsArea)

    self.setupViewSettingGroupBox()
    self.setupZFrameViewSettingsGroupBox()

    self.settingsAreaLayout.addWidget(self.zFrameViewSettingsGroupBox)
    self.layout.addWidget(self.collapsibleSettingsArea)

  def setupViewSettingGroupBox(self):
    self.setupLayoutsButton()
    self.setupCrosshairButton()
    self.viewSettingsGroupBox = qt.QGroupBox('View options:')
    viewSettingsLayout = qt.QVBoxLayout()
    self.viewSettingsGroupBox.setLayout(viewSettingsLayout)

  def setupLayoutsButton(self):
    self.layoutsMenuButton = self.createButton("Layouts", minimumHeight=30)
    self.layoutsMenu = qt.QMenu()
    self.layoutDict = dict()
    self.layoutDict[self.LAYOUT_SIDE_BY_SIDE] = self.layoutsMenu.addAction(self.sideBySideIcon, "Side by side")
    self.layoutDict[self.LAYOUT_FOUR_UP] = self.layoutsMenu.addAction(self.fourUpIcon, "Four-Up")
    self.layoutsMenuButton.setMenu(self.layoutsMenu)

  def setupCrosshairButton(self):
    self.crosshairButton = self.createButton("", checkable=True, icon=self.crosshairIcon, toolTip="Show crosshair")
    self.crosshairNode = slicer.mrmlScene.GetNthNodeByClass(0, 'vtkMRMLCrosshairNode')

  def setupZFrameViewSettingsGroupBox(self):
    self.zFrameViewSettingsGroupBox = qt.QGroupBox('View options:')
    viewSettingsLayout = qt.QVBoxLayout()
    self.zFrameViewSettingsGroupBox.setLayout(viewSettingsLayout)
    self.showZFrameModelButton = self.createButton("", icon=self.zFrameIcon, checkable=True, toolTip="Display zFrame model")
    self.showTemplateButton = self.createButton("", icon=self.templateIcon, checkable=True, toolTip="Display template")
    self.showNeedlePathButton = self.createButton("", icon=self.needleIcon, checkable=True, toolTip="Display needle path")
    self.showTemplatePathButton = self.createButton("", icon=self.pathIcon, checkable=True, toolTip="Display template paths")

    self.updateViewSettingButtons()
    viewSettingsLayout.addWidget(self.createHLayout([self.layoutsMenuButton, self.showZFrameModelButton, self.showTemplatePathButton]))
    viewSettingsLayout.addWidget(self.createHLayout([self.crosshairButton, self.showTemplateButton, self.showNeedlePathButton]))

  def updateViewSettingButtons(self):
    self.showTemplateButton.enabled = self.logic.templateSuccessfulLoaded
    self.showTemplatePathButton.enabled = self.logic.templateSuccessfulLoaded
    self.showZFrameModelButton.enabled = self.logic.zFrameSuccessfulLoaded
    self.showTemplateButton.checked = False
    self.showTemplatePathButton.checked = False
    self.showZFrameModelButton.checked = False
    self.showNeedlePathButton.checked = False

  def setupSliceWidgets(self):
    self.setupSliceWidget("Red")
    self.setupSliceWidget("Yellow")
    self.setupSliceWidget("Green")
    self.layoutManager.setLayout(self.LAYOUT_RED_SLICE_ONLY)

  def setupSliceWidget(self, name):
    widget = self.layoutManager.sliceWidget(name)
    setattr(self, name.lower()+"Widget", widget)
    setattr(self, name.lower()+"CompositeNode", widget.mrmlSliceCompositeNode())
    setattr(self, name.lower()+"SliceView", widget.sliceView())
    logic = widget.sliceLogic()
    setattr(self, name.lower()+"SliceLogic", logic)
    setattr(self, name.lower()+"SliceNode", logic.GetSliceNode())
    setattr(self, name.lower()+"FOV", [])

  def setDefaultOrientation(self):
    self.redSliceNode.SetOrientationToAxial()
    self.yellowSliceNode.SetOrientationToSagittal()
    self.greenSliceNode.SetOrientationToCoronal()

  def setAxialOrientation(self):
    self.redSliceNode.SetOrientationToAxial()
    self.yellowSliceNode.SetOrientationToAxial()
    self.greenSliceNode.SetOrientationToAxial()

  def setupZFrameRegistrationUIElements(self):
    self.zFrameRegistrationGroupBox = qt.QGroupBox()
    self.zFrameRegistrationGroupBoxGroupBoxLayout = qt.QGridLayout()
    self.zFrameRegistrationGroupBox.setLayout(self.zFrameRegistrationGroupBoxGroupBoxLayout)
    self.zFrameRegistrationGroupBox.hide()

    self.approveZFrameRegistrationButton = self.createButton("Confirm registration accuracy")

    self.zFrameRegistrationGroupBoxGroupBoxLayout.addWidget(self.approveZFrameRegistrationButton)
    self.layout.addWidget(self.zFrameRegistrationGroupBox)

  def setupTargetingStepUIElements(self):
    self.targetingGroupBox = qt.QGroupBox()
    self.targetingGroupBoxLayout = qt.QGridLayout()
    self.targetingGroupBox.setLayout(self.targetingGroupBoxLayout)

    self.preopDirButton = self.createDirectoryButton(text="Preop directory", caption="Choose Preop Location",
                                                     directory=self.getSetting('PreopLocation'))
    self.outputDirButton = self.createDirectoryButton(caption="Choose Data Output Location")
    self.intraopDirButton = self.createDirectoryButton(text="Intraop directory", caption="Choose Intraop Location",
                                                       directory=self.getSetting('IntraopLocation'), enabled=False)

    self.trackTargetsButton = self.createButton("Track targets", toolTip="Track targets", enabled=False)
    self.skipIntraopSeriesButton = self.createButton("Skip", toolTip="Skip the currently selected series", enabled=False)
    self.caseCompletedButton = self.createButton('Case completed', enabled=False)
    self.setupTargetsTable()
    self.setupIntraopSeriesSelector()

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

    self.targetingGroupBoxLayout.addWidget(self.collapsibleDirectoryConfigurationArea, 0, 0, 1, 2)
    self.targetingGroupBoxLayout.addWidget(self.targetTable, 1, 0, 1, 2)
    self.targetingGroupBoxLayout.addWidget(self.intraopSeriesSelector, 2, 0)
    self.targetingGroupBoxLayout.addWidget(self.skipIntraopSeriesButton, 2, 1)
    self.targetingGroupBoxLayout.addWidget(self.trackTargetsButton, 3, 0, 1, 2)
    self.targetingGroupBoxLayout.addWidget(self.caseCompletedButton, 4, 0, 1, 2)
    self.layout.addWidget(self.targetingGroupBox)

  def createHelperLabel(self, toolTipText=""):
    helperPixmap = qt.QPixmap(os.path.join(self.iconPath, 'icon-infoBox.png'))
    helperPixmap = helperPixmap.scaled(qt.QSize(23, 20))
    label = self.createLabel("", pixmap=helperPixmap, toolTip=toolTipText)
    label.setCursor(qt.Qt.PointingHandCursor)
    return label

  def setupTargetsTable(self):
    self.targetTable = qt.QTableView()
    self.targetTableModel = CustomTargetTableModel(self.logic)
    self.targetTableModel.setTargetModifiedCallback(self.updateNeedleModel)
    self.targetTable.setModel(self.targetTableModel)
    self.targetTable.setSelectionBehavior(qt.QTableView.SelectRows)
    self.targetTable.horizontalHeader().setResizeMode(qt.QHeaderView.Stretch)
    self.targetTable.verticalHeader().hide()
    self.targetTable.maximumHeight = 150

  def setupIntraopSeriesSelector(self):
    self.intraopSeriesSelector = qt.QComboBox()
    self.seriesModel = qt.QStandardItemModel()
    self.intraopSeriesSelector.setModel(self.seriesModel)

  def setupSegmentationUIElements(self):
    iconSize = qt.QSize(24, 24)

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

    self.applyRegistrationButton = self.createButton("Apply Registration", icon=self.greenCheckIcon, iconSize=iconSize,
                                                     toolTip="Run Registration.")
    self.applyRegistrationButton.setFixedHeight(45)

    self.editorWidgetButton = self.createButton("", icon=self.settingsIcon, toolTip="Show Label Editor",
                                                enabled=False, iconSize=iconSize)

    segmentationButtons = self.createHLayout([self.quickSegmentationButton, self.applySegmentationButton,
                                              self.cancelSegmentationButton, self.backButton, self.forwardButton,
                                              self.editorWidgetButton])
    self.setupEditorWidget()

    self.segmentationGroupBox = qt.QGroupBox()
    self.segmentationGroupBoxLayout = qt.QFormLayout()
    self.segmentationGroupBox.setLayout(self.segmentationGroupBoxLayout)
    self.segmentationGroupBoxLayout.addWidget(segmentationButtons)
    self.segmentationGroupBoxLayout.addRow(self.editorWidgetParent)
    self.segmentationGroupBoxLayout.addRow(self.applyRegistrationButton)
    self.segmentationGroupBox.hide()
    self.editorWidgetParent.hide()

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
    self.layout.addWidget(self.registrationGroupBox)

  def setupEvaluationStepUIElements(self):
    self.registrationEvaluationGroupBox = qt.QGroupBox()
    self.registrationEvaluationGroupBoxLayout = qt.QGridLayout()
    self.registrationEvaluationGroupBox.setLayout(self.registrationEvaluationGroupBoxLayout)
    self.registrationEvaluationGroupBox.hide()

    self.setupCollapsibleRegistrationArea()
    self.setupRegistrationValidationButtons()
    self.registrationEvaluationGroupBoxLayout.addWidget(self.segmentationGroupBox, 2, 0)
    self.registrationEvaluationGroupBoxLayout.addWidget(self.collapsibleRegistrationArea, 3, 0)
    self.registrationEvaluationGroupBoxLayout.addWidget(self.evaluationButtonsGroupBox, 5, 0)
    self.layout.addWidget(self.registrationEvaluationGroupBox)

  def setupRegistrationValidationButtons(self):
    self.approveRegistrationResultButton = self.createButton("", toolTip="Approve", icon=self.approveIcon)
    self.retryRegistrationButton = self.createButton("", toolTip="Retry", icon=self.retryIcon)
    self.rejectRegistrationResultButton = self.createButton("", toolTip="Reject", icon=self.rejectIcon)
    self.evaluationButtonsGroupBox = self.createHLayout([self.retryRegistrationButton,
                                                         self.approveRegistrationResultButton, self.rejectRegistrationResultButton])
    self.evaluationButtonsGroupBox.enabled = False

  def setupCollapsibleRegistrationArea(self):
    self.collapsibleRegistrationArea = ctk.ctkCollapsibleButton()
    self.collapsibleRegistrationArea.text = "Registration Results"
    self.registrationGroupBoxDisplayLayout = qt.QFormLayout(self.collapsibleRegistrationArea)

    self.resultSelector = ctk.ctkComboBox()
    self.resultSelector.setFixedWidth(250)
    self.registrationResultAlternatives = self.createHLayout([qt.QLabel('Alternative Registration Result'), self.resultSelector])
    self.registrationGroupBoxDisplayLayout.addWidget(self.registrationResultAlternatives)

    self.showRigidResultButton = self.createButton('Rigid', checkable=True, name='rigid')
    self.showAffineResultButton = self.createButton('Affine', checkable=True, name='affine')
    self.showBSplineResultButton = self.createButton('BSpline', checkable=True, name='bSpline')

    self.registrationButtonGroup = qt.QButtonGroup()
    self.registrationButtonGroup.addButton(self.showRigidResultButton, 1)
    self.registrationButtonGroup.addButton(self.showAffineResultButton, 2)
    self.registrationButtonGroup.addButton(self.showBSplineResultButton, 3)

    self.registrationTypesGroupBox = qt.QGroupBox("Type")
    self.registrationTypesGroupBoxLayout = qt.QFormLayout(self.registrationTypesGroupBox)
    self.registrationTypesGroupBoxLayout.addWidget(self.createVLayout([self.showRigidResultButton,
                                                                       self.showAffineResultButton,
                                                                       self.showBSplineResultButton]))
    self.setupVisualEffectsUIElements()

    self.registrationGroupBoxDisplayLayout.addWidget(self.createHLayout([self.registrationTypesGroupBox,
                                                                         self.visualEffectsGroupBox]))

  def setupVisualEffectsUIElements(self):
    self.opacitySpinBox = qt.QDoubleSpinBox()
    self.opacitySpinBox.minimum = 0
    self.opacitySpinBox.maximum = 1.0
    self.opacitySpinBox.value = 0
    self.opacitySpinBox.singleStep = 0.05

    self.opacitySliderPopup = ctk.ctkPopupWidget(self.opacitySpinBox)
    popupLayout = qt.QHBoxLayout(self.opacitySliderPopup)
    self.opacitySlider = ctk.ctkDoubleSlider(self.opacitySliderPopup)
    self.opacitySlider.orientation = qt.Qt.Horizontal
    self.opacitySlider.minimum = 0
    self.opacitySlider.maximum = 1.0
    self.opacitySlider.value = 0
    self.opacitySlider.singleStep = 0.05

    popupLayout.addWidget(self.opacitySlider)
    self.opacitySliderPopup.verticalDirection = ctk.ctkBasePopupWidget.TopToBottom
    self.opacitySliderPopup.animationEffect = ctk.ctkBasePopupWidget.FadeEffect
    self.opacitySliderPopup.orientation = qt.Qt.Horizontal
    self.opacitySliderPopup.easingCurve = qt.QEasingCurve.OutQuart
    self.opacitySliderPopup.effectDuration = 100

    self.rockCount = 0
    self.rockTimer = qt.QTimer()
    self.rockTimer.setInterval(50)
    self.rockCheckBox = qt.QCheckBox("Rock")
    self.rockCheckBox.checked = False

    self.flickerTimer = qt.QTimer()
    self.flickerTimer.setInterval(400)
    self.flickerCheckBox = qt.QCheckBox("Flicker")
    self.flickerCheckBox.checked = False

    self.animaHolderLayout = self.createHLayout([self.rockCheckBox, self.flickerCheckBox])
    self.visualEffectsGroupBox = qt.QGroupBox("Visual Effects")
    self.visualEffectsGroupBoxLayout = qt.QFormLayout(self.visualEffectsGroupBox)
    self.useRevealCursorButton = self.createButton("", icon=self.revealCursorIcon, checkable=True,
                                                   enabled=False, toolTip="Use reveal cursor")
    slider = self.createHLayout([self.opacitySpinBox, self.animaHolderLayout])
    self.visualEffectsGroupBoxLayout.addWidget(self.createVLayout([slider, self.useRevealCursorButton]))

  def setupConnections(self):

    def setupButtonConnections():
      self.preopDirButton.directorySelected.connect(lambda: setattr(self, "preopDataDir", self.preopDirButton.directory))
      self.outputDirButton.directorySelected.connect(lambda: setattr(self, "outputDir", self.outputDirButton.directory))
      self.intraopDirButton.directorySelected.connect(lambda: setattr(self, "intraopDataDir", self.intraopDirButton.directory))
      self.forwardButton.clicked.connect(self.onForwardButtonClicked)
      self.backButton.clicked.connect(self.onBackButtonClicked)
      self.editorWidgetButton.clicked.connect(self.onEditorGearIconClicked)
      self.applyRegistrationButton.clicked.connect(lambda: self.onInvokeRegistration(initial=True))
      self.quickSegmentationButton.clicked.connect(self.onQuickSegmentationButtonClicked)
      self.cancelSegmentationButton.clicked.connect(self.onCancelSegmentationButtonClicked)
      self.trackTargetsButton.clicked.connect(self.onTrackTargetsButtonClicked)
      self.applySegmentationButton.clicked.connect(self.onApplySegmentationButtonClicked)
      self.approveRegistrationResultButton.clicked.connect(self.onApproveRegistrationResultButtonClicked)
      self.skipIntraopSeriesButton.clicked.connect(self.onSkipIntraopSeriesButtonClicked)
      self.rejectRegistrationResultButton.clicked.connect(self.onRejectRegistrationResultButtonClicked)
      self.retryRegistrationButton.clicked.connect(self.onRetryRegistrationButtonClicked)
      self.caseCompletedButton.clicked.connect(self.onSaveDataButtonClicked)
      self.registrationDetailsButton.clicked.connect(self.onShowRegistrationDetails)
      self.registrationButtonGroup.connect('buttonClicked(int)', self.onRegistrationButtonChecked)
      self.crosshairButton.clicked.connect(self.onCrosshairButtonClicked)
      self.approveZFrameRegistrationButton.clicked.connect(self.onApproveZFrameRegistrationButtonClicked)
      self.useRevealCursorButton.connect('toggled(bool)', self.onRevealToggled)
      self.showZFrameModelButton.connect('toggled(bool)', self.onShowZFrameModelToggled)
      self.showTemplateButton.connect('toggled(bool)', self.onShowZFrameTemplateToggled)
      self.showTemplatePathButton.connect('toggled(bool)', self.onShowTemplatePathToggled)
      self.showNeedlePathButton.connect('toggled(bool)', self.onShowNeedlePathToggled)

    def setupSelectorConnections():
      self.resultSelector.connect('currentIndexChanged(QString)', self.onRegistrationResultSelected)
      self.intraopSeriesSelector.connect('currentIndexChanged(QString)', self.onIntraopSeriesSelectionChanged)

    def setupCheckBoxConnections():
      self.rockCheckBox.connect('toggled(bool)', self.onRockToggled)
      self.flickerCheckBox.connect('toggled(bool)', self.onFlickerToggled)

    def setupOtherConnections():
      self.opacitySpinBox.valueChanged.connect(self.onOpacitySpinBoxChanged)
      self.opacitySlider.valueChanged.connect(self.onOpacitySliderChanged)
      self.rockTimer.connect('timeout()', self.onRockToggled)
      self.flickerTimer.connect('timeout()', self.onFlickerToggled)
      self.targetTable.connect('clicked(QModelIndex)', self.onTargetTableSelectionChanged)
      self.layoutsMenu.triggered.connect(self.onLayoutSelectionChanged)
      self.layoutManager.layoutChanged.connect(self.onLayoutChanged)

    setupCheckBoxConnections()
    setupButtonConnections()
    setupSelectorConnections()
    setupOtherConnections()

  def onShowZFrameModelToggled(self, checked):
    self.logic.setZFrameVisibility(checked)

  def onShowZFrameTemplateToggled(self, checked):
    self.logic.setTemplateVisibility(checked)

  def onShowTemplatePathToggled(self, checked):
    self.logic.setTemplatePathVisibility(checked)

  def onShowNeedlePathToggled(self, checked):
    self.logic.setNeedlePathVisibility(checked)

  def onShowRegistrationDetails(self):
    if self.registrationGroupBox.visible:
      self.registrationGroupBox.hide()
      self.registrationGroupBox.enabled = True
    else:
      self.registrationGroupBox.show()
      self.registrationGroupBox.enabled = False

  def onLayoutChanged(self):
    if self.layoutManager.layout in self.ALLOWED_LAYOUTS:
      self.layoutsMenu.setActiveAction(self.layoutDict[self.layoutManager.layout])
      self.onLayoutSelectionChanged(self.layoutDict[self.layoutManager.layout])
      if self.registrationAssessmentMode:
        self.disableTargetMovingMode()
        self.setupRegistrationResultView()
        self.onRegistrationResultSelected(self.currentResult.name)
    else:
      self.layoutsMenuButton.setIcon(qt.QIcon())
      self.layoutsMenuButton.setText("Layouts")

  def onLayoutSelectionChanged(self, action):
    self.layoutsMenuButton.setIcon(action.icon)
    self.layoutsMenuButton.setText(action.text)
    selectedLayout = self.getLayoutByAction(action)
    if self.layoutManager.layout != selectedLayout:
      self.layoutManager.setLayout(selectedLayout)

  def getLayoutByAction(self, searchedAction):
    for layout, action in self.layoutDict.iteritems():
      if action is searchedAction:
        return layout

  def onCrosshairButtonClicked(self):
    if self.crosshairButton.checked:
      self.crosshairNode.SetCrosshairMode(slicer.vtkMRMLCrosshairNode.ShowSmallBasic)
      self.crosshairNode.SetCrosshairMode(slicer.vtkMRMLCrosshairNode.ShowSmallBasic)
    else:
      self.crosshairNode.SetCrosshairMode(slicer.vtkMRMLCrosshairNode.NoCrosshair)

  def onRegistrationButtonChecked(self, buttonId):
    self.disableTargetMovingMode()
    self.hideAllTargets()
    if buttonId == 1:
      self.onRigidResultClicked()
    elif buttonId == 2:
      if not self.currentResult.affineTargets:
        return self.showBSplineResultButton.click()
      self.onAffineResultClicked()
    elif buttonId == 3:
      self.onBSplineResultClicked()

  def deactivateUndoRedoButtons(self):
    self.forwardButton.setEnabled(0)
    self.backButton.setEnabled(0)

  def updateUndoRedoButtons(self, observer=None, caller=None):
    self.forwardButton.setEnabled(self.deletedMarkups.GetNumberOfFiducials() > 0)
    self.backButton.setEnabled(self.logic.inputMarkupNode.GetNumberOfFiducials() > 0)

  def onIntraopSeriesSelectionChanged(self, selectedSeries=None):
    if self.evaluationMode:
      return
    self.removeSliceAnnotations()
    if selectedSeries:
      trackingPossible = self.isTrackingPossible(selectedSeries)
      self.trackTargetsButton.setEnabled(trackingPossible)
      self.showTemplatePathButton.checked = trackingPossible and self.COVER_PROSTATE in selectedSeries
      self.skipIntraopSeriesButton.setEnabled(trackingPossible)
      self.configureViewersForSelectedIntraopSeries(selectedSeries)
      self.updateIntraopSeriesSelectorColors(selectedSeries)
      self.updateSliceAnnotations(selectedSeries)

  def isTrackingPossible(self, series):
    return self.logic.isTrackingPossible(series) and \
          ((self.GUIDANCE_IMAGE in series and self.registrationResults.getMostRecentApprovedCoverProstateRegistration()) or
          (self.COVER_PROSTATE in series and self.logic.zFrameRegistrationSuccessful) or
          (self.COVER_TEMPLATE in series and not self.logic.zFrameRegistrationSuccessful))

  def updateIntraopSeriesSelectorColors(self, selectedSeries):
    style = STYLE.YELLOW_BACKGROUND
    if not self.isTrackingPossible(selectedSeries):
      if self.registrationResults.registrationResultWasApproved(selectedSeries) or \
              (self.logic.zFrameRegistrationSuccessful and self.COVER_TEMPLATE in selectedSeries):
        style = STYLE.GREEN_BACKGROUND
      elif self.registrationResults.registrationResultWasSkipped(selectedSeries):
        style = STYLE.RED_BACKGROUND
      elif self.registrationResults.registrationResultWasRejected(selectedSeries):
        style = STYLE.GRAY_BACKGROUND
    self.intraopSeriesSelector.setStyleSheet(style)

  def updateSliceAnnotations(self, selectedSeries):
    if not self.isTrackingPossible(selectedSeries):
      annotationText = None
      if self.registrationResults.registrationResultWasApproved(selectedSeries):
        annotationText = self.APPROVED_RESULT_TEXT_ANNOTATION
      elif self.registrationResults.registrationResultWasRejected(selectedSeries):
        annotationText = self.REJECTED_RESULT_TEXT_ANNOTATION
      if annotationText:
        self.sliceAnnotations.append(SliceAnnotation(self.yellowWidget, annotationText, fontSize=15, yPos=20))
      if self.registrationResults.registrationResultWasSkipped(selectedSeries):
        self.sliceAnnotations.append(SliceAnnotation(self.redWidget, self.SKIPPED_RESULT_TEXT_ANNOTATION,
                                                       fontSize=15, yPos=20))

  def configureViewersForSelectedIntraopSeries(self, selectedSeries):
    if self.registrationResults.registrationResultWasApproved(selectedSeries) or \
            self.registrationResults.registrationResultWasRejected(selectedSeries):
      self.setupSideBySideRegistrationView()
    else:
      try:
        result = self.registrationResults.getResultsBySeries(selectedSeries)[0]
      except IndexError:
        volume = self.logic.getOrCreateVolumeForSeries(selectedSeries)
        self.setupRedSlicePreview(volume)
        return
      self.setupRedSlicePreview(result.fixedVolume)

  def resetVisualEffects(self):
    self.flickerCheckBox.checked = False
    self.rockCheckBox.checked = False
    self.useRevealCursorButton.enabled = False
    self.useRevealCursorButton.checked = False

  def setupFourUpView(self, volume):
    self.disableTargetTable()
    self.setBackgroundToVolume(volume.GetID())
    self.layoutManager.setLayout(self.LAYOUT_FOUR_UP)
    slicer.app.applicationLogic().FitSliceToAll()

  def setupRedSlicePreview(self, volume):
    self.disableTargetTable()
    self.layoutManager.setLayout(self.LAYOUT_RED_SLICE_ONLY)
    self.setBackgroundToVolume(volume.GetID())
    slicer.app.applicationLogic().FitSliceToAll()

  def setupSideBySideRegistrationView(self):
    # TODO: shall we add a selector for viewing different registration results that has been rejected?
    self.targetTable.enabled = True
    for result in self.registrationResults.getResultsBySeries(self.intraopSeriesSelector.currentText):
      if result.approved or result.rejected:
        self.layoutManager.setLayout(self.LAYOUT_SIDE_BY_SIDE)
        self.setupRegistrationResultSideBySideView()
        if result.rejected:
          self.onRegistrationResultSelected(result.name, registrationType='bSpline')
        elif result.approved:
          self.onRegistrationResultSelected(result.name, registrationType=result.approvedRegistrationType)
        break

  def onTargetTableSelectionChanged(self, modelIndex=None):
    if not modelIndex:
      self.getAndSelectTargetFromTable()
      return
    if self.moveTargetMode is True and modelIndex != self.currentlyMovedTargetModelIndex:
      self.disableTargetMovingMode()
    self.lastSelectedModelIndex = modelIndex
    row = modelIndex.row()
    if not self.currentTargets:
      self.currentTargets = self.preopTargets
    self.jumpSliceNodesToNthTarget(row)
    self.updateNeedleModel()

  def jumpSliceNodesToNthTarget(self, targetIndex):
    currentTargetsSliceNodes = [self.yellowSliceNode]
    if self.layoutManager.layout == self.LAYOUT_SIDE_BY_SIDE:
      self.jumpSliceNodeToTarget(self.redSliceNode, self.preopTargets, targetIndex)
      self.setTargetSelected(self.preopTargets, selected=False)
      self.preopTargets.SetNthFiducialSelected(targetIndex, True)
    else:
      currentTargetsSliceNodes = [self.redSliceNode, self.yellowSliceNode, self.greenSliceNode]
    for sliceNode in currentTargetsSliceNodes:
      self.jumpSliceNodeToTarget(sliceNode, self.currentTargets, targetIndex)
    self.setTargetSelected(self.currentTargets, selected=False)
    self.currentTargets.SetNthFiducialSelected(targetIndex, True)

  def onMoveTargetRequest(self, modelIndex):
    if self.moveTargetMode:
      self.disableTargetMovingMode()
      if self.currentlyMovedTargetModelIndex != modelIndex:
        self.onMoveTargetRequest(modelIndex)
      self.currentlyMovedTargetModelIndex = None
    else:
      self.currentlyMovedTargetModelIndex = modelIndex
      self.enableTargetMovingMode()

  def enableTargetMovingMode(self):
    self.clearTargetMovementObserverAndAnnotations()
    targetName = self.targetTableModel.targetList.GetNthFiducialLabel(self.currentlyMovedTargetModelIndex.row())

    widgets = [self.yellowWidget] if self.layoutManager.layout == self.LAYOUT_SIDE_BY_SIDE else \
                 [self.redWidget, self.yellowWidget, self.greenWidget]
    for widget in widgets:
      sliceView = widget.sliceView()
      interactor = sliceView.interactorStyle().GetInteractor()
      observer = interactor.AddObserver(vtk.vtkCommand.LeftButtonReleaseEvent, self.onViewerClickEvent)
      sliceView.setCursor(qt.Qt.CrossCursor)
      annotation = SliceAnnotation(widget, "Target Movement Mode (%s)" % targetName, opacity=0.5,
                                   verticalAlign="top", horizontalAlign="center")
      self.mouseReleaseEventObservers[widget] = (observer, annotation)
    self.moveTargetMode = True

  def disableTargetMovingMode(self):
    self.clearTargetMovementObserverAndAnnotations()
    self.mouseReleaseEventObservers = {}
    self.moveTargetMode = False

  def clearTargetMovementObserverAndAnnotations(self):
    for widget, (observer, annotation) in self.mouseReleaseEventObservers.iteritems():
      sliceView = widget.sliceView()
      interactor = sliceView.interactorStyle().GetInteractor()
      interactor.RemoveObserver(observer)
      sliceView.setCursor(qt.Qt.ArrowCursor)
      annotation.remove()

  def onViewerClickEvent(self, observee=None, event=None):
    posXY = observee.GetEventPosition()
    widget = self.getWidgetForInteractor(observee)
    posRAS = self.xyToRAS(widget.sliceLogic(), posXY)
    if self.currentlyMovedTargetModelIndex is not None:
      self.currentResult.isGoingToBeMoved(self.targetTableModel.targetList, self.currentlyMovedTargetModelIndex.row())
      self.targetTableModel.targetList.SetNthFiducialPositionFromArray(self.currentlyMovedTargetModelIndex.row(), posRAS)
    self.disableTargetMovingMode()

  def getWidgetForInteractor(self, observee):
    for widget in self.mouseReleaseEventObservers.keys():
      sliceView = widget.sliceView()
      interactor = sliceView.interactorStyle().GetInteractor()
      if interactor is observee:
        return widget
    return None

  def xyToRAS(self, sliceLogic, xyPoint):
    sliceNode = sliceLogic.GetSliceNode()
    rast = sliceNode.GetXYToRAS().MultiplyPoint(xyPoint + (0,1,))
    return rast[:3]

  def updateNeedleModel(self):
    if self.showNeedlePathButton.checked and self.logic.zFrameRegistrationSuccessful:
      modelIndex = self.lastSelectedModelIndex
      try:
        start, end = self.targetTableModel.needleStartEndPositions[modelIndex.row()]
        self.logic.createNeedleModelNode(start, end)
      except KeyError:
        self.logic.removeNeedleModelNode()

  def getAndSelectTargetFromTable(self):
    modelIndex = None
    if self.lastSelectedModelIndex:
      modelIndex = self.lastSelectedModelIndex
    else:
      if self.targetTableModel.rowCount():
        modelIndex = self.targetTableModel.index(0,0)
    if modelIndex:
      self.targetTable.clicked(modelIndex)

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

  def removeSliceAnnotations(self):
    for annotation in self.sliceAnnotations:
      annotation.remove()
    self.sliceAnnotations = []

  def addSideBySideSliceAnnotations(self):
    self.removeSliceAnnotations()
    self.sliceAnnotations.append(SliceAnnotation(self.redWidget, self.LEFT_VIEWER_SLICE_ANNOTATION_TEXT, fontSize=30,
                                                 yPos=55))
    self.sliceAnnotations.append(SliceAnnotation(self.yellowWidget, self.RIGHT_VIEWER_SLICE_ANNOTATION_TEXT, yPos=55,
                                                 fontSize=30))
    self.registrationResultNewImageAnnotation = SliceAnnotation(self.yellowWidget,
                                                                self.RIGHT_VIEWER_SLICE_NEEDLE_IMAGE_ANNOTATION_TEXT, yPos=35,
                                                                opacity=0.0, color=(0,0.5,0))
    self.sliceAnnotations.append(self.registrationResultNewImageAnnotation)
    self.registrationResultOldImageAnnotation = SliceAnnotation(self.yellowWidget,
                                                                self.RIGHT_VIEWER_SLICE_TRANSFORMED_ANNOTATION_TEXT, yPos=35)
    self.sliceAnnotations.append(self.registrationResultOldImageAnnotation)
    self.registrationResultStatusAnnotation = None

  def addFourUpSliceAnnotations(self):
    self.removeSliceAnnotations()
    for widget in (self.redWidget, self.yellowWidget, self.greenWidget):
      self.sliceAnnotations.append(SliceAnnotation(widget, self.RIGHT_VIEWER_SLICE_ANNOTATION_TEXT, yPos=55, fontSize=30))
    self.registrationResultNewImageAnnotation = SliceAnnotation(self.redWidget,
                                                                self.RIGHT_VIEWER_SLICE_NEEDLE_IMAGE_ANNOTATION_TEXT, yPos=35,
                                                                opacity=0.0, color=(0,0.5,0))
    self.sliceAnnotations.append(self.registrationResultNewImageAnnotation)
    self.registrationResultOldImageAnnotation = SliceAnnotation(self.redWidget,
                                                                self.RIGHT_VIEWER_SLICE_TRANSFORMED_ANNOTATION_TEXT, yPos=35)
    self.sliceAnnotations.append(self.registrationResultOldImageAnnotation)
    self.registrationResultStatusAnnotation = None

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

  def onRevealToggled(self, checked):
    if self.revealCursor:
      self.revealCursor.tearDown()
    if checked:
      import CompareVolumes
      self.revealCursor = CompareVolumes.LayerReveal()

  def setOldNewIndicatorAnnotationOpacity(self, value):
    self.registrationResultNewImageAnnotation.opacity = value
    self.registrationResultOldImageAnnotation.opacity = 1.0 - value

  def showOpacitySliderPopup(self, show):
    if show:
      if not self.opacitySliderPopup.visible:
        self.opacitySpinBox.enabled = False
        self.opacitySlider.enabled = False
        self.opacitySliderPopup.show()
        self.opacitySliderPopup.autoHide = False
    else:
      self.opacitySpinBox.enabled = True
      self.opacitySlider.enabled = True
      self.opacitySliderPopup.hide()
      self.opacitySliderPopup. autoHide = True

  def onRockToggled(self):

    def startRocking():
      self.showOpacitySliderPopup(True)
      self.flickerCheckBox.enabled = False
      self.rockTimer.start()
      self.opacitySpinBox.value = 0.5 + math.sin(self.rockCount / 10.) / 2.
      self.rockCount += 1

    def stopRocking():
      self.showOpacitySliderPopup(False)
      self.flickerCheckBox.enabled  = True
      self.rockTimer.stop()

    if self.rockCheckBox.checked:
      startRocking()
    else:
      stopRocking()

  def onFlickerToggled(self):

    def startFlickering():
      self.showOpacitySliderPopup(True)
      self.rockCheckBox.setEnabled(False)
      self.flickerTimer.start()
      self.opacitySpinBox.value = 1.0 if self.opacitySpinBox.value == 0.0 else 0.0

    def stopFlickering():
      self.showOpacitySliderPopup(False)
      self.rockCheckBox.setEnabled(True)
      self.flickerTimer.stop()
      self.opacitySpinBox.value = 0.0

    if self.flickerCheckBox.checked:
      startFlickering()
    else:
      stopFlickering()

  def onSaveDataButtonClicked(self):
    self.save(showDialog=True)

  def save(self, showDialog=False):
    if not os.path.exists(self.outputDirButton.directory) or self.generatedOutputDirectory == "":
      self.notificationDialog("CRITICAL ERROR: You need to provide a valid output directory for saving data. Please make "
                              "sure to select one.")
    else:
      message = self.logic.save(self.generatedOutputDirectory)
      if showDialog:
        self.notificationDialog(message)

  def configureSegmentationMode(self):
    if self.COVER_PROSTATE in self.intraopSeriesSelector.currentText:
      self.showTemplatePathButton.checked = False
    self.referenceVolumeSelector.setCurrentNode(self.logic.currentIntraopVolume)
    self.intraopVolumeSelector.setCurrentNode(self.logic.currentIntraopVolume)
    self.applyRegistrationButton.setEnabled(False)
    self.quickSegmentationButton.setEnabled(self.referenceVolumeSelector.currentNode() is not None)
    self.setupFourUpView(self.logic.currentIntraopVolume)
    self.onQuickSegmentationButtonClicked()

  def inputsAreSet(self):
    return not (self.preopVolumeSelector.currentNode() is None and self.intraopVolumeSelector.currentNode() is None and
                self.preopLabelSelector.currentNode() is None and self.intraopLabelSelector.currentNode() is None and
                self.fiducialSelector.currentNode() is None)

  def updateCurrentPatientAndViewBox(self, currentFile):
    self.currentID = self.logic.getDICOMValue(currentFile, DICOMTAGS.PATIENT_ID)
    self.patientIDLabel.setText(self.currentID)

    def updatePreopStudyDate():
      studyDate = self.logic.extractDateFromDICOMFile(currentFile, DICOMTAGS.STUDY_DATE)
      self.preopStudyDateLabel.setText(studyDate)

    def updatePatientBirthDate():
      dateOfBirth = self.logic.extractDateFromDICOMFile(currentFile, DICOMTAGS.PATIENT_BIRTH_DATE)
      if dateOfBirth == '':
        self.patientDOBLabel.setText('No Date found')
      else:
        self.patientDOBLabel.setText(dateOfBirth)

    def updatePatientName():
      currentPatientName = ''
      currentPatientNameDICOM = self.logic.getDICOMValue(currentFile, DICOMTAGS.PATIENT_NAME)
      if currentPatientNameDICOM:
        splitted = currentPatientNameDICOM.split('^')
        try:
          currentPatientName = splitted[1] + ", " + splitted[0]
        except IndexError:
          currentPatientName = splitted[0]
      self.patientNameLabel.setText(currentPatientName)

    updatePatientBirthDate()
    self.intraopStudyDateLabel.setText("")
    updatePreopStudyDate()
    updatePatientName()

  def updateIntraopSeriesSelectorTable(self):
    self.intraopSeriesSelector.blockSignals(True)
    seriesList = self.logic.seriesList
    for series in seriesList:
      sItem = self.getOrCreateItem(series)
      color = COLOR.YELLOW
      if self.registrationResults.registrationResultWasApproved(series) or \
        (self.COVER_TEMPLATE in series and self.logic.zFrameRegistrationSuccessful):
        color = COLOR.GREEN
      elif self.registrationResults.registrationResultWasSkipped(series):
        color = COLOR.RED
      elif self.registrationResults.registrationResultWasRejected(series):
        color = COLOR.GRAY
      self.seriesModel.setData(sItem.index(), color, qt.Qt.BackgroundRole)
    self.intraopSeriesSelector.setCurrentIndex(-1)
    self.intraopSeriesSelector.blockSignals(False)
    self.selectMostRecentEligibleSeries()

  def getOrCreateItem(self, series):
    index = self.intraopSeriesSelector.findText(series)
    if index != -1:
      sItem = self.seriesModel.item(index)
    else:
      sItem = qt.QStandardItem(series)
      self.seriesModel.appendRow(sItem)
    return sItem

  def selectMostRecentEligibleSeries(self):
    if self.evaluationMode:
      self.intraopSeriesSelector.blockSignals(True)
    substring = self.GUIDANCE_IMAGE
    index = -1
    if not self.registrationResults.getMostRecentApprovedCoverProstateRegistration():
      substring = self.COVER_TEMPLATE if not self.logic.zFrameRegistrationSuccessful else self.COVER_PROSTATE
    for item in list(reversed(range(len(self.logic.seriesList)))):
      series = self.seriesModel.item(item).text()
      if substring in series:
        index = self.intraopSeriesSelector.findText(series)
        break
    if index != -1:
      self.intraopSeriesSelector.setCurrentIndex(index)
    self.intraopSeriesSelector.blockSignals(False)

  def onRegistrationResultSelected(self, seriesText, registrationType=None):
    self.disableTargetMovingMode()
    if not seriesText:
      return
    self.hideAllTargets()
    self.currentResult = seriesText
    self.showAffineResultButton.setEnabled(self.GUIDANCE_IMAGE not in seriesText)
    if registrationType:
      for button in self.registrationButtonGroup.buttons():
        if button.name == registrationType:
          button.click()
          break
    elif self.registrationButtonGroup.checkedId() != -1:
      self.onRegistrationButtonChecked(self.registrationButtonGroup.checkedId())
    else:
      self.showBSplineResultButton.click()

  def hideAllTargets(self):
    for result in self.registrationResults.getResultsAsList():
      for targetNode in [targets for targets in result.targets.values() if targets]:
        self.setTargetVisibility(targetNode, show=False)
    self.setTargetVisibility(self.preopTargets, show=False)

  def onRigidResultClicked(self):
    self.targetTableModel.targetList = self.currentResult.rigidTargets
    self.displayRegistrationResults(registrationType='rigid')

  def onAffineResultClicked(self):
    self.targetTableModel.targetList = self.currentResult.affineTargets
    self.displayRegistrationResults(registrationType='affine')

  def onBSplineResultClicked(self):
    self.targetTableModel.targetList = self.currentResult.bSplineTargets
    self.displayRegistrationResults(registrationType='bSpline')

  def displayRegistrationResults(self, registrationType):
    self.setCurrentRegistrationResultSliceViews(registrationType)
    self.showTargets(registrationType=registrationType)
    self.visualEffectsGroupBox.setEnabled(True)
    if self.lastSelectedModelIndex:
      self.targetTable.clicked(self.lastSelectedModelIndex)

  def setDefaultFOV(self, sliceLogic, volume, factor=0.5):
    sliceLogic.FitSliceToAll()
    FOV = sliceLogic.GetSliceNode().GetFieldOfView()
    self.setFOV(sliceLogic, [FOV[0] * factor, FOV[1] * factor, FOV[2]])
    sliceNode = sliceLogic.GetSliceNode()
    sliceNode.RotateToVolumePlane(volume)

  def setFOV(self, sliceLogic, FOV):
    sliceNode = sliceLogic.GetSliceNode()
    sliceNode.SetFieldOfView(FOV[0], FOV[1], FOV[2])
    sliceNode.UpdateMatrices()

  def setCurrentRegistrationResultSliceViews(self, registrationType):
    compositeNodes = [self.yellowCompositeNode]
    if self.layoutManager.layout == self.LAYOUT_SIDE_BY_SIDE:
      self.redCompositeNode.SetForegroundVolumeID(None)
      self.redCompositeNode.SetBackgroundVolumeID(self.preopVolume.GetID())
    else:
      compositeNodes = [self.redCompositeNode, self.yellowCompositeNode, self.greenCompositeNode]

    bgVolume = self.currentResult.getVolume(registrationType)
    bgVolume = bgVolume if self.logic.isVolumeExtentValid(bgVolume) else self.currentResult.fixedVolume

    for compositeNode in compositeNodes:
      compositeNode.SetForegroundVolumeID(self.currentResult.fixedVolume.GetID())
      compositeNode.SetBackgroundVolumeID(bgVolume.GetID())

    self.setDefaultFOV(self.redSliceLogic, self.preopVolume if self.layoutManager.layout == self.LAYOUT_SIDE_BY_SIDE
                                                            else bgVolume)
    self.setDefaultFOV(self.yellowSliceLogic, self.currentResult.getVolume(registrationType))
    self.setDefaultFOV(self.greenSliceLogic, self.currentResult.getVolume(registrationType))

  def showTargets(self, registrationType):
    self.setTargetVisibility(self.currentResult.rigidTargets, show=registrationType == 'rigid')
    self.setTargetVisibility(self.currentResult.bSplineTargets, show=registrationType == 'bSpline')
    if self.currentResult.affineTargets:
      self.setTargetVisibility(self.currentResult.affineTargets, show=registrationType == 'affine')
    self.currentTargets = getattr(self.currentResult, registrationType+'Targets')
    self.setTargetVisibility(self.preopTargets)

  def setTargetVisibility(self, targetNode, show=True):
    self.markupsLogic.SetAllMarkupsVisibility(targetNode, show)

  def setTargetSelected(self, targetNode, selected=False):
    self.markupsLogic.SetAllMarkupsSelected(targetNode, selected)

  def configureSliceNodesForPreopData(self):
    for nodeId in ["vtkMRMLSliceNodeRed", "vtkMRMLSliceNodeYellow", "vtkMRMLSliceNodeGreen"]:
      slicer.mrmlScene.GetNodeByID(nodeId).SetUseLabelOutline(True)
    self.redSliceNode.SetOrientationToAxial()

  def loadT2Label(self):
    mostRecentFilename = self.logic.getMostRecentWholeGlandSegmentation(self.preopSegmentationPath)
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
        self.markupsLogic.SetAllMarkupsLocked(self.preopTargets, True)
    return success

  def loadMpReviewProcessedData(self, preopDir):
    resourcesDir = os.path.join(preopDir, 'RESOURCES')
    self.preopTargetsPath = os.path.join(preopDir, 'Targets')

    if not os.path.exists(resourcesDir):
      self.confirmDialog("The selected directory does not fit the mpReview directory structure. Make sure that you "
                         "select the study root directory which includes directories RESOURCES")
      return False

    seriesMap = {}

    patientInformationRetrieved = False

    for root, subdirs, files in os.walk(resourcesDir):
      logging.debug('Root: ' + root + ', files: ' + str(files))
      resourceType = os.path.split(root)[1]

      logging.debug('Resource: ' + resourceType)

      if resourceType == 'Reconstructions':
        for f in [f for f in files if f.endswith('.xml')]:
          logging.debug('File: ' + f)
          metaFile = os.path.join(root, f)
          logging.debug('Ends with xml: ' + metaFile)
          try:
            (seriesNumber, seriesName) = self.logic.getSeriesInfoFromXML(metaFile)
            logging.debug(str(seriesNumber) + ' ' + seriesName)
          except:
            logging.debug('Failed to get from XML')
            continue

          volumePath = os.path.join(root, seriesNumber + '.nrrd')
          seriesMap[seriesNumber] = {'MetaInfo': None, 'NRRDLocation': volumePath, 'LongName': seriesName}
          seriesMap[seriesNumber]['ShortName'] = str(seriesNumber) + ":" + seriesName
      elif resourceType == 'DICOM' and not patientInformationRetrieved:
        self.logic.importStudy(root)
        for f in files:
          self.updateCurrentPatientAndViewBox(os.path.join(root, f))
          patientInformationRetrieved = True
          break

    logging.debug('All series found: ' + str(seriesMap.keys()))
    logging.debug('All series found: ' + str(seriesMap.values()))

    logging.debug('******************************************************************************')

    self.preopImagePath = None
    self.preopSegmentationPath = None

    for series in seriesMap:
      seriesName = str(seriesMap[series]['LongName'])
      logging.debug('series Number ' + series + ' ' + seriesName)
      if re.search("ax", str(seriesName), re.IGNORECASE) and re.search("t2", str(seriesName), re.IGNORECASE):
        logging.debug(' FOUND THE SERIES OF INTEREST, ITS ' + seriesName)
        logging.debug(' LOCATION OF VOLUME : ' + str(seriesMap[series]['NRRDLocation']))

        path = os.path.join(seriesMap[series]['NRRDLocation'])
        logging.debug(' LOCATION OF IMAGE path : ' + str(path))

        segmentationPath = os.path.dirname(os.path.dirname(path))
        segmentationPath = os.path.join(segmentationPath, 'Segmentations')
        logging.debug(' LOCATION OF SEGMENTATION path : ' + segmentationPath)

        if not self.preopSegmentationPath and os.path.exists(segmentationPath) and os.listdir(segmentationPath):
          self.preopImagePath = seriesMap[series]['NRRDLocation']
          self.preopSegmentationPath = segmentationPath

    if self.preopSegmentationPath is None:
      self.confirmDialog("No segmentations found.\nMake sure that you used mpReview for segmenting the prostate "
                         "first and using its output as the preop data input here.")
      return False
    return True

  def loadPreopData(self):
    # TODO: using decorators
    if not self.loadMpReviewProcessedData(self.preopDataDir):
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
    self.targetTableModel.targetList = self.preopTargets

    self.fiducialSelector.setCurrentNode(self.preopTargets)
    self.markupsLogic.JumpSlicesToNthPointInMarkup(self.preopTargets.GetID(), 0)

    self.logic.styleDisplayNode(self.preopTargets.GetDisplayNode())
    self.redCompositeNode.SetLabelOpacity(1)

    self.layoutManager.setLayout(self.LAYOUT_RED_SLICE_ONLY)

    self.setDefaultFOV(self.redSliceLogic, self.preopVolume)

  def checkForPatientIdSimilarityAndGetSeriesNumbers(self, fileList):
    newSeries = {}
    for currentFile in fileList:
      currentFile = os.path.join(self.intraopDataDir, currentFile)
      seriesNumber = int(self.logic.getDICOMValue(currentFile, DICOMTAGS.SERIES_NUMBER))
      if seriesNumber not in newSeries.keys():
        patientID = self.logic.getDICOMValue(currentFile, DICOMTAGS.PATIENT_ID)
        studyDate = self.logic.extractDateFromDICOMFile(currentFile, DICOMTAGS.STUDY_DATE)
        newSeries[seriesNumber] = [patientID, studyDate]

    acceptedSeriesNumbers = []
    for seriesNumber, values in newSeries.iteritems():
      patientID, studyDate = values
      if patientID is not None and patientID != self.currentID:
        if not self.yesNoDialog(message='WARNING: Preop data of Patient ID ' + self.currentID + ' was selected, but '
                                        ' data of patient with ID ' + patientID + ' just arrived in the folder, which '
                                        'you selected for incoming data.\nDo you want to keep this series?',
                                title="PatientsID Not Matching"):
          self.logic.deleteSeriesFromSeriesList(seriesNumber)
          continue
      if self.intraopStudyDateLabel.text == '':
        self.intraopStudyDateLabel.setText(studyDate)
      acceptedSeriesNumbers.append(seriesNumber)
    acceptedSeriesNumbers.sort()
    return acceptedSeriesNumbers

  def onCancelSegmentationButtonClicked(self):
    if self.yesNoDialog("Do you really want to cancel the segmentation process?"):
      self.setQuickSegmentationModeOFF()

  def onQuickSegmentationButtonClicked(self):
    self.hideAllLabels()
    self.setBackgroundToVolume(self.referenceVolumeSelector.currentNode().GetID())
    self.setQuickSegmentationModeON()

  def setBackgroundToVolume(self, volumeID):
    for compositeNode in [self.redCompositeNode, self.yellowCompositeNode, self.greenCompositeNode]:
      compositeNode.Reset(None)
      compositeNode.SetBackgroundVolumeID(volumeID)
    self.setDefaultOrientation()
    slicer.app.applicationLogic().FitSliceToAll()

  def hideAllLabels(self):
    for compositeNode in [self.redCompositeNode, self.yellowCompositeNode, self.greenCompositeNode]:
      compositeNode.SetLabelVolumeID(None)

  def setQuickSegmentationModeON(self):
    self.logic.deleteClippingData()
    self.setSegmentationButtons(segmentationActive=True)
    self.deactivateUndoRedoButtons()
    self.disableEditorWidgetAndResetEditorTool()
    self.setupQuickModeHistory()
    self.layoutManager.setLayout(self.LAYOUT_FOUR_UP)
    self.logic.runQuickSegmentationMode()
    # TODO: remove Observer after segmentation finised
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
      self.deletedMarkups.Reset(None)
    except AttributeError:
      self.deletedMarkups = slicer.vtkMRMLMarkupsFiducialNode()
      self.deletedMarkups.SetName('deletedMarkups')

  def resetToRegularViewMode(self):
    interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
    interactionNode.SwitchToViewTransformMode()
    interactionNode.SetPlaceModePersistence(0)

  def onOpacitySpinBoxChanged(self, value):
    if self.opacitySlider.value != value:
      self.opacitySlider.value = value
    self.onOpacityChanged(value)

  def onOpacitySliderChanged(self, value):
    if self.opacitySpinBox.value != value:
      self.opacitySpinBox.value = value

  def onOpacityChanged(self, value):
    if self.layoutManager.layout == self.LAYOUT_FOUR_UP:
      self.redCompositeNode.SetForegroundOpacity(value)
      self.greenCompositeNode.SetForegroundOpacity(value)
    self.yellowCompositeNode.SetForegroundOpacity(value)
    self.setOldNewIndicatorAnnotationOpacity(value)

  def activateEvaluationStep(self):
    self.evaluationMode = True
    self.currentRegisteredSeries.setText(self.logic.currentIntraopVolume.GetName())
    self.targetingGroupBox.hide()
    self.registrationEvaluationGroupBoxLayout.addWidget(self.targetTable, 4, 0)
    self.registrationEvaluationGroupBox.show()
    self.useRevealCursorButton.enabled = True

  def connectCrosshairNode(self):
    if not self.crosshairNodeObserverTag:
      self.crosshairNodeObserverTag = self.crosshairNode.AddObserver(slicer.vtkMRMLCrosshairNode.CursorPositionModifiedEvent,
                                                                     self.calcCursorTargetsDistance)

  def disconnectCrosshairNode(self):
    if self.crosshairNode and self.crosshairNodeObserverTag:
      self.crosshairNode.RemoveObserver(self.crosshairNodeObserverTag)
    self.crosshairNodeObserverTag = None

  def calcCursorTargetsDistance(self, observee, event):
    ras = [0.0,0.0,0.0]
    xyz = [0.0,0.0,0.0]
    insideView = self.crosshairNode.GetCursorPositionRAS(ras)
    sliceNode = self.crosshairNode.GetCursorPositionXYZ(xyz)

    if not insideView or sliceNode not in [self.redSliceNode, self.yellowSliceNode, self.greenSliceNode]:
      self.targetTableModel.cursorPosition = None
      return

    if (self.registrationAssessmentMode and (self.layoutManager.layout == self.LAYOUT_FOUR_UP or
       (self.layoutManager.layout == self.LAYOUT_SIDE_BY_SIDE and sliceNode is self.yellowSliceNode))) or \
      (not self.registrationAssessmentMode and sliceNode is self.yellowSliceNode):
      self.targetTableModel.cursorPosition = ras

  def openTargetingStep(self, ratingResult=None):
    self.zFrameRegistrationGroupBox.hide()
    self.logic.removeNeedleModelNode()
    self.targetTableModel.computeCursorDistances = False
    self.evaluationMode = False
    self.save()
    self.disconnectCrosshairNode()
    self.hideAllLabels()
    if ratingResult:
      self.currentResult.score = ratingResult
    self.registrationWatchBox.hide()
    self.updateIntraopSeriesSelectorTable()
    self.registrationEvaluationGroupBox.hide()
    self.targetingGroupBoxLayout.addWidget(self.targetTable, 1, 0, 1, 2)
    self.targetingGroupBox.show()
    self.removeSliceAnnotations()
    self.resetVisualEffects()

  def onRetryRegistrationButtonClicked(self):
    self.registrationAssessmentMode = False
    self.logic.retryMode = True
    self.evaluationButtonsGroupBox.enabled = False
    self.onTrackTargetsButtonClicked()

  def onApproveRegistrationResultButtonClicked(self):
    self.currentResult.approve(registrationType=self.registrationButtonGroup.checkedButton().name)

    if self.ratingWindow.isRatingEnabled():
      self.ratingWindow.show(disableWidget=self.parent, callback=self.openTargetingStep)
    else:
      self.openTargetingStep()

  def onRejectRegistrationResultButtonClicked(self):
    results = self.registrationResults.getResultsBySeriesNumber(self.currentResult.seriesNumber)
    for result in results:
      result.reject()
    self.openTargetingStep()

  def onSkipIntraopSeriesButtonClicked(self):
    self.skipSeries(self.intraopSeriesSelector.currentText)
    self.openTargetingStep()

  def skipAllUnregisteredPreviousSeries(self, selectedSeries):
    selectedSeriesNumber = RegistrationResult.getSeriesNumberFromString(selectedSeries)
    for series in self.logic.seriesList:
      currentSeriesNumber = RegistrationResult.getSeriesNumberFromString(series)
      if currentSeriesNumber < selectedSeriesNumber:
        results = self.registrationResults.getResultsBySeriesNumber(currentSeriesNumber)
        if len(results) == 0:
          self.skipSeries(series)
      else:
        break

  def skipSeries(self, seriesText):
    volume = self.logic.getOrCreateVolumeForSeries(seriesText)
    name, suffix = self.logic.getRegistrationResultNameAndGeneratedSuffix(volume.GetName())
    result = self.registrationResults.createResult(name+suffix)
    result.fixedVolume = volume
    result.skip()

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
    self.layoutManager.setLayout(self.LAYOUT_SIDE_BY_SIDE)

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
    self.setDefaultFOV(logic, volume)

  def onTrackTargetsButtonClicked(self):
    self.disableTargetMovingMode()
    self.removeSliceAnnotations()
    self.targetTableModel.computeCursorDistances = False
    if not self.logic.zFrameRegistrationSuccessful and self.COVER_TEMPLATE in self.intraopSeriesSelector.currentText:
      self.openZFrameRegistrationStep()
      return
    else:
      if self.currentResult is None or \
         self.registrationResults.getMostRecentApprovedCoverProstateRegistration() is None or \
         self.logic.retryMode or self.COVER_PROSTATE in self.intraopSeriesSelector.currentText:
        self.initiateOrRetryTracking()
      else:
        self.repeatRegistrationForCurrentSelection()
      self.activateEvaluationStep()

  def openZFrameRegistrationStep(self):
    volume = self.logic.getOrCreateVolumeForSeries(self.intraopSeriesSelector.currentText)
    if volume:
      self.evaluationMode = True
      self.targetingGroupBox.hide()
      self.zFrameRegistrationGroupBox.show()
      progress = self.makeProgressIndicator(2, 1)
      progress.labelText = '\nZFrame registration'
      self.logic.runZFrameRegistration(volume)
      progress.setValue(2)
      progress.close()
      self.setupFourUpView(volume)
      self.redSliceNode.SetSliceVisible(True)
      self.showZFrameModelButton.checked = True
      self.showTemplateButton.checked = True
      self.showTemplatePathButton.checked = True

  def onApproveZFrameRegistrationButtonClicked(self):
    self.logic.zFrameRegistrationSuccessful = True
    self.redSliceNode.SetSliceVisible(False)
    self.showZFrameModelButton.checked = False
    self.showTemplateButton.checked = False
    self.showTemplatePathButton.checked = False
    self.openTargetingStep()
    self.save()

  def initiateOrRetryTracking(self):
    volume = self.logic.getOrCreateVolumeForSeries(self.intraopSeriesSelector.currentText)
    if volume:
      self.logic.currentIntraopVolume = volume
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
    selectedSeries = self.intraopSeriesSelector.currentText
    self.skipAllUnregisteredPreviousSeries(selectedSeries)
    volume = self.logic.getOrCreateVolumeForSeries(selectedSeries)
    if volume:
      self.logic.currentIntraopVolume = volume
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

  def finalizeRegistrationStep(self):
    self.targetTableModel.computeCursorDistances = True
    self.targetTable.enabled = True
    self.addNewTargetsToScene()
    self.openRegistrationResultAssessmentStep()
    self.showBSplineResultButton.click()
    self.currentResult.printSummary()
    self.connectCrosshairNode()
    if not self.logic.isVolumeExtentValid(self.currentResult.bSplineVolume):
      self.notificationDialog("One or more empty volume were created during registration process. You have three options:\n"
                              "1. Skip the registration result \n"
                              "2. Retry with creating a new segmentation \n"
                              "3. Set targets to your preferred position (in Four-Up layout)",
                              title="Action needed: Registration created empty volume(s)")

  def addNewTargetsToScene(self):
    for targetNode in [targets for targets in self.currentResult.targets.values() if targets]:
      slicer.mrmlScene.AddNode(targetNode)

  def setupRegistrationResultView(self):
    if self.layoutManager.layout == self.LAYOUT_FOUR_UP:
      self.setupRegistrationResultFourUpView()
    else:
      self.setupRegistrationResultSideBySideView()

  def setupRegistrationResultSideBySideView(self):
    self.hideAllLabels()
    self.addSideBySideSliceAnnotations()

    self.refreshViewNodeIDs(self.preopTargets, [self.redSliceNode])
    for targetNode in [targets for targets in self.currentResult.targets.values() if targets]:
      self.refreshViewNodeIDs(targetNode, [self.yellowSliceNode])
    self.setAxialOrientation()

  def setupRegistrationResultFourUpView(self):
    self.hideAllLabels()
    self.addFourUpSliceAnnotations()

    for targetNode in [targets for targets in self.currentResult.targets.values() if targets]:
      self.refreshViewNodeIDs(targetNode, [self.redSliceNode, self.yellowSliceNode, self.greenSliceNode])
    self.setDefaultOrientation()

  def openRegistrationResultAssessmentStep(self):
    self.registrationAssessmentMode = True
    self.updateRegistrationResultSelector()
    self.layoutManager.setLayout(self.LAYOUT_SIDE_BY_SIDE)
    self.setupRegistrationResultView()
    self.registrationWatchBox.show()
    self.segmentationGroupBox.hide()
    self.activateRegistrationResultsArea(collapsed=False, enabled=True)
    self.evaluationButtonsGroupBox.enabled = True

  def refreshViewNodeIDs(self, targets, sliceNodes):
    displayNode = targets.GetDisplayNode()
    if displayNode:
      displayNode.RemoveAllViewNodeIDs()
      for sliceNode in sliceNodes:
        displayNode.AddViewNodeID(sliceNode.GetID())

  def onNewImageDataReceived(self, **kwargs):
    newFileList = kwargs.pop('newList')
    newSeriesNumbers = self.checkForPatientIdSimilarityAndGetSeriesNumbers(newFileList)
    self.updateIntraopSeriesSelectorTable()
    selectedSeries = self.intraopSeriesSelector.currentText
    if selectedSeries != "":
      selectedSeriesNumber = RegistrationResult.getSeriesNumberFromString(selectedSeries)
      if not self.logic.zFrameRegistrationSuccessful and self.COVER_TEMPLATE in selectedSeries and \
                      selectedSeriesNumber in newSeriesNumbers:
        self.onTrackTargetsButtonClicked()
        return

      if not self.evaluationMode and \
              self.notifyUserAboutNewData and any(seriesText in self.intraopSeriesSelector.currentText for seriesText
                                                  in [self.COVER_TEMPLATE, self.COVER_PROSTATE, self.GUIDANCE_IMAGE]):
        dialog = IncomingDataMessageBox()
        answer, checked = dialog.exec_()
        self.notifyUserAboutNewData = not checked
        if answer == qt.QMessageBox.AcceptRole:
          self.onTrackTargetsButtonClicked()


class SliceTrackerLogic(ScriptedLoadableModuleLogic, ModuleLogicMixin):

  ZFRAME_MODEL_PATH = 'Resources/zframe/zframe-model.vtk'
  ZFRAME_TEMPLATE_CONFIG_FILE_NAME = 'Resources/zframe/ProstateTemplate.csv'
  ZFRAME_MODEL_NAME = 'ZFrameModel'
  ZFRAME_TEMPLATE_NAME = 'NeedleGuideTemplate'
  ZFRAME_TEMPLATE_PATH_NAME = 'NeedleGuideNeedlePath'
  COMPUTED_NEEDLE_MODEL_NAME = 'ComputedNeedleModel'
  MPREVIEW_COLORS_FILE_NAME = 'Resources/Colors/mpReviewColors.csv'

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
  def currentResult(self):
      return self.registrationResults.activeResult

  @currentResult.setter
  def currentResult(self, series):
    self.registrationResults.activeResult = series

  @property
  def templateSuccessfulLoaded(self):
    return self.tempModelNode and self.pathModelNode

  @property
  def zFrameSuccessfulLoaded(self):
    return self.zFrameModelNode

  def __init__(self, parent=None):
    ScriptedLoadableModuleLogic.__init__(self, parent)
    self.modulePath = os.path.dirname(slicer.util.modulePath(self.moduleName))
    self.markupsLogic = slicer.modules.markups.logic()
    self.volumesLogic = slicer.modules.volumes.logic()
    self.scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()
    self.defaultTemplateFile = os.path.join(self.modulePath, self.ZFRAME_TEMPLATE_CONFIG_FILE_NAME)
    self.defaultColorFile = os.path.join(self.modulePath, self.MPREVIEW_COLORS_FILE_NAME)
    self.configureTimers()
    self.resetAndInitializeData()

  def resetAndInitializeData(self):

    self.stopWatching()

    self.currentFileCount = 0

    self.inputMarkupNode = None
    self.clippingModelNode = None
    self.seriesList = []
    self.loadableList = {}
    self.alreadyLoadedSeries = {}
    self.storeSCPProcess = None

    self.currentIntraopVolume = None
    self.registrationResults = RegistrationResults()

    self._intraopDataDir = ""

    self._incomingDataCallback = None

    self.biasCorrectionDone = False

    self.retryMode = False
    self.zFrameRegistrationSuccessful = False
    self.zFrameModelNode = None
    self.zFrameTransform = None

    self.showTemplatePath = False
    self.showNeedlePath = False

    self.needleModelNode = None
    self.tempModelNode = None
    self.pathModelNode = None
    self.templateConfig = []
    self.templateMaxDepth = []
    self.pathOrigins = []  ## Origins of needle paths (after transformation by parent transform node)
    self.pathVectors = []  ## Normal vectors of needle paths (after transformation by parent transform node)

    self.loadColorTable()
    self.clearOldNodes()
    self.loadZFrameModel()
    self.loadTemplateConfigFile()

  def configureTimers(self):
    self.importTimer = qt.QTimer()
    self.importTimer.setInterval(5000)
    self.importTimer.timeout.connect(self.importDICOMSeries)
    self.importTimer.setSingleShot(True)

    self.watchTimer = qt.QTimer()
    self.watchTimer.setInterval(500)
    self.watchTimer.timeout.connect(self.startWatchingIntraop)
    self.watchTimer.setSingleShot(True)

  def clearOldNodes(self):
    self.clearOldNodesByName(self.ZFRAME_TEMPLATE_NAME)
    self.clearOldNodesByName(self.ZFRAME_TEMPLATE_PATH_NAME)
    self.clearOldNodesByName(self.ZFRAME_MODEL_NAME)
    self.clearOldNodesByName(self.COMPUTED_NEEDLE_MODEL_NAME)

  def isTrackingPossible(self, series):
    return not (self.registrationResults.registrationResultWasApproved(series) or
                self.registrationResults.registrationResultWasSkipped(series) or
                self.registrationResults.registrationResultWasRejected(series))

  def setReceivedNewImageDataCallback(self, func):
    assert hasattr(func, '__call__')
    self._incomingDataCallback = func

  def save(self, outputDir):
    self.createDirectory(outputDir)

    successfullySavedData = ["The following data was successfully saved:\n"]
    failedSaveOfData = ["The following data failed to saved:\n"]

    def saveIntraopSegmentation():
      intraopLabel = self.registrationResults.intraopLabel
      if intraopLabel:
        intraopLabelName = intraopLabel.GetName().replace("label", "LABEL")
        success, name = self.saveNodeData(intraopLabel, outputDir, '.nrrd', name=intraopLabelName)
        self.handleSaveNodeDataReturn(success, name, successfullySavedData, failedSaveOfData)

        modelName = intraopLabel.GetName().replace("label", "MODEL")
        if self.clippingModelNode:
          success, name = self.saveNodeData(self.clippingModelNode, outputDir, '.vtk', name=modelName)
          self.handleSaveNodeDataReturn(success, name, successfullySavedData, failedSaveOfData)

    def saveOriginalTargets():
      originalTargets = self.registrationResults.originalTargets
      if originalTargets:
        success, name = self.saveNodeData(originalTargets, outputDir, '.fcsv', name="PreopTargets")
        self.handleSaveNodeDataReturn(success, name, successfullySavedData, failedSaveOfData)

    def saveBiasCorrectionResult():
      if self.biasCorrectionDone:
        biasCorrectedResult = self.registrationResults.biasCorrectedResult
        if biasCorrectedResult:
          success, name = self.saveNodeData(biasCorrectedResult, outputDir, '.nrrd')
          self.handleSaveNodeDataReturn(success, name, successfullySavedData, failedSaveOfData)

    def saveZFrameTransformation():
      if self.zFrameTransform:
        success, name = self.saveNodeData(self.zFrameTransform, outputDir, '.h5')
        self.handleSaveNodeDataReturn(success, name, successfullySavedData, failedSaveOfData)

    saveIntraopSegmentation()
    saveOriginalTargets()
    saveBiasCorrectionResult()
    saveZFrameTransformation()

    savedSuccessfully, failedToSave = self.registrationResults.save(outputDir)
    successfullySavedData += savedSuccessfully
    failedSaveOfData += failedToSave

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

  def getMostRecentWholeGlandSegmentation(self, path):
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
      self.currentResult.setVolume(regType, self.createScalarVolumeNode(prefix + '-VOLUME-' + regType + suffix))
      transformName = prefix + '-TRANSFORM-' + regType + suffix
      transform = self.createBSplineTransformNode(transformName) if regType == 'bSpline' \
        else self.createLinearTransformNode(transformName)
      self.currentResult.setTransform(regType, transform)

  def transformTargets(self, registrations, targets, prefix):
    if targets:
      for registration in registrations:
        name = prefix + '-TARGETS-' + registration
        clone = self.cloneFiducialAndTransform(name, targets, self.currentResult.getTransform(registration))
        self.markupsLogic.SetAllMarkupsLocked(clone, True)
        self.currentResult.setTargets(registration, clone)

  def applyInitialRegistration(self, fixedVolume, sourceVolume, fixedLabel, movingLabel, targets, progressCallback=None):

    self.progressCallback = progressCallback
    if not self.retryMode:
      self.registrationResults = RegistrationResults()
    name, suffix = self.getRegistrationResultNameAndGeneratedSuffix(fixedVolume.GetName())
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

    coverProstateRegResult = self.registrationResults.getMostRecentApprovedCoverProstateRegistration()

    lastRigidTfm = self.registrationResults.getLastApprovedRigidTransformation()

    name, suffix = self.getRegistrationResultNameAndGeneratedSuffix(self.currentIntraopVolume.GetName())
    result = self.registrationResults.createResult(name+suffix)
    result.fixedVolume = self.currentIntraopVolume
    result.fixedLabel = self.volumesLogic.CreateAndAddLabelVolume(slicer.mrmlScene, self.currentIntraopVolume,
                                                                  self.currentIntraopVolume.GetName() + '-label')
    result.originalTargets = coverProstateRegResult.approvedTargets
    sourceVolume = coverProstateRegResult.fixedVolume
    result.movingVolume = self.volumesLogic.CloneVolume(slicer.mrmlScene, sourceVolume, 'movingVolumeReReg')

    self.runBRAINSResample(inputVolume=coverProstateRegResult.fixedLabel, referenceVolume=self.currentIntraopVolume,
                           outputVolume=result.fixedLabel, warpTransform=lastRigidTfm)

    self.createVolumeAndTransformNodes(['rigid', 'bSpline'], prefix=str(result.seriesNumber), suffix=suffix)

    self.doRigidRegistration(initialTransform=lastRigidTfm)
    self.dilateMask(result.fixedLabel)
    self.doBSplineRegistration(initialTransform=self.currentResult.rigidTransform, useScaleVersor3D=True,
                               useScaleSkewVersor3D=True, useAffine=True)

    self.transformTargets(['rigid', 'bSpline'], result.originalTargets, str(result.seriesNumber))
    result.movingVolume = sourceVolume

  def getRegistrationResultNameAndGeneratedSuffix(self, name):
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
    clonedTargets.SetAndObserveDisplayNodeID(self.displayNode.GetID())
    tfmLogic.hardenTransform(clonedTargets)
    return clonedTargets

  def cloneFiducials(self, original, cloneName):
    nodeId = self.markupsLogic.AddNewFiducialNode(cloneName, slicer.mrmlScene)
    clone = slicer.mrmlScene.GetNodeByID(nodeId)
    for i in range(original.GetNumberOfFiducials()):
      pos = [0.0, 0.0, 0.0]
      original.GetNthFiducialPosition(i, pos)
      name = original.GetNthFiducialLabel(i)
      clone.AddFiducial(pos[0], pos[1], pos[2])
      clone.SetNthFiducialLabel(i, name)
    return clone

  def dilateMask(self, mask):
    imagedata = mask.GetImageData()
    dilateErode = vtk.vtkImageDilateErode3D()
    dilateErode.SetInputData(imagedata)
    dilateErode.SetDilateValue(1.0)
    dilateErode.SetErodeValue(0.0)
    dilateErode.SetKernelSize(12,12,1)
    dilateErode.Update()
    mask.SetAndObserveImageData(dilateErode.GetOutput())

  def startIntraopDirListener(self):
    self.currentFileList = []
    self.lastFileCount = len(self.getFileList(self._intraopDataDir))
    self.currentFileCount = self.lastFileCount
    self.importDICOMSeries()
    self.stopWatching()
    self.startWatchingIntraop()

  def stopWatching(self):
    self.importTimer.stop()
    self.watchTimer.stop()

  def startWatchingIntraop(self):
    self.currentFileCount = len(self.getFileList(self._intraopDataDir))
    if self.lastFileCount != self.currentFileCount:
      self.importTimer.start()
    self.lastFileCount = self.currentFileCount
    self.watchTimer.start()

  def createLoadableFileListForSeries(self, selectedSeries):
    selectedSeriesNumber = RegistrationResult.getSeriesNumberFromString(selectedSeries)
    self.loadableList[selectedSeries] = []
    for dcm in self.getFileList(self._intraopDataDir):
      currentFile = os.path.join(self._intraopDataDir, dcm)
      currentSeriesNumber = int(self.getDICOMValue(currentFile, DICOMTAGS.SERIES_NUMBER))
      if currentSeriesNumber and currentSeriesNumber == selectedSeriesNumber:
        self.loadableList[selectedSeries].append(currentFile)

  def getOrCreateVolumeForSeries(self, series):
    try:
      volume = self.alreadyLoadedSeries[series]
    except KeyError:
      files = self.loadableList[series]
      loadables = self.scalarVolumePlugin.examine([files])
      volume = self.scalarVolumePlugin.load(loadables[0])
      volume.SetName(loadables[0].name)
      self.alreadyLoadedSeries[series] = volume
    return volume

  def importDICOMSeries(self):
    indexer = ctk.ctkDICOMIndexer()
    db = slicer.dicomDatabase

    fileList = self.getFileList(self._intraopDataDir)

    newFileList = list(set(fileList) - set(self.currentFileList))

    for currentFile in newFileList:
      currentFile = os.path.join(self._intraopDataDir, currentFile)
      indexer.addFile(db, currentFile, None)
      series = self.makeSeriesNumberDescription(currentFile)
      if series and series not in self.seriesList and self.isDICOMSeriesEligible(series):
        self.seriesList.append(series)
        self.createLoadableFileListForSeries(series)

    indexer.addDirectory(db, self._intraopDataDir)
    indexer.waitForImportFinished()

    self.seriesList = sorted(self.seriesList, key=lambda series: RegistrationResult.getSeriesNumberFromString(series))

    if self._incomingDataCallback and len(newFileList) > 0 and \
                    len(self.getFileList(self._intraopDataDir)) == self.currentFileCount:
      self._incomingDataCallback(newList=newFileList)

    self.currentFileList = fileList

  def deleteSeriesFromSeriesList(self, seriesNumber):
    for series in self.seriesList:
      currentSeriesNumber = RegistrationResult.getSeriesNumberFromString(series)
      if currentSeriesNumber == seriesNumber:
        self.seriesList.remove(series)

  def extractDateFromDICOMFile(self, currentFile, tag=DICOMTAGS.STUDY_DATE):
    extractedDate = self.getDICOMValue(currentFile, tag)
    if extractedDate:
      formatted = datetime.date(int(extractedDate[0:4]), int(extractedDate[4:6]), int(extractedDate[6:8]))
      return formatted.strftime("%Y-%b-%d")
    else:
      return ""

  def isDICOMSeriesEligible(self, series):
    return SliceTrackerConstants.COVER_PROSTATE in series or SliceTrackerConstants.COVER_TEMPLATE in series or \
           SliceTrackerConstants.GUIDANCE_IMAGE in series

  def makeSeriesNumberDescription(self, dicomFile):
    seriesDescription = self.getDICOMValue(dicomFile, DICOMTAGS.SERIES_DESCRIPTION)
    seriesNumber = self.getDICOMValue(dicomFile, DICOMTAGS.SERIES_NUMBER)
    seriesNumberDescription = None
    if seriesDescription and seriesNumber:
      seriesNumberDescription = seriesNumber + ": " + seriesDescription
    return seriesNumberDescription

  def getTargetPositions(self, registeredTargets):
    number_of_targets = registeredTargets.GetNumberOfFiducials()
    target_positions = []
    for target in range(number_of_targets):
      target_position = [0.0, 0.0, 0.0]
      registeredTargets.GetNthFiducialPosition(target, target_position)
      target_positions.append(target_position)
    logging.debug('target_positions are ' + str(target_positions))
    return target_positions

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

  def loadColorTable(self):

    self.mpReviewColorNode = slicer.vtkMRMLColorTableNode()
    colorNode = self.mpReviewColorNode
    colorNode.SetName('mpReview')
    slicer.mrmlScene.AddNode(colorNode)
    colorNode.SetTypeToUser()
    with open(self.defaultColorFile) as f:
      n = sum(1 for line in f)
    colorNode.SetNumberOfColors(n - 1)
    import csv
    self.structureNames = []
    with open(self.defaultColorFile, 'rb') as csvfile:
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
    for widgetName in ['Red', 'Green', 'Yellow']:
      slice = lm.sliceWidget(widgetName)
      sliceLogic = slice.sliceLogic()
      sliceLogic.FitSliceToAll()

    # set the mouse mode into Markups fiducial placement
    placeModePersistence = 1
    self.markupsLogic.StartPlaceMode(placeModePersistence)

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
    self.displayNode = slicer.vtkMRMLMarkupsDisplayNode()
    slicer.mrmlScene.AddNode(self.displayNode)
    self.inputMarkupNode = slicer.vtkMRMLMarkupsFiducialNode()
    self.inputMarkupNode.SetName('inputMarkupNode')
    slicer.mrmlScene.AddNode(self.inputMarkupNode)
    self.inputMarkupNode.SetAndObserveDisplayNodeID(self.displayNode.GetID())
    self.styleDisplayNode(self.displayNode)

  def styleDisplayNode(self, displayNode):
    displayNode.SetTextScale(0)
    displayNode.SetGlyphScale(2.0)

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

  def runBRAINSResample(self, inputVolume, referenceVolume, outputVolume, warpTransform):

    params = {'inputVolume': inputVolume, 'referenceVolume': referenceVolume, 'outputVolume': outputVolume,
              'warpTransform': warpTransform, 'interpolationMode': 'NearestNeighbor'}

    logging.debug('about to run BRAINSResample CLI with those params: ')
    logging.debug(params)
    slicer.cli.run(slicer.modules.brainsresample, None, params, wait_for_completion=True)
    logging.debug('resample labelmap through')
    slicer.mrmlScene.AddNode(outputVolume)

  def loadZFrameModel(self):
    zFrameModelPath = os.path.join(self.modulePath, self.ZFRAME_MODEL_PATH)
    if not self.zFrameModelNode:
      _, self.zFrameModelNode = slicer.util.loadModel(zFrameModelPath, returnNode=True)
      self.zFrameModelNode.SetName(self.ZFRAME_MODEL_NAME)
      slicer.mrmlScene.AddNode(self.zFrameModelNode)
      modelDisplayNode = self.zFrameModelNode.GetDisplayNode()
      modelDisplayNode.SetColor(1, 1, 0)
    self.zFrameModelNode.SetDisplayVisibility(False)

  def clearOldNodesByName(self, name):
    collection = slicer.mrmlScene.GetNodesByName(name)
    for index in range(collection.GetNumberOfItems()):
      slicer.mrmlScene.RemoveNode(collection.GetItemAsObject(index))

  def runZFrameRegistration(self, inputVolume):
    # TODO: create configfile that chooses the Registration algorithm to use
    configFilePath = os.path.join(self.modulePath, 'Resources/zframe', 'zframe-config.csv')
    registration = LineMarkerRegistration(inputVolume, configFilePath)
    registration.runRegistration()
    self.zFrameTransform = registration.getOutputTransformation()
    slicer.mrmlScene.AddNode(registration.getOutputVolume())
    self.applyZFrameTransform(self.zFrameTransform)

  def loadTemplateConfigFile(self):
    self.templateIndex = []
    self.templateConfig = []

    reader = csv.reader(open(self.defaultTemplateFile, 'rb'))
    try:
      next(reader)
      for row in reader:
        self.templateIndex.append(row[0:2])
        self.templateConfig.append([float(row[2]), float(row[3]), float(row[4]),
                                    float(row[5]), float(row[6]), float(row[7]),
                                    float(row[8])])
    except csv.Error as e:
      print('file %s, line %d: %s' % (self.defaultTemplateFile, reader.line_num, e))
      return

    self.createTemplateAndNeedlePathModel()
    self.setTemplateVisibility(0)
    self.setTemplatePathVisibility(0)
    self.setNeedlePathVisibility(0)
    self.updateTemplateVectors()

  def createTemplateAndNeedlePathModel(self):

    self.templatePathVectors = []
    self.templatePathOrigins = []

    self.checkAndCreateTemplateModelNode()
    self.checkAndCreatePathModelNode()

    pathModelAppend = vtk.vtkAppendPolyData()
    templateModelAppend = vtk.vtkAppendPolyData()

    for row in self.templateConfig:
      p, n = self.extractPointsAndNormalVectors(row)

      tempTubeFilter = self.createTubeFilter(p[0], p[1], radius=1.0, numSides=18)
      templateModelAppend.AddInputData(tempTubeFilter.GetOutput())
      templateModelAppend.Update()

      pathTubeFilter = self.createTubeFilter(p[0], p[2], radius=0.8, numSides=18)
      pathModelAppend.AddInputData(pathTubeFilter.GetOutput())
      pathModelAppend.Update()

      self.templatePathOrigins.append([row[0], row[1], row[2], 1.0])
      self.templatePathVectors.append([n[0], n[1], n[2], 1.0])
      self.templateMaxDepth.append(row[6])

    self.tempModelNode.SetAndObservePolyData(templateModelAppend.GetOutput())
    modelDisplayNode = self.tempModelNode.GetDisplayNode()
    modelDisplayNode.SetColor(0.5,0,1)
    self.pathModelNode.SetAndObservePolyData(pathModelAppend.GetOutput())
    modelDisplayNode = self.pathModelNode.GetDisplayNode()
    modelDisplayNode.SetColor(0.8,0.5,1)

  def createNeedleModelNode(self, start, end):
    self.removeNeedleModelNode()
    self.needleModelNode = self.createModelNode(self.COMPUTED_NEEDLE_MODEL_NAME)
    modelDisplayNode = self.setAndObserveDisplayNode(self.needleModelNode)
    modelDisplayNode.SetColor(0, 1, 0)
    pathTubeFilter = self.createTubeFilter(start, end, radius=1.0, numSides=18)
    self.needleModelNode.SetAndObservePolyData(pathTubeFilter.GetOutput())
    self.setNeedlePathVisibility(self.showNeedlePath)

  def removeNeedleModelNode(self):
    if self.needleModelNode:
      slicer.mrmlScene.RemoveNode(self.needleModelNode)
    self.clearOldNodesByName(self.COMPUTED_NEEDLE_MODEL_NAME)

  def extractPointsAndNormalVectors(self, row):
    p1 = numpy.array(row[0:3])
    p2 = numpy.array(row[3:6])
    v = p2-p1
    nl = numpy.linalg.norm(v)
    n = v/nl  # normal vector
    l = row[6]
    p3 = p1 + l * n
    return [p1, p2, p3], n

  def createTubeFilter(self, start, end, radius, numSides):
    lineSource = vtk.vtkLineSource()
    lineSource.SetPoint1(start)
    lineSource.SetPoint2(end)
    tubeFilter = vtk.vtkTubeFilter()

    tubeFilter.SetInputConnection(lineSource.GetOutputPort())
    tubeFilter.SetRadius(radius)
    tubeFilter.SetNumberOfSides(numSides)
    tubeFilter.CappingOn()
    tubeFilter.Update()
    return tubeFilter

  def checkAndCreatePathModelNode(self):
    if self.pathModelNode is None:
      self.pathModelNode = self.createModelNode(self.ZFRAME_TEMPLATE_PATH_NAME)
      self.setAndObserveDisplayNode(self.pathModelNode)

  def checkAndCreateTemplateModelNode(self):
    if self.tempModelNode is None:
      self.tempModelNode = self.createModelNode(self.ZFRAME_TEMPLATE_NAME)
      self.setAndObserveDisplayNode(self.tempModelNode)
      self.modelNodeTag = self.tempModelNode.AddObserver(slicer.vtkMRMLTransformableNode.TransformModifiedEvent,
                                                         self.updateTemplateVectors)

  def applyZFrameTransform(self, transform):
    for node in [node for node in [self.pathModelNode, self.tempModelNode, self.zFrameModelNode, self.needleModelNode] if node]:
      node.SetAndObserveTransformNodeID(transform.GetID())

  def setModelVisibility(self, node, visible):
    dnode = node.GetDisplayNode()
    if dnode is not None:
      dnode.SetVisibility(visible)

  def setModelSliceIntersectionVisibility(self, node, visible):
    dnode = node.GetDisplayNode()
    if dnode is not None:
      dnode.SetSliceIntersectionVisibility(visible)

  def setZFrameVisibility(self, visibility):
    self.setModelVisibility(self.zFrameModelNode, visibility)
    self.setModelSliceIntersectionVisibility(self.zFrameModelNode, visibility)

  def setTemplateVisibility(self, visibility):
    self.setModelVisibility(self.tempModelNode, visibility)

  def setTemplatePathVisibility(self, visibility):
    self.showTemplatePath = visibility
    self.setModelVisibility(self.pathModelNode, visibility)
    self.setModelSliceIntersectionVisibility(self.pathModelNode, visibility)

  def setNeedlePathVisibility(self, visibility):
    self.showNeedlePath = visibility
    if self.needleModelNode:
      self.setModelVisibility(self.needleModelNode, visibility)
      self.setModelSliceIntersectionVisibility(self.needleModelNode, visibility)

  def updateTemplateVectors(self, observee=None, event=None):
    if self.tempModelNode is None:
      return

    trans = vtk.vtkMatrix4x4()
    transformNode = self.tempModelNode.GetParentTransformNode()
    if transformNode is not None:
      transformNode.GetMatrixTransformToWorld(trans)
    else:
      trans.Identity()

    # Calculate offset
    zero = [0.0, 0.0, 0.0, 1.0]
    offset = trans.MultiplyDoublePoint(zero)

    self.pathOrigins = []
    self.pathVectors = []

    for i, orig in enumerate(self.templatePathOrigins):
      torig = trans.MultiplyDoublePoint(orig)
      self.pathOrigins.append(numpy.array(torig[0:3]))
      vec = self.templatePathVectors[i]
      tvec = trans.MultiplyDoublePoint(vec)
      self.pathVectors.append(numpy.array([tvec[0]-offset[0], tvec[1]-offset[1], tvec[2]-offset[2]]))
      i += 1

  def computeNearestPath(self, pos):
    minMag2 = numpy.Inf
    minDepth = 0.0
    minIndex = -1
    needleStart = None
    needleEnd = None

    p = numpy.array(pos)
    for i, orig in enumerate(self.pathOrigins):
      vec = self.pathVectors[i]
      op = p - orig
      aproj = numpy.inner(op, vec)
      perp = op-aproj*vec
      mag2 = numpy.vdot(perp, perp)
      if mag2 < minMag2:
        minMag2 = mag2
        minIndex = i
        minDepth = aproj
      i += 1

    indexX = '--'
    indexY = '--'
    inRange = False

    if minIndex != -1:
      indexX = self.templateIndex[minIndex][0]
      indexY = self.templateIndex[minIndex][1]
      if 0 < minDepth < self.templateMaxDepth[minIndex]:
        inRange = True
        needleStart, needleEnd = self.getNeedleStartEndPointFromPathOrigins(minIndex)
      else:
        self.removeNeedleModelNode()

    return needleStart, needleEnd, indexX, indexY, minDepth, inRange

  def getNeedleStartEndPointFromPathOrigins(self, index):
    start = self.pathOrigins[index]
    v = self.pathVectors[index]
    nl = numpy.linalg.norm(v)
    n = v / nl  # normal vector
    l = self.templateMaxDepth[index]
    end = start + l * n
    return start, end


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
from SliceTrackerUtils.decorators import onExceptionReturnNone


class RegistrationResults(object):

  @property
  def activeResult(self):
    return self._getActiveResult()

  @activeResult.setter
  def activeResult(self, series):
    assert series in self._registrationResults.keys()
    self._activeResult = series

  @property
  @onExceptionReturnNone
  def originalTargets(self):
    return self.getMostRecentApprovedCoverProstateRegistration().originalTargets

  @property
  @onExceptionReturnNone
  def intraopLabel(self):
    return self.getMostRecentApprovedCoverProstateRegistration().fixedLabel

  @property
  @onExceptionReturnNone
  def biasCorrectedResult(self):
    return self.getMostRecentApprovedCoverProstateRegistration().movingVolume

  def __init__(self):
    self._registrationResults = OrderedDict()
    self._activeResult = None
    self.preopTargets = None

  def save(self, outputDir):
    savedSuccessfully = []
    failedToSave = []

    for result in self._registrationResults.values():
      successfulList, failedList = result.save(outputDir)
      savedSuccessfully += successfulList
      failedToSave += failedList

    return savedSuccessfully, failedToSave

  def _registrationResultHasStatus(self, series, status):
    if not type(series) is int:
      series = RegistrationResult.getSeriesNumberFromString(series)
    results = self.getResultsBySeriesNumber(series)
    return any(result.status == status for result in results) if len(results) else False

  def registrationResultWasApproved(self, series):
    return self._registrationResultHasStatus(series, RegistrationResult.APPROVED_STATUS)

  def registrationResultWasSkipped(self, series):
    return self._registrationResultHasStatus(series, RegistrationResult.SKIPPED_STATUS)

  def registrationResultWasRejected(self, series):
    return self._registrationResultHasStatus(series, RegistrationResult.REJECTED_STATUS)

  def getResultsAsList(self):
    return self._registrationResults.values()

  def getMostRecentApprovedCoverProstateRegistration(self):
    mostRecent = None
    for result in self._registrationResults.values():
      if SliceTrackerConstants.COVER_PROSTATE in result.name and result.approved:
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

  @onExceptionReturnNone
  def getResult(self, series):
    return self._registrationResults[series]

  def getResultsBySeries(self, series):
    seriesNumber = RegistrationResult.getSeriesNumberFromString(series)
    return self.getResultsBySeriesNumber(seriesNumber)

  def getResultsBySeriesNumber(self, seriesNumber):
    return [result for result in self.getResultsAsList() if seriesNumber == result.seriesNumber]

  def removeResult(self, series):
    try:
      del self._registrationResults[series]
    except KeyError:
      pass

  def exists(self, series):
    return series in self._registrationResults.keys()

  @onExceptionReturnNone
  def _getActiveResult(self):
    return self._registrationResults[self._activeResult]

  @onExceptionReturnNone
  def getMostRecentResult(self):
    lastKey = self._registrationResults.keys()[-1]
    return self._registrationResults[lastKey]

  @onExceptionReturnNone
  def getMostRecentApprovedResult(self):
    for result in reversed(self._registrationResults.values()):
      if result.approved:
        return result
    return None

  @onExceptionReturnNone
  def getMostRecentVolumes(self):
    return self.getMostRecentResult().volumes

  @onExceptionReturnNone
  def getMostRecentTransforms(self):
    return self.getMostRecentResult().transforms

  @onExceptionReturnNone
  def getMostRecentTargets(self):
    return self.getMostRecentResult().targets


class RegistrationResult(ModuleLogicMixin):

  REGISTRATION_TYPE_NAMES = ['rigid', 'affine', 'bSpline']

  SKIPPED_STATUS = 'skipped'
  APPROVED_STATUS = 'approved'
  REJECTED_STATUS = 'rejected'
  POSSIBLE_STATES = [SKIPPED_STATUS, APPROVED_STATUS, REJECTED_STATUS]

  @staticmethod
  def getSeriesNumberFromString(text):
    return int(text.split(": ")[0])

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
  @onExceptionReturnNone
  def approvedTargets(self):
    return self.targets[self.approvedRegistrationType]

  @property
  @onExceptionReturnNone
  def approvedVolume(self):
    return self.volumes[self.approvedRegistrationType]

  @property
  def approved(self):
    return self.status == self.APPROVED_STATUS

  @property
  def skipped(self):
    return self.status == self.SKIPPED_STATUS

  @property
  def rejected(self):
    return self.status == self.REJECTED_STATUS

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

  @property
  def targetsWereModified(self):
    return len(self.modifiedTargets) > 0

  def __init__(self, series):
    self.name = series

    self.status = None
    self.approvedRegistrationType = None

    self._initVolumes()
    self._initTransforms()
    self._initTargets()
    self._initLabels()

    self.cmdArguments = ""
    self.score = None

    self.modifiedTargets = {}

  def isGoingToBeMoved(self, targetList, index):
    assert targetList in self.targets.values()
    if not self.modifiedTargets.has_key(targetList):
      self.modifiedTargets[targetList] = {}
    if not self.modifiedTargets[targetList].has_key(index):
      originalPosition = [0.0, 0.0, 0.0]
      targetList.GetNthFiducialPosition(index, originalPosition)
      self.modifiedTargets[targetList][index] = originalPosition

  def _initLabels(self):
    self.movingLabel = None
    self.fixedLabel = None

  def _initTargets(self):
    self.rigidTargets = None
    self.affineTargets = None
    self.bSplineTargets = None
    self.originalTargets = None

  def _initTransforms(self):
    self.rigidTransform = None
    self.affineTransform = None
    self.bSplineTransform = None

  def _initVolumes(self):
    self.fixedVolume = None
    self.movingVolume = None
    self.rigidVolume = None
    self.affineVolume = None
    self.bSplineVolume = None

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

  def approve(self, registrationType):
    assert registrationType in self.REGISTRATION_TYPE_NAMES
    self.approvedRegistrationType = registrationType
    self.status = self.APPROVED_STATUS

  def skip(self):
    self.status = self.SKIPPED_STATUS

  def reject(self):
    self.status = self.REJECTED_STATUS

  def printSummary(self):
    logging.debug('# ___________________________  registration output  ________________________________')
    logging.debug(self.__dict__)
    logging.debug('# __________________________________________________________________________________')

  def save(self, outputDir):
    savedSuccessfully = []
    failedToSave = []

    def saveCMDParameters():
      name = self.replaceUnwantedCharacters(self.name)
      filename = os.path.join(outputDir, name + "-CMD-PARAMETERS.txt")
      f = open(filename, 'w+')
      f.write(self.cmdArguments)
      f.close()

    def saveTransformations():
      for transformNode in [node for node in self.transforms.values() if node]:
        success, name = self.saveNodeData(transformNode, outputDir, ".h5")
        self.handleSaveNodeDataReturn(success, name, savedSuccessfully, failedToSave)

    def saveTargets():
      for targetNode in [node for node in self.targets.values() if node]:
        success, name = self.saveNodeData(targetNode, outputDir, ".fcsv")
        self.handleSaveNodeDataReturn(success, name, savedSuccessfully, failedToSave)

    def saveApprovedTargets():
      if not self.approved:
        return
      fileName = self.approvedTargets.GetName().replace("-TARGETS-", "-APPROVED-TARGETS-")
      success, name = self.saveNodeData(self.approvedTargets, outputDir, ".fcsv", name=fileName)
      self.handleSaveNodeDataReturn(success, name, savedSuccessfully, failedToSave)

    saveCMDParameters()
    saveTransformations()
    saveTargets()
    saveApprovedTargets()

    return savedSuccessfully, failedToSave


class IncomingDataMessageBox(ExtendedQMessageBox):

  def __init__(self, parent=None):
    super(IncomingDataMessageBox, self).__init__(parent)
    self.setWindowTitle("Dialog with CheckBox")
    self.setText("New data has been received. What would you do?")
    self.setIcon(qt.QMessageBox.Question)
    trackButton =  self.addButton(qt.QPushButton('Track targets'), qt.QMessageBox.AcceptRole)
    self.addButton(qt.QPushButton('Postpone'), qt.QMessageBox.NoRole)
    self.setDefaultButton(trackButton)


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


class CustomTargetTableModel(qt.QAbstractTableModel):

  COLUMN_NAME = 'Name'
  COLUMN_2D_DISTANCE = 'Cursor distance 2D[mm]'
  COLUMN_3D_DISTANCE = 'Cursor distance 3D[mm]'
  COLUMN_HOLE = 'Hole'
  COLUMN_DEPTH = 'Depth [mm]'

  headers = [COLUMN_NAME, COLUMN_2D_DISTANCE, COLUMN_3D_DISTANCE, COLUMN_HOLE, COLUMN_DEPTH]

  @property
  def targetList(self):
    return self._targetList

  @targetList.setter
  def targetList(self, targetList):
    self.needleStartEndPositions = {}
    if self._targetList and self.observer:
      self._targetList.RemoveObserver(self.observer)
    self._targetList = targetList
    if self._targetList:
      self.observer = self._targetList.AddObserver(self._targetList.PointModifiedEvent, self.computeNewDepthAndHole)
    self.computeNewDepthAndHole()
    self.reset()

  @property
  def cursorPosition(self):
    return self._cursorPosition

  @cursorPosition.setter
  def cursorPosition(self, cursorPosition):
    self._cursorPosition = cursorPosition
    self.dataChanged(self.index(0, 1), self.index(self.rowCount(None)-1, 2))

  def __init__(self, logic, targets=None, parent=None, *args):
    qt.QAbstractTableModel.__init__(self, parent, *args)
    self.logic = logic
    self._cursorPosition = None
    self._targetList = None
    self.needleStartEndPositions = {}
    self.targetList = targets
    self.computeCursorDistances = False
    self.zFrameDepths = {}
    self.zFrameHole = {}
    self.observer = None
    self._targetModifiedCallback = None

  def setTargetModifiedCallback(self, func):
    assert hasattr(func, '__call__')
    self._targetModifiedCallback = func

  def headerData(self, col, orientation, role):
    if orientation == qt.Qt.Horizontal and role == qt.Qt.DisplayRole:
        return self.headers[col]
    return None

  def rowCount(self, parent=None):
    try:
      number_of_targets = self.targetList.GetNumberOfFiducials()
      return number_of_targets
    except AttributeError:
      return 0

  def columnCount(self, parent=None):
    return len(self.headers)

  def data(self, index, role):
    if not index.isValid() or role != qt.Qt.DisplayRole:
      return None

    row = index.row()
    col = index.column()

    targetPosition = [0.0, 0.0, 0.0]
    if col in [1,2,3,4]:
      self.targetList.GetNthFiducialPosition(row, targetPosition)

    if col == 0:
      return self.targetList.GetNthFiducialLabel(row)
    elif (col == 1 or col == 2) and self.cursorPosition and self.computeCursorDistances:
      if col == 1:
        distance2D = self.logic.getNeedleTipTargetDistance2D(targetPosition, self.cursorPosition)
        return 'x = ' + str(round(distance2D[0], 2)) + ' y = ' + str(round(distance2D[1], 2))
      distance3D = self.logic.getNeedleTipTargetDistance3D(targetPosition, self.cursorPosition)
      return str(round(distance3D, 2))

    elif (col == 3 or col == 4) and self.logic.zFrameRegistrationSuccessful:
      if col == 3:
        return self.computeZFrameHole(row, targetPosition)
      else:
        return self.computeZFrameDepth(row, targetPosition)
    return ""

  def computeZFrameHole(self, index, targetPosition):
    if index not in self.zFrameHole.keys():
      (start, end, indexX, indexY, depth, inRange) = self.logic.computeNearestPath(targetPosition)
      self.needleStartEndPositions[index] = (start, end)
      self.zFrameHole[index] = '(%s, %s)' % (indexX, indexY)
    return self.zFrameHole[index]

  def computeZFrameDepth(self, index, targetPosition):
    if index not in self.zFrameDepths.keys():
      (start, end, indexX, indexY, depth, inRange) = self.logic.computeNearestPath(targetPosition)
      self.zFrameDepths[index] = '%.3f' % depth if inRange else '(%.3f)' % depth
    return self.zFrameDepths[index]

  def computeNewDepthAndHole(self, observer=None, caller=None):
    self.zFrameDepths = {}
    self.zFrameHole = {}
    if not self.targetList or not self.logic.zFrameRegistrationSuccessful:
      return

    for index in range(self.targetList.GetNumberOfFiducials()):
      pos = [0.0, 0.0, 0.0]
      self.targetList.GetNthFiducialPosition(index, pos)
      self.computeZFrameHole(index, pos)

    self.dataChanged(self.index(0, 3), self.index(self.rowCount(None)-1, 4))
    if self._targetModifiedCallback:
      self._targetModifiedCallback()