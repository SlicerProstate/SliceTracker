import os
import math, re
from __main__ import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from Editor import EditorWidget
import SimpleITK as sitk
import sitkUtils
import EditorLib
import logging


class DICOMTAGS:

  PATIENT_NAME          = '0010,0010'
  PATIENT_ID            = '0010,0020'
  PATIENT_BIRTH_DATE    = '0010,0030'
  SERIES_DESCRIPTION    = '0008,103E'
  SERIES_NUMBER         = '0020,0011'
  STUDY_DATE            = '0008,0020'
  STUDY_TIME            = '0008,0030'
  ACQUISITION_TIME      = '0008,0032'


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


class SliceTrackerWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  STYLE_GRAY_BACKGROUND_WHITE_FONT  = 'background-color: rgb(130,130,130); ' \
                                      'color: rgb(255,255,255)'
  STYLE_WHITE_BACKGROUND            = 'background-color: rgb(255,255,255)'
  STYLE_LIGHT_GRAY_BACKGROUND       = 'background-color: rgb(230,230,230)'
  STYLE_ORANGE_BACKGROUND           = 'background-color: rgb(255,102,0)'

  COLOR_RED = qt.QColor(qt.Qt.red)
  COLOR_YELLOW = qt.QColor(qt.Qt.yellow)
  COLOR_GREEN = qt.QColor(qt.Qt.green)

  @staticmethod
  def makeProgressIndicator(maxVal, initialValue=0):
    progressIndicator = qt.QProgressDialog()
    progressIndicator.minimumDuration = 0
    progressIndicator.modal = True
    progressIndicator.setMaximum(maxVal)
    progressIndicator.setValue(initialValue)
    progressIndicator.setWindowTitle("Processing...")
    progressIndicator.show()
    progressIndicator.autoClose = False
    return progressIndicator

  @staticmethod
  def createDirectory(directory, message=None):
    if message:
      logging.debug(message)
    try:
      os.makedirs(directory)
    except OSError:
      logging.debug('Failed to create the following directory: ' + directory)

  @staticmethod
  def confirmDialog(message, title='SliceTracker'):
    result = qt.QMessageBox.question(slicer.util.mainWindow(), title, message,
                                     qt.QMessageBox.Ok | qt.QMessageBox.Cancel)
    return result == qt.QMessageBox.Ok

  @staticmethod
  def notificationDialog(message, title='SliceTracker'):
    return qt.QMessageBox.information(slicer.util.mainWindow(), title, message)

  @staticmethod
  def yesNoDialog(message, title='SliceTracker'):
    result = qt.QMessageBox.question(slicer.util.mainWindow(), title, message,
                                     qt.QMessageBox.Yes | qt.QMessageBox.No)
    return result == qt.QMessageBox.Yes

  @staticmethod
  def warningDialog(message, title='SliceTracker'):
    return qt.QMessageBox.warning(slicer.util.mainWindow(), title, message)

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

  def onReload(self):
    ScriptedLoadableModuleWidget.onReload(self)
    slicer.mrmlScene.Clear(0)
    self.biasCorrectionDone = False
    self.logic = SliceTrackerLogic()

  def getSetting(self, settingName):
    settings = qt.QSettings()
    return str(settings.value(self.moduleName + '/' + settingName))

  def setSetting(self, settingName, value):
    settings = qt.QSettings()
    settings.setValue(self.moduleName + '/' + settingName, value)

  def createPatientWatchBox(self):
    self.patientViewBox = qt.QGroupBox()
    self.patientViewBox.setStyleSheet(self.STYLE_LIGHT_GRAY_BACKGROUND)
    self.patientViewBox.setFixedHeight(90)
    self.patientViewBoxLayout = qt.QGridLayout()
    self.patientViewBox.setLayout(self.patientViewBoxLayout)
    self.patientViewBoxLayout.setColumnMinimumWidth(1, 50)
    self.patientViewBoxLayout.setColumnMinimumWidth(2, 50)
    self.patientViewBoxLayout.setHorizontalSpacing(0)
    self.layout.addWidget(self.patientViewBox)
    # create patient attributes
    self.categoryPatientID = qt.QLabel('Patient ID: ')
    self.patientViewBoxLayout.addWidget(self.categoryPatientID, 1, 1)
    self.categoryPatientName = qt.QLabel('Patient Name: ')
    self.patientViewBoxLayout.addWidget(self.categoryPatientName, 2, 1)
    self.categoryPatientBirthDate = qt.QLabel('Date of Birth: ')
    self.patientViewBoxLayout.addWidget(self.categoryPatientBirthDate, 3, 1)
    self.categoryPreopStudyDate = qt.QLabel('Preop Study Date:')
    self.patientViewBoxLayout.addWidget(self.categoryPreopStudyDate, 4, 1)
    self.categoryCurrentStudyDate = qt.QLabel('Current Study Date:')
    self.patientViewBoxLayout.addWidget(self.categoryCurrentStudyDate, 5, 1)
    self.patientID = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.patientID, 1, 2)
    self.patientName = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.patientName, 2, 2)
    self.patientBirthDate = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.patientBirthDate, 3, 2)
    self.preopStudyDate = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.preopStudyDate, 4, 2)
    self.currentStudyDate = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.currentStudyDate, 5, 2)

  def createIcon(self, filename):
    path = os.path.join(self.iconPath, filename)
    pixmap = qt.QPixmap(path)
    return qt.QIcon(pixmap)

  def createLabel(self, title, **kwargs):
    label = qt.QLabel(title)
    return self.extendQtGuiElementProperties(label, **kwargs)

  def createButton(self, title, **kwargs):
    button = qt.QPushButton(title)
    return self.extendQtGuiElementProperties(button, **kwargs)

  def extendQtGuiElementProperties(self, element, **kwargs):
    for key, value in kwargs.iteritems():
      if hasattr(element, key):
        setattr(element, key, value)
      else:
        if key == "fixedHeight":
          element.minimumHeight = value
          element.maximumHeight = value
        elif key == 'hidden':
          if value:
            element.hide()
          else:
            element.show()
        else:
          logging.error("%s does not have attribute %s" % (element.className(), key))
    return element

  def createComboBox(self, **kwargs):
    combobox = slicer.qMRMLNodeComboBox()
    combobox.addEnabled = False
    combobox.removeEnabled = False
    combobox.noneEnabled = True
    combobox.showHidden = False
    for key, value in kwargs.iteritems():
      if hasattr(combobox, key):
        setattr(combobox, key, value)
      else:
        logging.error("qMRMLNodeComboBox does not have attribute %s" % key)
    combobox.setMRMLScene(slicer.mrmlScene)
    return combobox

  def setupIcons(self):
    self.labelSegmentationIcon = self.createIcon('icon-labelSegmentation.png')
    self.cancelSegmentationIcon = self.createIcon('icon-cancelSegmentation.png')
    self.greenCheckIcon = self.createIcon('icon-greenCheck.png')
    self.acceptedIcon = self.createIcon('icon-accept.png')
    self.discardedIcon = self.createIcon('icon-discard.png')
    self.quickSegmentationIcon = self.createIcon('icon-quickSegmentation.png')
    self.folderIcon = self.createIcon('icon-folder.png')
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

    self.currentIntraopVolume = None
    self.currentIntraopLabel = None

    self.preopVolume = None
    self.preopLabel = None
    self.preopTargets = None

    self.seriesItems = []
    self.revealCursor = None

    self.quickSegmentationActive = False
    self.comingFromPreopTag = False
    self.biasCorrectionDone = False
    self.retryMode = False

    self.outputTargets = dict()
    self.outputVolumes = dict()
    self.outputTransforms = dict()

    self.reRegistrationMode = False
    self.registrationResults = []
    self.selectableRegistrationResults = []

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
    self.logic.setupColorTable()
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
    self.preopDataDir = ""
    self.preopDirButton = self.createButton('choose directory', icon=self.folderIcon)
    self.dataSelectionGroupBoxLayout.addRow("Preop directory:", self.preopDirButton)

    self.outputDir = self.getSetting('OutputLocation')
    self.outputDirButton = self.createButton(self.shortenDirText(self.outputDir), icon=self.folderIcon)
    self.dataSelectionGroupBoxLayout.addRow("Output directory:", self.outputDirButton)

    self.intraopDataDir = ""
    self.intraopDirButton = self.createButton('choose directory', icon=self.folderIcon, enabled=False)
    self.dataSelectionGroupBoxLayout.addRow("Intraop directory:", self.intraopDirButton)

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
                                         styleSheet=self.STYLE_WHITE_BACKGROUND)
    rowLayout.addWidget(self.reRegButton)
    self.dataSelectionGroupBoxLayout.addWidget(row)

  def setupProstateSegmentationStep(self):

    firstRow = qt.QWidget()
    rowLayout = qt.QHBoxLayout()
    firstRow.setLayout(rowLayout)

    self.text = qt.QLabel('Reference Volume: ')
    rowLayout.addWidget(self.text)

    # reference volume selector
    self.referenceVolumeSelector = self.createComboBox(nodeTypes=["vtkMRMLScalarVolumeNode", ""], noneEnabled=True,
                                                       selectNodeUponCreation=True, showChildNodeTypes=False,
                                                       toolTip="Pick the input to the algorithm.")
    rowLayout.addWidget(self.referenceVolumeSelector)

    helperPixmap = qt.QPixmap(os.path.join(self.iconPath, 'icon-infoBox.png'))
    helperPixmap = helperPixmap.scaled(qt.QSize(20, 20))
    self.helperLabel = self.createLabel("", pixmap=helperPixmap, toolTip="This is the information you needed, right?")

    rowLayout.addWidget(self.helperLabel)

    self.labelSelectionGroupBoxLayout.addRow(firstRow)

    # Set Icon Size for the 4 Icon Items
    size = qt.QSize(70, 30)
    self.quickSegmentationButton = self.createButton('Quick Mode', icon=self.quickSegmentationIcon, iconSize=size,
                                                     styleSheet=self.STYLE_WHITE_BACKGROUND)

    self.labelSegmentationButton = self.createButton('Label Mode', icon=self.labelSegmentationIcon, iconSize=size,
                                                     styleSheet=self.STYLE_WHITE_BACKGROUND)

    self.applySegmentationButton = self.createButton("", icon=self.greenCheckIcon, iconSize=size,
                                                     styleSheet=self.STYLE_WHITE_BACKGROUND, enabled=False)

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
    self.registrationGroupBoxLayout.addRow("Preop Image Volume: ", self.preopVolumeSelector)

    self.preopLabelSelector = self.createComboBox(nodeTypes=["vtkMRMLLabelMapVolumeNode", ""], showChildNodeTypes=False,
                                                  selectNodeUponCreation=False, toolTip="Pick algorithm input.")
    self.registrationGroupBoxLayout.addRow("Preop Label Volume: ", self.preopLabelSelector)

    self.intraopVolumeSelector = self.createComboBox(nodeTypes=["vtkMRMLScalarVolumeNode", ""], noneEnabled=True,
                                                     showChildNodeTypes=False, selectNodeUponCreation=True,
                                                     toolTip="Pick algorithm input.")
    self.registrationGroupBoxLayout.addRow("Intraop Image Volume: ", self.intraopVolumeSelector)
    self.intraopLabelSelector = self.createComboBox(nodeTypes=["vtkMRMLLabelMapVolumeNode", ""],
                                                    showChildNodeTypes=False,
                                                    selectNodeUponCreation=True, toolTip="Pick algorithm input.")
    self.registrationGroupBoxLayout.addRow("Intraop Label Volume: ", self.intraopLabelSelector)

    self.fiducialSelector = self.createComboBox(nodeTypes=["vtkMRMLMarkupsFiducialNode", ""], noneEnabled=True,
                                                showChildNodeTypes=False, selectNodeUponCreation=False,
                                                toolTip="Select the Targets")
    self.registrationGroupBoxLayout.addRow("Targets: ", self.fiducialSelector)

    self.applyBSplineRegistrationButton = self.createButton("Apply Registration", icon=self.greenCheckIcon,
                                                            toolTip="Run the algorithm.")
    self.applyBSplineRegistrationButton.setFixedHeight(45)
    self.registrationGroupBoxLayout.addRow(self.applyBSplineRegistrationButton)

  def setupRegistrationEvaluationStep(self):
    # Buttons which registration step should be shown
    selectPatientRowLayout = qt.QHBoxLayout()

    firstRow = qt.QWidget()
    rowLayout = self.createAlignedRowLayout(firstRow, alignment=qt.Qt.AlignLeft)

    self.text = qt.QLabel('Registration Result')
    rowLayout.addWidget(self.text)

    self.resultSelector = ctk.ctkComboBox()
    self.resultSelector.setFixedWidth(250)

    self.acceptRegistrationResultButton = self.createButton("Accept Result")
    self.retryRegistrationButton = self.createButton("Retry")
    self.skipRegistrationResultButton = self.createButton("Skip Result")

    self.acceptedRegistrationResultLabel = self.createLabel("", pixmap=self.acceptedIcon.pixmap(20, 20), hidden=True)
    self.discardedRegistrationResultLabel = self.createLabel("", pixmap=self.discardedIcon.pixmap(20, 20), hidden=True)
    self.registrationResultStatus = self.createLabel("accepted!", hidden=True)

    rowLayout.addWidget(self.resultSelector)
    rowLayout.addWidget(self.acceptRegistrationResultButton)
    rowLayout.addWidget(self.retryRegistrationButton)
    rowLayout.addWidget(self.skipRegistrationResultButton)
    rowLayout.addWidget(self.acceptedRegistrationResultLabel)
    rowLayout.addWidget(self.discardedRegistrationResultLabel)
    rowLayout.addWidget(self.registrationResultStatus)

    self.showPreopResultButton = self.createButton('Show Cover Prostate')
    self.showRigidResultButton = self.createButton('Show Rigid Result')
    self.showAffineResultButton = self.createButton('Show Affine Result')
    self.showBSplineResultButton = self.createButton('Show BSpline Result')

    self.registrationButtonGroup = qt.QButtonGroup()
    self.registrationButtonGroup.addButton(self.showPreopResultButton, 1)
    self.registrationButtonGroup.addButton(self.showRigidResultButton, 2)
    self.registrationButtonGroup.addButton(self.showAffineResultButton, 3)
    self.registrationButtonGroup.addButton(self.showBSplineResultButton, 4)

    biggerWidget = qt.QWidget()
    twoRowLayout = qt.QVBoxLayout()
    biggerWidget.setLayout(twoRowLayout)

    twoRowLayout.addWidget(firstRow)

    secondRow = qt.QWidget()
    rowLayout = qt.QHBoxLayout()
    secondRow.setLayout(rowLayout)
    rowLayout.addWidget(self.showPreopResultButton)
    rowLayout.addWidget(self.showRigidResultButton)
    rowLayout.addWidget(self.showAffineResultButton)
    rowLayout.addWidget(self.showBSplineResultButton)
    twoRowLayout.addWidget(secondRow)

    selectPatientRowLayout.addWidget(biggerWidget)

    self.groupBoxDisplay = qt.QGroupBox("Display")
    self.groupBoxDisplayLayout = qt.QFormLayout(self.groupBoxDisplay)
    self.groupBoxDisplayLayout.addRow(selectPatientRowLayout)
    self.evaluationGroupBoxLayout.addWidget(self.groupBoxDisplay)

    fadeHolder = qt.QWidget()
    fadeLayout = qt.QHBoxLayout()
    fadeHolder.setLayout(fadeLayout)

    self.visualEffectsGroupBox = qt.QGroupBox("Visual Evaluation")
    self.groupBoxLayout = qt.QFormLayout(self.visualEffectsGroupBox)
    self.evaluationGroupBoxLayout.addWidget(self.visualEffectsGroupBox)

    self.fadeSlider = ctk.ctkSliderWidget()
    self.fadeSlider.minimum = 0
    self.fadeSlider.maximum = 1.0
    self.fadeSlider.value = 0
    self.fadeSlider.singleStep = 0.05
    fadeLayout.addWidget(self.fadeSlider)

    animaHolder = qt.QWidget()
    animaLayout = qt.QVBoxLayout()
    animaHolder.setLayout(animaLayout)
    fadeLayout.addWidget(animaHolder)

    self.rockCount = 0
    self.rockTimer = qt.QTimer()
    self.rockCheckBox = qt.QCheckBox("Rock")
    self.rockCheckBox.checked = False
    animaLayout.addWidget(self.rockCheckBox)

    self.flickerTimer = qt.QTimer()
    self.flickerCheckBox = qt.QCheckBox("Flicker")
    self.flickerCheckBox.checked = False
    animaLayout.addWidget(self.flickerCheckBox)

    self.groupBoxLayout.addRow("Opacity", fadeHolder)

    self.revealCursorCheckBox = qt.QCheckBox("Use RevealCursor")
    self.revealCursorCheckBox.checked = False
    self.groupBoxLayout.addRow("", self.revealCursorCheckBox)

    self.groupBoxTargets = qt.QGroupBox("Targets")
    self.groupBoxLayoutTargets = qt.QFormLayout(self.groupBoxTargets)
    self.evaluationGroupBoxLayout.addWidget(self.groupBoxTargets)

    self.targetTable = qt.QTableWidget()
    self.targetTable.setRowCount(0)
    self.targetTable.setColumnCount(3)
    self.targetTable.setColumnWidth(0, 160)
    self.targetTable.setColumnWidth(1, 180)
    self.targetTable.setColumnWidth(2, 180)
    self.targetTable.setHorizontalHeaderLabels(['Target', 'Distance to needle-tip 2D [mm]',
                                                'Distance to needle-tip 3D [mm]'])
    self.groupBoxLayoutTargets.addRow(self.targetTable)

    self.needleTipButton = qt.QPushButton('Set needle-tip')
    self.groupBoxLayoutTargets.addRow(self.needleTipButton)

    self.groupBoxOutputData = qt.QGroupBox("Data output")
    self.groupBoxOutputDataLayout = qt.QFormLayout(self.groupBoxOutputData)
    self.evaluationGroupBoxLayout.addWidget(self.groupBoxOutputData)
    self.saveDataButton = self.createButton('Save Data', icon=self.littleDiscIcon, maximumWidth=150,
                                            enabled=os.path.exists(self.getSetting('OutputLocation')))
    self.groupBoxOutputDataLayout.addWidget(self.saveDataButton)

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
    self.tabWidget.connect('currentChanged(int)', self.onTabWidgetClicked)
    self.preopDirButton.connect('clicked()', self.onPreopDirSelected)
    self.intraopDirButton.connect('clicked()', self.onIntraopDirSelected)
    self.reRegButton.connect('clicked(bool)', self.onReRegistrationClicked)
    self.referenceVolumeSelector.connect('currentNodeChanged(bool)', self.onTab2clicked)
    self.forwardButton.connect('clicked(bool)', self.onForwardButtonClicked)
    self.backButton.connect('clicked(bool)', self.onBackButtonClicked)
    self.applyBSplineRegistrationButton.connect('clicked(bool)', self.onApplyRegistrationClicked)
    self.resultSelector.connect('currentIndexChanged(int)', self.onRegistrationResultSelected)
    self.fadeSlider.connect('valueChanged(double)', self.changeOpacity)
    self.rockCheckBox.connect('toggled(bool)', self.onRockToggled)
    self.flickerCheckBox.connect('toggled(bool)', self.onFlickerToggled)
    self.revealCursorCheckBox.connect('toggled(bool)', self.revealToggled)
    self.needleTipButton.connect('clicked(bool)', self.onNeedleTipButtonClicked)
    self.outputDirButton.connect('clicked()', self.onOutputDirSelected)
    self.quickSegmentationButton.connect('clicked(bool)', self.onQuickSegmentationButtonClicked)
    self.cancelSegmentationButton.connect('clicked(bool)', self.onCancelSegmentationButtonClicked)
    self.labelSegmentationButton.connect('clicked(bool)', self.onLabelSegmentationButtonClicked)
    self.applySegmentationButton.connect('clicked(bool)', self.onApplySegmentationButtonClicked)
    self.acceptRegistrationResultButton.connect('clicked(bool)', self.onAcceptRegistrationResultButtonClicked)
    self.skipRegistrationResultButton.connect('clicked(bool)', self.onSkipRegistrationResultButtonClicked)
    self.retryRegistrationButton.connect('clicked(bool)', self.onRetryRegistrationButtonClicked)
    self.loadAndSegmentButton.connect('clicked(bool)', self.onLoadAndSegmentButtonClicked)
    self.preopVolumeSelector.connect('currentNodeChanged(bool)', self.updateRegistrationOverviewTab)
    self.intraopVolumeSelector.connect('currentNodeChanged(bool)', self.updateRegistrationOverviewTab)
    self.intraopLabelSelector.connect('currentNodeChanged(bool)', self.updateRegistrationOverviewTab)
    self.preopLabelSelector.connect('currentNodeChanged(bool)', self.updateRegistrationOverviewTab)
    self.fiducialSelector.connect('currentNodeChanged(bool)', self.updateRegistrationOverviewTab)
    self.rockTimer.connect('timeout()', self.onRockToggled)
    self.flickerTimer.connect('timeout()', self.onFlickerToggled)
    self.saveDataButton.connect('clicked(bool)', self.onSaveDataButtonClicked)
    self.registrationButtonGroup.connect('buttonClicked(int)', self.onRegistrationButtonChecked)
    self.seriesModel.itemChanged.connect(self.updateSeriesSelectionButtons)

  def onRegistrationButtonChecked(self, id):
    if id == 1:
      self.onPreopResultClicked()
    elif id == 2:
      self.onRigidResultClicked()
    elif id == 3:
      self.onAffineResultClicked()
    elif id == 4:
      self.onBSplineResultClicked()

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

  def startStoreSCP(self):
    # TODO: add proper communication establishment
    # command : $ sudo storescp -v -p 104
    pathToExe = os.path.join(slicer.app.slicerHome, 'bin', 'storescp')
    port = 104
    cmd = ('sudo ' + pathToExe + ' -v -p ' + str(port))
    os.system(cmd)

  def onLoadAndSegmentButtonClicked(self):
    self.retryMode = False
    selectedSeriesList = self.getSelectedSeries()

    if len(selectedSeriesList) > 0:
      if self.reRegistrationMode:
        if not self.yesNoDialog("You are currently in the Re-Registration mode. Are you sure, that you want to "
                                "recreate the segmentation?"):
          return

      # TODO: delete volumes when starting new instead of just clearing
      self.logic.clearAlreadyLoadedSeries()
      self.currentIntraopVolume = self.logic.loadSeriesIntoSlicer(selectedSeriesList, self.intraopDataDir)

      self.tabBar.setTabEnabled(1, True)

      self.tabWidget.setCurrentIndex(1)

  def onReRegistrationClicked(self):
    logging.debug('Performing Re-Registration')

    selectedSeriesList = self.getSelectedSeries()

    if len(selectedSeriesList) == 1:
      self.currentIntraopVolume = self.logic.loadSeriesIntoSlicer(selectedSeriesList, self.intraopDataDir)
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

  def onRegistrationResultSelected(self):
    for index, result in enumerate(self.registrationResults):
      self.markupsLogic.SetAllMarkupsVisibility(result['outputTargetsRigid'], False)
      if 'outputTargetsAffine' in result.keys():
        self.markupsLogic.SetAllMarkupsVisibility(result['outputTargetsAffine'], False)
      self.markupsLogic.SetAllMarkupsVisibility(result['outputTargetsBSpline'], False)

      if result['name'] == self.resultSelector.currentText:
        self.currentRegistrationResultIndex = index

    self.currentIntraopVolume = self.registrationResults[-1]['fixedVolume']
    self.outputVolumes = self.getMostRecentVolumes()
    self.outputTargets = self.getTargetsForCurrentRegistrationResult()
    self.preopVolume = self.registrationResults[-1]['movingVolume']

    self.showAffineResultButton.setEnabled("GUIDANCE" not in self.resultSelector.currentText)

    self.onBSplineResultClicked()
    self.updateRegistrationResultStatus()

  def getMostRecentVolumes(self):
    results = self.registrationResults[-1]
    volumes = {'Rigid': results['outputVolumeRigid'], 'BSpline': results['outputVolumeBSpline']}
    if 'outputVolumeAffine' in results.keys():
      volumes['Affine'] = results['outputVolumeAffine']
    return volumes

  def getCurrentRegistrationResult(self):
    try:
      currentResult = self.registrationResults[self.currentRegistrationResultIndex]
    except AttributeError:
      currentResult = None
    return currentResult

  def getTargetsForCurrentRegistrationResult(self):
    results = self.getCurrentRegistrationResult()
    targets = {'Rigid': results['outputTargetsRigid'], 'BSpline': results['outputTargetsBSpline']}
    if 'outputTargetsAffine' in results.keys():
      targets['Affine'] = results['outputTargetsAffine']
    return targets

  def updateRegistrationResultSelector(self):
    for result in [result for result in self.registrationResults if result not in self.selectableRegistrationResults]:
      name = result['name']
      self.resultSelector.addItem(name)
      self.resultSelector.currentIndex = self.resultSelector.findText(name)
      self.selectableRegistrationResults.append(result)

  def clearTargetTable(self):

    self.needleTipButton.enabled = False

    self.targetTable.clear()
    self.targetTable.setColumnCount(3)
    self.targetTable.setColumnWidth(0, 180)
    self.targetTable.setColumnWidth(1, 200)
    self.targetTable.setColumnWidth(2, 200)
    self.targetTable.setHorizontalHeaderLabels(['Target', 'Distance to needle-tip 2D [mm]',
                                                'Distance to needle-tip 3D [mm]'])

  def onNeedleTipButtonClicked(self):
    self.needleTipButton.enabled = False
    self.logic.setNeedleTipPosition()

  def updateTargetTable(self, observer, caller):

    self.needleTip_position = []
    self.target_positions = []

    # get the positions of needle Tip and Targets
    [self.needleTip_position, self.target_positions] = self.logic.getNeedleTipAndTargetsPositions(
      self.outputTargets['BSpline'])

    # get the targets
    bSplineTargets = self.outputTargets['BSpline']
    number_of_targets = bSplineTargets.GetNumberOfFiducials()

    # set number of rows in targetTable
    self.targetTable.setRowCount(number_of_targets)
    self.target_items = []

    # refresh the targetTable
    for target in range(number_of_targets):
      target_text = bSplineTargets.GetNthFiducialLabel(target)
      item = qt.QTableWidgetItem(target_text)
      self.targetTable.setItem(target, 0, item)
      # make sure to keep a reference to the item
      self.target_items.append(item)

    self.items_2D = []
    self.items_3D = []

    for index in range(number_of_targets):
      distances = self.logic.measureDistance(self.target_positions[index], self.needleTip_position)
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

    # reset needleTipButton
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
    self.preopDataDir = qt.QFileDialog.getExistingDirectory(self.parent, 'Preop data directory',
                                                            self.getSetting('PreopLocation'))
    self.reRegistrationMode = False
    self.reRegButton.setEnabled(False)
    if os.path.exists(self.preopDataDir):
      self.setTabsEnabled([1, 2, 3], False)
      self.setSetting('PreopLocation', self.preopDataDir)
      self.preopDirButton.text = self.shortenDirText(self.preopDataDir)
      self.loadPreopData()
      self.updateSeriesSelectorTable()

  def shortenDirText(self, directory):
    try:
      split = directory.split('/')
      splittedDir = ('.../' + str(split[-2]) + '/' + str(split[-1]))
      return splittedDir
    except:
      pass

  def onIntraopDirSelected(self):
    self.intraopDataDir = qt.QFileDialog.getExistingDirectory(self.parent, 'Intraop data directory',
                                                              self.getSetting('IntraopLocation'))
    if os.path.exists(self.intraopDataDir):
      self.intraopDirButton.text = self.shortenDirText(self.intraopDataDir)
      self.setSetting('IntraopLocation', self.intraopDataDir)
      self.logic.initializeListener(self.intraopDataDir)

  def onOutputDirSelected(self):
    self.outputDir = qt.QFileDialog.getExistingDirectory(self.parent, 'Preop data directory',
                                                         self.getSetting('OutputLocation'))
    if os.path.exists(self.outputDir):
      self.outputDirButton.text = self.shortenDirText(self.outputDir)
      self.setSetting('OutputLocation', self.outputDir)
      self.saveDataButton.setEnabled(True)
    else:
      self.saveDataButton.setEnabled(False)

  def onSaveDataButtonClicked(self):
    # TODO: if registration was redone: make a sub folder and move all initial results there

    self.successfullySavedData = []
    self.failedSaveOfData = []

    # patient_id-biopsy_DICOM_study_date-study_time
    time = qt.QTime().currentTime().toString().replace(":", "")
    dirName = self.patientID.text + "-biopsy-" + self.currentStudyDate.text + time
    self.outputDirectory = os.path.join(self.outputDir, dirName, "MRgBiopsy")

    self.createDirectory(self.outputDirectory)

    self.saveIntraopSegmentation()
    self.saveBiasCorrectionResult()
    self.saveRegistrationResults()
    self.saveTipPosition()
    message = ""
    if len(self.successfullySavedData) > 0:
      message = "The following data was successfully saved:\n"
      for saved in self.successfullySavedData:
        message += saved + "\n"

    if len(self.failedSaveOfData) > 0:
      message += "The following data failed to saved:\n"
      for failed in self.failedSaveOfData:
        message += failed + "\n"

    return self.notificationDialog(message)

  def saveTipPosition(self):
    # TODO
    # if user clicked on the tip position - save that as well, prefixed with the series number
    pass

  def saveNodeData(self, node, extension, name=None):
    try:
      name = name if name else node.GetName()
      name = self.replaceUnwantedCharacters(name)
      filename = os.path.join(self.outputDirectory, name + extension)
      success = slicer.util.saveNode(node, filename)
      listToAdd = self.successfullySavedData if success else self.failedSaveOfData
      listToAdd.append(node.GetName())
    except AttributeError:
      self.failedSaveOfData.append(name)

  def replaceUnwantedCharacters(self, string, characters=[": ", " ", ":", "/"], replaceWith="-"):
    for character in characters:
      string = string.replace(character, replaceWith)
    return string

  def saveIntraopSegmentation(self):
    intraopLabelName = self.currentIntraopLabel.GetName().replace("label", "LABEL")
    self.saveNodeData(self.currentIntraopLabel, '.nrrd', name=intraopLabelName)
    self.saveNodeData(self.preopTargets, '.fcsv', name="PreopTargets")
    modelName = self.currentIntraopLabel.GetName().replace("label", "MODEL")
    self.saveNodeData(self.logic.clippingModelNode, '.vtk', name=modelName)

  def saveBiasCorrectionResult(self):
    if self.biasCorrectionDone:
      self.saveNodeData(self.preopVolume, '.nrrd')

  def saveRegistrationResults(self):
    self.saveRegistrationCommandLineArguments()
    self.saveOutputTransformations()
    self.saveTransformedFiducials()

  def saveRegistrationCommandLineArguments(self):
    for result in self.registrationResults:
      name = self.replaceUnwantedCharacters(result["name"])
      filename = os.path.join(self.outputDirectory, name + "-CMD-PARAMETERS.txt")
      f = open(filename, 'w+')
      f.write(result["cmdArguments"])
      f.close()

  def saveOutputTransformations(self):
    for result in self.registrationResults:
      for key in [key for key in result.keys() if key.find("outputTransform") != -1]:
        self.saveNodeData(result[key], ".h5")

  def saveTransformedFiducials(self):
    for result in self.registrationResults:
      for key in [key for key in result.keys() if key.find("outputTargets") != -1]:
        self.saveNodeData(result[key], ".fcsv")

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
      lastRegistrationResult = self.registrationResults[-1]
      if not lastRegistrationResult['accepted'] and not lastRegistrationResult['discarded']:
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
    if self.retryMode:
      self.setTabsEnabled([0], False)
    self.currentIndex = 1

    self.removeSliceAnnotations()

    self.referenceVolumeSelector.setCurrentNode(self.currentIntraopVolume)
    self.intraopVolumeSelector.setCurrentNode(self.currentIntraopVolume)

    enableButton = 0 if self.referenceVolumeSelector.currentNode() is None else 1
    self.labelSegmentationButton.setEnabled(enableButton)
    self.quickSegmentationButton.setEnabled(enableButton)

    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    self.compositeNodeRed.Reset()
    self.markupsLogic.SetAllMarkupsVisibility(self.preopTargets, False)
    self.compositeNodeRed.SetBackgroundVolumeID(self.currentIntraopVolume.GetID())

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
    if self.retryMode:
      self.setTabsEnabled([0], True)
      self.retryMode = False

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
    self.preopStudyDateDICOM = self.logic.getDICOMValue(currentFile, DICOMTAGS.STUDY_DATE)
    formattedDate = self.preopStudyDateDICOM[0:4] + "-" + self.preopStudyDateDICOM[4:6] + "-" + \
                    self.preopStudyDateDICOM[6:8]
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
    for seriesText in seriesList:
      sItem = qt.QStandardItem(seriesText)
      self.seriesItems.append(sItem)
      self.seriesModel.appendRow(sItem)
      sItem.setCheckable(0)
      color = self.COLOR_YELLOW
      if self.registrationResultWasAccepted(seriesText):
        color = self.COLOR_GREEN
      elif self.registrationResultWasSkipped(seriesText):
        color = self.COLOR_RED
      else:
        sItem.setCheckable(1)
      self.seriesModel.setData(sItem.index(), color, qt.Qt.BackgroundRole)

    for item in list(reversed(range(len(seriesList)))):
      seriesText = self.seriesModel.item(item).text()
      if "PROSTATE" in seriesText or "GUIDANCE" in seriesText:
        self.seriesModel.item(item).setCheckState(1)
        break
    self.updateSeriesSelectionButtons()

  def registrationResultWasSkipped(self, series):
    wasSkipped = False
    if series in self.logic.alreadyLoadedSeries.keys():
      for result in self.registrationResults:
        if series.split(':')[0] == result['name'].split(':')[0]:
          if result['accepted'] and result['discarded']:
            wasSkipped = True
    return wasSkipped

  def registrationResultWasAccepted(self, series):
    wasAccepted = False
    if series in self.logic.alreadyLoadedSeries.keys():
      for result in self.registrationResults:
        if series.split(':')[0] == result['name'].split(':')[0]:
          if result['accepted'] and not result['discarded']:
            wasAccepted = True
    return wasAccepted

  def resetShowResultButtons(self, checkedButton):
    checked = self.STYLE_GRAY_BACKGROUND_WHITE_FONT
    unchecked = self.STYLE_WHITE_BACKGROUND
    for button in self.registrationButtonGroup.buttons():
      button.setStyleSheet(checked if button is checkedButton else unchecked)

  def onPreopResultClicked(self):
    self.saveCurrentSliceViewPositions()
    self.resetShowResultButtons(checkedButton=self.showPreopResultButton)

    self.unlinkImages()

    currentResult = self.getCurrentRegistrationResult()
    self.compositeNodeRed.SetBackgroundVolumeID(currentResult['movingVolume'].GetID())
    self.compositeNodeRed.SetForegroundVolumeID(currentResult['fixedVolume'].GetID())

    # show preop Targets
    fiducialNode = currentResult['targets']
    self.markupsLogic.SetAllMarkupsVisibility(fiducialNode, True)

    self.setDefaultFOV(self.redSliceLogic)

    # jump to first markup slice
    self.markupsLogic.JumpSlicesToNthPointInMarkup(fiducialNode.GetID(), 0)

    restoredSlicePositions = self.savedSlicePositions
    self.setFOV(self.yellowSliceLogic, restoredSlicePositions['yellowFOV'], restoredSlicePositions['yellowOffset'])

    self.comingFromPreopTag = True

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

  def onRigidResultClicked(self):
    self.displayRegistrationResults(button=self.showRigidResultButton, registrationType='Rigid')

  def onAffineResultClicked(self):
    self.displayRegistrationResults(button=self.showAffineResultButton, registrationType='Affine')

  def onBSplineResultClicked(self):
    self.displayRegistrationResults(button=self.showBSplineResultButton, registrationType='BSpline')

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

  def unlinkImages(self):
    self._linkImages(0)

  def linkImages(self):
    self._linkImages(1)

  def _linkImages(self, link):
    self.compositeNodeRed.SetLinkedControl(link)
    self.compositeNodeYellow.SetLinkedControl(link)

  def setCurrentRegistrationResultSliceViews(self, registrationType):
    currentResult = self.getCurrentRegistrationResult()
    self.compositeNodeYellow.SetBackgroundVolumeID(currentResult['fixedVolume'].GetID())
    self.compositeNodeRed.SetForegroundVolumeID(currentResult['fixedVolume'].GetID())
    self.compositeNodeRed.SetBackgroundVolumeID(currentResult['outputVolume' + registrationType].GetID())

  def showTargets(self, registrationType):
    self.markupsLogic.SetAllMarkupsVisibility(self.outputTargets['Rigid'], 1 if registrationType == 'Rigid' else 0)
    self.markupsLogic.SetAllMarkupsVisibility(self.outputTargets['BSpline'], 1 if registrationType == 'BSpline' else 0)
    if 'Affine' in self.outputTargets.keys():
      self.markupsLogic.SetAllMarkupsVisibility(self.outputTargets['Affine'], 1 if registrationType == 'Affine' else 0)
    self.markupsLogic.JumpSlicesToNthPointInMarkup(self.outputTargets[registrationType].GetID(), 0)

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
    (success, self.preopVolume) = slicer.util.loadVolume(self.preopImagePath, returnNode=True)
    if success:
      self.preopVolume.SetName('volume-PREOP')
      self.preopVolumeSelector.setCurrentNode(self.preopVolume)
    return success

  def loadPreopTargets(self):
    mostRecentTargets = self.logic.getMostRecentTargetsFile(self.preopTargetsPath)
    success = False
    if mostRecentTargets:
      filename = os.path.join(self.preopTargetsPath, mostRecentTargets)
      (success, self.preopTargets) = slicer.util.loadMarkupsFiducialList(filename, returnNode=True)
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
      self.preopVolume = self.logic.applyBiasCorrection(self.preopVolume, self.preopLabel)
      self.preopVolumeSelector.setCurrentNode(self.preopVolume)
      self.biasCorrectionDone = True
    logging.debug('TARGETS PREOP')
    logging.debug(self.preopTargets)

    self.markupsLogic.SetAllMarkupsVisibility(self.preopTargets, 1)

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

  def patientCheckAfterImport(self, directory, fileList):
    for currentFile in fileList:
      currentFile = os.path.join(directory, currentFile)
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
    currentResult = self.getCurrentRegistrationResult()
    currentResult['accepted'] = True
    currentSeriesNumber = currentResult['name'].split(':')[0]
    for result in self.registrationResults:
      if result is not currentResult:
        seriesNumber = result['name'].split(':')[0]
        if currentSeriesNumber == seriesNumber:
          result['discarded'] = True
    self.updateRegistrationResultStatus()

  def onSkipRegistrationResultButtonClicked(self):
    currentResult = self.getCurrentRegistrationResult()
    currentResult['accepted'] = True
    currentResult['discarded'] = True
    currentSeriesNumber = currentResult['name'].split(':')[0]
    for result in self.registrationResults:
      if result is not currentResult:
        seriesNumber = result['name'].split(':')[0]
        if currentSeriesNumber == seriesNumber:
          result['accepted'] = True
          result['discarded'] = True
    self.updateRegistrationResultStatus()
    pass

  def updateRegistrationResultStatus(self):
    currentResult = self.getCurrentRegistrationResult()
    if currentResult['accepted'] or currentResult['discarded']:
      self.acceptRegistrationResultButton.hide()
      self.retryRegistrationButton.hide()
      self.skipRegistrationResultButton.hide()
      self.registrationResultStatus.show()
      if currentResult['accepted'] and not currentResult['discarded']:
        self.discardedRegistrationResultLabel.hide()
        self.acceptedRegistrationResultLabel.show()
        self.registrationResultStatus.setText("accepted!")
      elif currentResult['discarded']:
        self.acceptedRegistrationResultLabel.hide()
        self.discardedRegistrationResultLabel.show()
        if currentResult['accepted']:
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

      labelName = self.referenceVolumeSelector.currentNode().GetName() + '-label'
      self.currentIntraopLabel = self.logic.labelMapFromClippingModel(inputVolume)
      self.currentIntraopLabel.SetName(labelName)

      displayNode = self.currentIntraopLabel.GetDisplayNode()
      displayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNode1')

      self.intraopLabelSelector.setCurrentNode(self.currentIntraopLabel)

      self.markupsLogic.SetAllMarkupsVisibility(self.logic.inputMarkupNode, False)
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

    if self.retryMode:
      mostRecentCoverProstateRegistrationResult = self.getMostRecentAcceptedCoverProstateRegistration()
      if mostRecentCoverProstateRegistrationResult:
        self.preopVolumeSelector.setCurrentNode(mostRecentCoverProstateRegistrationResult['fixedVolume'])
        self.preopLabelSelector.setCurrentNode(mostRecentCoverProstateRegistrationResult['fixedLabel'])
        self.fiducialSelector.setCurrentNode(mostRecentCoverProstateRegistrationResult['outputTargetsBSpline'])

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

  def getMostRecentAcceptedCoverProstateRegistration(self):
    mostRecent = None
    for result in self.registrationResults:
      if "COVER PROSTATE" in result['name'] and result['accepted'] and not result['discarded']:
        mostRecent = result
    return mostRecent

  def onLabelSegmentationButtonClicked(self):
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    self.clearCurrentLabels()
    self.setSegmentationButtons(segmentationActive=True)
    self.compositeNodeRed.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())

    # create new labelmap and set
    referenceVolume = self.referenceVolumeSelector.currentNode()
    self.currentIntraopLabel = self.volumesLogic.CreateAndAddLabelVolume(slicer.mrmlScene, referenceVolume,
                                                                         referenceVolume.GetName() + '-label')
    self.intraopLabelSelector.setCurrentNode(self.currentIntraopLabel)
    selectionNode = slicer.app.applicationLogic().GetSelectionNode()
    selectionNode.SetReferenceActiveVolumeID(referenceVolume.GetID())
    selectionNode.SetReferenceActiveLabelVolumeID(self.currentIntraopLabel.GetID())
    slicer.app.applicationLogic().PropagateVolumeSelection(50)

    # show label
    self.compositeNodeRed.SetLabelOpacity(1)

    # set color table
    logging.debug('intraopLabelID : ' + str(self.currentIntraopLabel.GetID()))

    # set color table
    displayNode = self.currentIntraopLabel.GetDisplayNode()
    displayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNode1')

    parameterNode = self.editUtil.getParameterNode()
    parameterNode.SetParameter('effect', 'DrawEffect')

    # set label properties
    self.editUtil.setLabel(1)
    self.editUtil.setLabelOutline(1)

  def createRegistrationResult(self, params):

    # this function stores information and nodes of a single
    # registration run to be able to switch between results.

    name = self.generateNameForRegistrationResult(self.currentIntraopVolume)

    summary = {'name': name,
               'accepted': False,
               'discarded': False,
               'cmdArguments': self.logic.cmdArguments,
               'outputVolumeRigid': self.outputVolumes['Rigid'],
               'outputVolumeBSpline': self.outputVolumes['BSpline'],
               'outputTransformRigid': self.outputTransforms['Rigid'],
               'outputTransformBSpline': self.outputTransforms['BSpline'],
               'outputTargetsRigid': self.outputTargets['Rigid'],
               'outputTargetsBSpline': self.outputTargets['BSpline']}
    summary.update(params)

    if 'Affine' in self.outputVolumes.keys():
      summary['outputVolumeAffine'] = self.outputVolumes['Affine']
      summary['outputTransformAffine'] = self.outputTransforms['Affine']
      summary['outputTargetsAffine'] = self.outputTargets['Affine']

    self.registrationResults.append(summary)

    logging.debug('# ___________________________  registration output  ________________________________')
    logging.debug(summary)
    logging.debug('# __________________________________________________________________________________')

  def generateNameForRegistrationResult(self, intraoVolume):
    name = intraoVolume.GetName()
    nOccurences = 0
    for result in self.registrationResults:
      if name in result['name']:
        nOccurences += 1
    if nOccurences:
      name = name + "_Retry_" + str(nOccurences)
    return name

  def onApplyRegistrationClicked(self):
    fixedVolume = self.intraopVolumeSelector.currentNode()
    fixedLabel = self.intraopLabelSelector.currentNode()
    movingLabel = self.preopLabelSelector.currentNode()
    targets = self.fiducialSelector.currentNode()

    sourceVolumeNode = self.preopVolumeSelector.currentNode()
    movingVolume = self.volumesLogic.CloneVolume(slicer.mrmlScene, sourceVolumeNode, 'movingVolume-PREOP-INTRAOP')

    if self.logic.applyRegistration(fixedVolume, movingVolume, fixedLabel, movingLabel, targets):
      params = {'movingVolume': sourceVolumeNode,
                'fixedVolume': fixedVolume,
                'movingLabel': movingLabel,
                'fixedLabel': fixedLabel,
                'targets': targets}
      self.finalizeRegistrationStep(params)
      logging.debug('Registration is done')

  def onRetryRegistrationButtonClicked(self):
    # if self.yesNoDialog("Do you really want to discard the current registration results and reate a new segmentation "
    #                     "label on the current needle image?"):
    # self.deleteRegistrationResult(-1)
    self.retryMode = True
    self.tabWidget.setCurrentIndex(1)

  def deleteRegistrationResult(self, index):
    result = self.registrationResults[index]
    # TODO: deleting tragets causes total crash of Slicer
    nodesToDelete = ['fixedLabel', 'movingLabel', 'outputVolumeRigid', 'outputVolumeAffine', 'outputVolumeBSpline',
                     'outputTransformRigid', 'outputTransformAffine', 'outputTransformBSpline']
    # 'outputTargetsRigid', 'outputTargetAffine', 'outputTargetsBSpline']
    for node in [result[key] for key in nodesToDelete if key in result.keys()]:
      if node:
        slicer.mrmlScene.RemoveNodeReferences(node)
        slicer.mrmlScene.RemoveNode(node)

    self.registrationResults.remove(result)

  def onInvokeReRegistration(self):
    # moving volume: copy last fixed volume
    mostRecentCoverProstateRegistrationResult = self.getMostRecentAcceptedCoverProstateRegistration()
    sourceVolumeNode = mostRecentCoverProstateRegistrationResult['fixedVolume']
    movingVolume = self.volumesLogic.CloneVolume(slicer.mrmlScene, sourceVolumeNode, 'movingVolumeReReg')

    # get the intraop targets
    targets = mostRecentCoverProstateRegistrationResult['outputTargetsBSpline']

    # take the 'intraop label map', which is always fixed label in the very first preop-intraop registration
    originalFixedLabel = mostRecentCoverProstateRegistrationResult['fixedLabel']

    # create fixed label
    fixedLabel = self.volumesLogic.CreateAndAddLabelVolume(slicer.mrmlScene, self.currentIntraopVolume,
                                                           self.currentIntraopVolume.GetName() + '-label')

    lastRigidTfm = self.getLastRigidTransformation()
    self.logic.BRAINSResample(inputVolume=originalFixedLabel, referenceVolume=self.currentIntraopVolume,
                              outputVolume=fixedLabel, warpTransform=lastRigidTfm)

    if self.logic.applyReRegistration(fixedVolume=self.currentIntraopVolume, movingVolume=movingVolume,
                                      fixedLabel=fixedLabel, targets=targets, lastRigidTfm=lastRigidTfm):
      movingLabel = None
      params = {'movingVolume': sourceVolumeNode,
                'fixedVolume': self.currentIntraopVolume,
                'movingLabel': movingLabel,
                'fixedLabel': fixedLabel,
                'targets': targets}

      self.finalizeRegistrationStep(params)

      logging.debug(('Re-Registration is done'))

  def finalizeRegistrationStep(self, params):
    self.outputVolumes = self.logic.volumes
    self.outputTransforms = self.logic.transforms
    self.outputTargets = self.logic.transformedTargets

    self.createRegistrationResult(params)

    for targetNode in self.outputTargets.values():
      slicer.mrmlScene.AddNode(targetNode)

    self.updateRegistrationResultSelector()
    self.tabWidget.setCurrentIndex(3)
    self.uncheckSeriesSelectionItems()

  def getLastRigidTransformation(self):
    nCoverProstateRegistrations = sum([1 for result in self.registrationResults if "COVER PROSTATE" in result['name']])
    if len(self.registrationResults) == 1 or len(self.registrationResults) == nCoverProstateRegistrations:
      logging.debug('Resampling label with same mask')
      # last registration was preop-intraop, take the same mask
      # this is an identity transform:
      lastRigidTfm = vtk.vtkGeneralTransform()
      lastRigidTfm.Identity()
    else:
      lastRigidTfm = self.registrationResults[-1]['outputTransformRigid']
    return lastRigidTfm

  def setupScreenAfterRegistration(self):

    self.compositeNodeRed.SetForegroundVolumeID(self.currentIntraopVolume.GetID())
    self.compositeNodeRed.SetBackgroundVolumeID(self.registrationResults[-1]['outputVolumeBSpline'].GetID())
    self.compositeNodeYellow.SetBackgroundVolumeID(self.currentIntraopVolume.GetID())

    self.redSliceLogic.FitSliceToAll()
    self.yellowSliceLogic.FitSliceToAll()

    self.refreshViewNodeIDs(self.preopTargets, self.redSliceNode)
    self.refreshViewNodeIDs(self.outputTargets['Rigid'], self.yellowSliceNode)
    self.refreshViewNodeIDs(self.outputTargets['BSpline'], self.yellowSliceNode)

    if 'Affine' in self.outputTargets.keys():
      self.refreshViewNodeIDs(self.outputTargets['Affine'], self.yellowSliceNode)

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

  def checkTabAfterImport(self):
    # change icon of tabBar if user is not in Data selection tab
    if not self.tabWidget.currentIndex == 0:
      self.tabBar.setTabIcon(0, self.newImageDataIcon)


class SliceTrackerLogic(ScriptedLoadableModuleLogic):

  @staticmethod
  def getDICOMValue(currentFile, tag, fallback=None):
    db = slicer.dicomDatabase
    try:
      value = db.fileValue(currentFile, tag)
    except RuntimeError:
      logging.info("There are problems with accessing DICOM values from file %s" % currentFile)
      value = fallback
    return value

  @staticmethod
  def getFileList(directory):
    return [f for f in os.listdir(directory) if ".DS_Store" not in f]

  @staticmethod
  def importStudy(dicomDataDir):
    indexer = ctk.ctkDICOMIndexer()
    indexer.addDirectory(slicer.dicomDatabase, dicomDataDir)
    indexer.waitForImportFinished()

  @staticmethod
  def createTransformNode(name, isBSpline):
    node = slicer.vtkMRMLBSplineTransformNode() if isBSpline else slicer.vtkMRMLLinearTransformNode()
    node.SetName(name)
    slicer.mrmlScene.AddNode(node)
    return node

  @staticmethod
  def createVolumeNode(name):
    volume = slicer.vtkMRMLScalarVolumeNode()
    volume.SetName(name)
    slicer.mrmlScene.AddNode(volume)
    return volume

  def __init__(self, parent=None):
    ScriptedLoadableModuleLogic.__init__(self, parent)
    self.inputMarkupNode = None
    self.clippingModelNode = None
    self.volumes = {}
    self.transforms = {}
    self.transformedTargets = {}
    self.cmdArguments = ""
    self.seriesList = []
    self.alreadyLoadedSeries = {}

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

    progress = SliceTrackerWidget.makeProgressIndicator(2, 1)
    progress.labelText = '\nBias Correction'

    outputVolume = slicer.vtkMRMLScalarVolumeNode()
    outputVolume.SetName('volume-PREOP-N4')
    slicer.mrmlScene.AddNode(outputVolume)
    params = {'inputImageName': volume.GetID(),
              'maskImageName': label.GetID(),
              'outputImageName': outputVolume.GetID(),
              'numberOfIterations': '500,400,300'}

    slicer.cli.run(slicer.modules.n4itkbiasfieldcorrection, None, params, wait_for_completion=True)

    progress.setValue(2)
    progress.close()
    return outputVolume

  def createVolumeAndTransformNodes(self, registrationTypes, suffix):
    self.volumes = {}
    self.transforms = {}
    for regType in registrationTypes:
      isBSpline = regType == 'BSpline'
      self.transforms[regType] = self.createTransformNode(suffix + '-TRANSFORM-' + regType, isBSpline)
      self.volumes[regType] = self.createVolumeNode(suffix + '-VOLUME-' + regType)

  def applyRegistration(self, fixedVolume, movingVolume, fixedLabel, movingLabel, targets):

    if fixedVolume and movingVolume and fixedLabel and movingLabel:
      self.cmdArguments = ""
      self.fixedVolume = fixedVolume
      self.movingVolume = movingVolume
      self.fixedLabel = fixedLabel
      self.movingLabel = movingLabel

      self.progress = SliceTrackerWidget.makeProgressIndicator(4, 1)

      prefix = fixedVolume.GetName().split(":")[0]
      self.createVolumeAndTransformNodes(['Rigid', 'Affine', 'BSpline'], prefix)

      self.doRigidRegistration(movingBinaryVolume=self.movingLabel, initializeTransformMode="useCenterOfROIAlign")
      self.doAffineRegistration()
      self.doBSplineRegistration(initialTransform=self.transforms['Affine'], useScaleVersor3D=False,
                                 useScaleSkewVersor3D=True,
                                 movingBinaryVolume=self.movingLabel, useAffine=False, samplingPercentage="0.002",
                                 maskInferiorCutOffFromCenter="1000", numberOfHistogramBins="50",
                                 numberOfMatchPoints="10", metricSamplingStrategy="Random", costMetric="MMI")

      self.transformedTargets = self.transformTargets(['Rigid', 'Affine', 'BSpline'], targets, prefix)
      return True
    else:
      return False

  def applyReRegistration(self, fixedVolume, movingVolume, fixedLabel, targets, lastRigidTfm):

    if fixedVolume and movingVolume and fixedLabel and lastRigidTfm:
      self.cmdArguments = ""
      self.fixedVolume = fixedVolume
      self.movingVolume = movingVolume
      self.fixedLabel = fixedLabel

      self.progress = SliceTrackerWidget.makeProgressIndicator(4, 1)
      prefix = fixedVolume.GetName().split(":")[0]

      self.createVolumeAndTransformNodes(['Rigid', 'BSpline'], prefix)

      self.doRigidRegistration(initialTransform=lastRigidTfm)
      self.dilateMask(fixedLabel)
      self.doBSplineRegistration(initialTransform=self.transforms['Rigid'], useScaleVersor3D=True,
                                 useScaleSkewVersor3D=True, useAffine=True)

      self.transformedTargets = self.transformTargets(['Rigid', 'BSpline'], targets, prefix)

      return True
    else:
      return False

  def doBSplineRegistration(self, initialTransform, useScaleVersor3D, useScaleSkewVersor3D, **kwargs):
    self.progress.labelText = '\nBSpline registration'
    self.progress.setValue(3)
    paramsBSpline = {'fixedVolume': self.fixedVolume,
                     'movingVolume': self.movingVolume,
                     'outputVolume': self.volumes['BSpline'].GetID(),
                     'bsplineTransform': self.transforms['BSpline'].GetID(),
                     'fixedBinaryVolume': self.fixedLabel,
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
    self.cmdArguments += "BSpline Registration Parameters: %s" % str(paramsBSpline) + "\n\n"

    self.progress.labelText = '\nCompleted Registration'
    self.progress.setValue(4)
    self.progress.close()

  def doAffineRegistration(self):
    self.progress.labelText = '\nAffine registration'
    self.progress.setValue(2)
    paramsAffine = {'fixedVolume': self.fixedVolume,
                    'movingVolume': self.movingVolume,
                    'fixedBinaryVolume': self.fixedLabel,
                    'movingBinaryVolume': self.movingLabel,
                    'outputTransform': self.transforms['Affine'].GetID(),
                    'outputVolume': self.volumes['Affine'].GetID(),
                    'maskProcessingMode': "ROI",
                    'useAffine': True,
                    'initialTransform': self.transforms['Rigid']}
    slicer.cli.run(slicer.modules.brainsfit, None, paramsAffine, wait_for_completion=True)
    self.cmdArguments += "Affine Registration Parameters: %s" % str(paramsAffine) + "\n\n"

  def doRigidRegistration(self, **kwargs):
    self.progress.labelText = '\nRigid registration'
    self.progress.setValue(2)
    paramsRigid = {'fixedVolume': self.fixedVolume,
                   'movingVolume': self.movingVolume,
                   'fixedBinaryVolume': self.fixedLabel,
                   'outputTransform': self.transforms['Rigid'].GetID(),
                   'outputVolume': self.volumes['Rigid'].GetID(),
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
    self.cmdArguments += "Rigid Registration Parameters: %s" % str(paramsRigid) + "\n\n"

  def transformTargets(self, registrations, targets, prefix):
    outputTargets = {}
    if targets:
      for registration in registrations:
        name = prefix + '-TARGETS-' + registration
        outputTargets[registration] = self.cloneFiducialAndTransform(name, targets, self.transforms[registration])
    return outputTargets

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

  def initializeListener(self, directory):
    numberOfFiles = len(self.getFileList(directory))
    self.lastFileCount = numberOfFiles
    self.directory = directory
    self.createCurrentFileList(directory)
    self.startTimer()

  def startTimer(self):
    currentFileCount = len(self.getFileList(self.directory))
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

  def createLoadableFileListFromSelection(self, selectedSeriesList, directory):

    # this function creates a DICOM filelist for all files in intraop directory.
    # It compares the names of the studies in seriesList to the
    # DICOM tag of the DICOM filelist and creates a new list of list loadable
    # list, where it puts together all DICOM files of one series into one list

    if os.path.exists(directory):

      self.loadableList = {}
      for series in selectedSeriesList:
        self.loadableList[series] = []

      for dcm in self.getFileList(directory):
        currentFile = os.path.join(directory, dcm)
        seriesNumberDescription = self.makeSeriesNumberDescription(currentFile)
        if seriesNumberDescription and seriesNumberDescription in selectedSeriesList:
          self.loadableList[seriesNumberDescription].append(currentFile)

  def loadSeriesIntoSlicer(self, selectedSeries, directory):

    self.createLoadableFileListFromSelection(selectedSeries, directory)
    volume = None

    for series in [s for s in selectedSeries if s not in self.alreadyLoadedSeries.keys()]:
      files = self.loadableList[series]
      # create DICOMScalarVolumePlugin and load selectedSeries data from files into slicer
      scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()

      loadables = scalarVolumePlugin.examine([files])

      name = loadables[0].name
      volume = scalarVolumePlugin.load(loadables[0])
      volume.SetName(name)
      slicer.mrmlScene.AddNode(volume)
      self.alreadyLoadedSeries[series] = volume
    return volume

  def waitingForSeriesToBeCompleted(self):

    logging.debug('**  new data in intraop directory detected **')
    logging.debug('waiting 5 more seconds for the series to be completed')

    qt.QTimer.singleShot(5000, self.importDICOMSeries)

  def importDICOMSeries(self):
    newFileList = []
    indexer = ctk.ctkDICOMIndexer()
    db = slicer.dicomDatabase

    if self.thereAreFilesInTheFolderFlag == 1:
      newFileList = self.currentFileList
      self.thereAreFilesInTheFolderFlag = 0
    else:
      newFileList = list(set(self.getFileList(self.directory)) - set(self.currentFileList))

    for currentFile in newFileList:
      currentFile = os.path.join(self.directory, currentFile)
      indexer.addFile(db, currentFile, None)
      seriesNumberDescription = self.makeSeriesNumberDescription(currentFile)
      if seriesNumberDescription and seriesNumberDescription not in self.seriesList:
        self.seriesList.append(seriesNumberDescription)

    indexer.addDirectory(db, str(self.directory))
    indexer.waitForImportFinished()

    self.seriesList = sorted(self.seriesList, key=lambda series: int(series.split(":")[0]))

    slicer.modules.SliceTrackerWidget.patientCheckAfterImport(self.directory, newFileList)
    slicer.modules.SliceTrackerWidget.checkTabAfterImport()

  def makeSeriesNumberDescription(self, dicomFile):
    seriesDescription = self.getDICOMValue(dicomFile, DICOMTAGS.SERIES_DESCRIPTION)
    seriesNumber = self.getDICOMValue(dicomFile, DICOMTAGS.SERIES_NUMBER)
    seriesNumberDescription = None
    if seriesDescription and seriesNumber:
      seriesNumberDescription = seriesNumber + ":" + seriesDescription
    return seriesNumberDescription

  def getNeedleTipAndTargetsPositions(self, bSplineTargets):

    # Get the fiducial lists
    fidNode2 = slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0)

    # get the needleTip_position
    self.needleTip_position = [0.0, 0.0, 0.0]
    fidNode2.GetNthFiducialPosition(0, self.needleTip_position)

    # get the target position(s)
    number_of_targets = bSplineTargets.GetNumberOfFiducials()
    self.target_positions = []

    for target in range(number_of_targets):
      target_position = [0.0, 0.0, 0.0]
      bSplineTargets.GetNthFiducialPosition(target, target_position)
      self.target_positions.append(target_position)

    logging.debug('needleTip_position = ' + str(self.needleTip_position))
    logging.debug('target_positions are ' + str(self.target_positions))

    return [self.needleTip_position, self.target_positions]

  def setNeedleTipPosition(self):

    if slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0) is None:

      # if needle tip is placed for the first time:

      # create Markups Node & display node to store needle tip position
      needleTipMarkupDisplayNode = slicer.vtkMRMLMarkupsDisplayNode()
      needleTipMarkupNode = slicer.vtkMRMLMarkupsFiducialNode()
      needleTipMarkupNode.SetName('needle-tip')
      slicer.mrmlScene.AddNode(needleTipMarkupDisplayNode)
      slicer.mrmlScene.AddNode(needleTipMarkupNode)
      needleTipMarkupNode.SetAndObserveDisplayNodeID(needleTipMarkupDisplayNode.GetID())

      # dont show needle tip in red Slice View
      needleNode = slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0)
      needleDisplayNode = needleNode.GetDisplayNode()
      needleDisplayNode.AddViewNodeID(slicer.modules.SliceTrackerWidget.yellowSliceNode.GetID())

      # update the target table when markup was set
      needleTipMarkupNode.AddObserver(vtk.vtkCommand.ModifiedEvent,
                                      slicer.modules.SliceTrackerWidget.updateTargetTable)

      # be sure to have the correct display node
      needleTipMarkupDisplayNode = slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0).GetDisplayNode()

      # Set visual fiducial attributes
      needleTipMarkupDisplayNode.SetTextScale(1.6)
      needleTipMarkupDisplayNode.SetGlyphScale(2.0)
      needleTipMarkupDisplayNode.SetGlyphType(12)
      # TODO: set color is somehow not working here
      needleTipMarkupDisplayNode.SetColor(1, 1, 50)

    else:
      # remove fiducial
      needleNode = slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0)
      needleNode.RemoveAllMarkups()

      # clear target table
      slicer.modules.SliceTrackerWidget.clearTargetTable()

    # set active node ID and start place mode
    mlogic = slicer.modules.markups.logic()
    mlogic.SetActiveListID(slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0))
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

  def setupColorTable(self):

    # setup the PCampReview color table

    self.colorFile = os.path.join(slicer.modules.SliceTrackerWidget.modulePath,
                                  'Resources/Colors/PCampReviewColors.csv')
    self.PCampReviewColorNode = slicer.vtkMRMLColorTableNode()
    colorNode = self.PCampReviewColorNode
    colorNode.SetName('PCampReview')
    slicer.mrmlScene.AddNode(colorNode)
    colorNode.SetTypeToUser()
    with open(self.colorFile) as f:
      n = sum(1 for line in f)
    colorNode.SetNumberOfColors(n - 1)
    import csv
    self.structureNames = []
    with open(self.colorFile, 'rb') as csvfile:
      reader = csv.DictReader(csvfile, delimiter=',')
      for index, row in enumerate(reader):
        colorNode.SetColor(index, row['Label'], float(row['R']) / 255,
                           float(row['G']) / 255, float(row['B']) / 255, float(row['A']))
        self.structureNames.append(row['Label'])

  def takeScreenshot(self, name, description, layout=-1):
    # show the message even if not taking a screen shot
    self.delayDisplay(description)

    if self.enableScreenshots == 0:
      return

    lm = slicer.app.layoutManager()
    # switch on the type to get the requested window
    widget = 0
    if layout == slicer.qMRMLScreenShotDialog.FullLayout:
      # full layout
      widget = lm.viewport()
    elif layout == slicer.qMRMLScreenShotDialog.ThreeD:
      # just the 3D window
      widget = lm.threeDWidget(0).threeDView()
    elif layout == slicer.qMRMLScreenShotDialog.Red:
      # red slice window
      widget = lm.sliceWidget("Red")
    elif layout == slicer.qMRMLScreenShotDialog.Yellow:
      # yellow slice window
      widget = lm.sliceWidget("Yellow")
    elif layout == slicer.qMRMLScreenShotDialog.Green:
      # green slice window
      widget = lm.sliceWidget("Green")
    else:
      # default to using the full window
      widget = slicer.util.mainWindow()
      # reset the layout so that the node is set correctlyupdateSeriesSelectorTable
      layout = slicer.qMRMLScreenShotDialog.FullLayout

    # grab and convert to vtk image data
    qpixMap = qt.QPixmap().grabWidget(widget)
    qimage = qpixMap.toImage()
    imageData = vtk.vtkImageData()
    slicer.qMRMLUtils().qImageToVtkImageData(qimage, imageData)

    annotationLogic = slicer.modules.annotations.logic()
    annotationLogic.CreateSnapShot(name, description, layout, self.screenshotScaleFactor, imageData)

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
    # initialize Label Map
    outputLabelMap = slicer.vtkMRMLLabelMapVolumeNode()
    name = (slicer.modules.SliceTrackerWidget.referenceVolumeSelector.currentNode().GetName() + '-label')
    outputLabelMap.SetName(name)
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
